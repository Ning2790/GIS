"""认证业务逻辑。

本模块不直接读写用户数据（全部通过 users 模块的 service 完成）；
登录会话（sessions 表）由本模块管理：login 建立、refresh 轮换、logout 撤销。
refresh 带重放检测：已轮换令牌被延迟重放时整族撤销（见 refresh 的注释）。

需求 4.2「二次访问自动登录」的落地形态 = **设备绑定**（device_bindings 表）：
客户端生成并持久化随机 device_id，登录时登记设备、刷新时会话与设备必须匹配；
用户可查看已登录设备并逐个撤销（撤销设备即撤销其名下全部会话，该设备需重新登录）。
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BadRequestError, NotFoundError, UnauthorizedError
from app.core.security import create_access_token
from app.modules.admin import service as admin_service
from app.modules.auth import repository
from app.modules.auth.models import DeviceBinding, LoginSession
from app.modules.users import service as users_service
from app.modules.users.models import User, UserRole, UserStatus

logger = logging.getLogger(__name__)

# 刷新令牌有效期。访问令牌短时效（core/config.py），过期后用刷新令牌换新令牌对。
REFRESH_TOKEN_EXPIRE_DAYS = 30
_REFRESH_TOKEN_BYTES = 48
# 已撤销会话的保留时长：清理任务不早于此时长删除撤销记录（覆盖重放检测窗口）。
_REVOKED_RETENTION_SECONDS = 86400


def _hash_token(token: str) -> str:
    """刷新令牌为高熵随机串，存 SHA-256 哈希即可（不存明文）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(moment: datetime) -> datetime:
    """SQLite 读出的时间会丢时区信息，统一按 UTC 处理后再比较。"""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _refresh_ttl_seconds(remember: bool) -> int:
    """刷新令牌有效期（秒）：记住我 = 30 天；否则用配置的短期会话时长。"""
    if remember:
        return REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    return get_settings().refresh_token_short_expire_hours * 3600


def _start_session(
    db: Session,
    user_id: int,
    user_agent: str | None,
    family_id: str | None = None,
    device_id: str | None = None,
    *,
    remember: bool = True,
) -> tuple[str, int]:
    """建立登录会话并返回 (明文刷新令牌, 有效期秒数)；数据库只落哈希。

    family_id 为空 = 新登录（新家族）；refresh 轮换时传入旧会话的家族号（同族链），
    device_id / remember 同样由轮换继承。
    """
    ttl_seconds = _refresh_ttl_seconds(remember)
    token = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
    repository.create_session(
        db,
        LoginSession(
            user_id=user_id,
            family_id=family_id or secrets.token_hex(16),
            token_hash=_hash_token(token),
            user_agent=user_agent[:255] if user_agent else None,
            device_id=device_id,
            remember=remember,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        ),
    )
    return token, ttl_seconds


def register_tourist(
    db: Session,
    phone: str,
    password: str,
    nickname: str | None = None,
) -> User:
    return users_service.register(
        db,
        phone=phone,
        password=password,
        role=UserRole.TOURIST,
        nickname=nickname,
    )


def register_enterprise(
    db: Session,
    phone: str,
    password: str,
    license_no: str,
    license_file: str | None = None,
    nickname: str | None = None,
    role: str = UserRole.ENTERPRISE,
) -> User:
    if role not in (UserRole.ENTERPRISE, UserRole.MERCHANT):
        raise BadRequestError("角色只能是 enterprise 或 merchant")
    return users_service.register(
        db,
        phone=phone,
        password=password,
        role=role,
        nickname=nickname,
        license_no=license_no,
        license_file=license_file,
    )


def login(
    db: Session,
    phone: str,
    password: str,
    user_agent: str | None = None,
    *,
    device_id: str | None = None,
    device_label: str | None = None,
    ip: str | None = None,
    remember: bool = True,
) -> tuple[str, str, int, User]:
    """校验凭据并建立会话，返回 (access_token, refresh_token, refresh_expires_in, user)。

    携带 device_id 时同时登记设备绑定（需求 4.2）：二次访问据此免密续期，
    设备可在「已登录设备」里查看与撤销；remember=false 时刷新令牌为短期会话。
    """
    user = users_service.authenticate(db, phone, password)
    access_token = create_access_token(subject=str(user.id), role=user.role)
    refresh_token, expires_in = _start_session(
        db, user.id, user_agent, device_id=device_id, remember=remember
    )
    if device_id:
        repository.touch_binding(
            db,
            user_id=user.id,
            device_id=device_id,
            label=device_label,
            ip=ip,
            user_agent=user_agent[:255] if user_agent else None,
            now=datetime.now(UTC),
        )
    db.commit()  # 会话与设备绑定落库（repository 只 flush）
    return access_token, refresh_token, expires_in, user


def _verify_device(
    db: Session, session: LoginSession, *, device_id: str | None, now: datetime
) -> None:
    """设备校验（需求 4.2）：会话绑定过设备时，刷新必须来自同一设备且设备未被移除。

    - 未上报设备的老客户端（session.device_id 为空）不受影响；
    - 没带 device_id / 换了设备：拒绝并要求重新登录；
    - 设备已被用户移除：连带撤销该设备名下全部会话（处置立即落库）。
    """
    if not session.device_id:
        return
    if not device_id or device_id != session.device_id:
        raise UnauthorizedError("设备未绑定或已更换，请重新登录")
    binding = repository.get_binding(db, user_id=session.user_id, device_id=session.device_id)
    if binding is None or binding.revoked_at is not None:
        repository.revoke_sessions_for_device(
            db, user_id=session.user_id, device_id=session.device_id, revoked_at=now
        )
        db.commit()  # 设备移除的处置立即落库
        logger.info(
            "刷新请求来自已被移除的设备：user_id=%s device_id=%s", session.user_id, device_id
        )
        raise UnauthorizedError("该设备已被移除，请重新登录")


def refresh(
    db: Session, refresh_token: str, *, device_id: str | None = None, ip: str | None = None
) -> tuple[str, str, int]:
    """用刷新令牌换新令牌对，返回 (access_token, refresh_token, refresh_expires_in)。

    轮换：旧刷新令牌立即作废；撤销是原子条件更新，并发请求只有一个能成功
    （另一个按"登录已失效"拒绝）。会话过期 / 已撤销 / 用户状态异常时拒绝。
    设备校验：会话绑定过设备时，请求必须来自同一设备且设备未被移除（见 _verify_device）。

    **重放检测**：已轮换的令牌再次出现时区分两种情况——
    - 撤销发生在宽限期（REFRESH_REUSE_GRACE_SECONDS）内：并发刷新的正常竞态，仅拒绝；
    - 超出宽限期：判定为令牌重放（泄漏迹象），**撤销整个轮换家族**——攻击者手里的
      新令牌一并失效，合法用户重新登录（安全优先的取舍）。
    """
    now = datetime.now(UTC)
    session = repository.get_by_token_hash(db, _hash_token(refresh_token))
    if session is None:
        raise UnauthorizedError("登录已失效，请重新登录")
    if session.revoked_at is not None:
        revoke_age_seconds = (now - _as_utc(session.revoked_at)).total_seconds()
        if revoke_age_seconds > get_settings().refresh_reuse_grace_seconds:
            revoked_count = repository.revoke_family(db, session.family_id, now)
            db.commit()  # 重放处置立即落库（家族撤销不可丢）
            logger.warning(
                "检测到刷新令牌延迟重放，已撤销家族全部会话：family=%s user_id=%s count=%s",
                session.family_id,
                session.user_id,
                revoked_count,
            )
        raise UnauthorizedError("登录已失效，请重新登录")
    if _as_utc(session.expires_at) <= now:
        raise UnauthorizedError("登录已过期，请重新登录")
    _verify_device(db, session, device_id=device_id, now=now)

    try:
        user = users_service.get_user(db, session.user_id)
    except NotFoundError as exc:
        raise UnauthorizedError("登录已失效，请重新登录") from exc
    if user.status != UserStatus.ACTIVE:
        session.revoked_at = datetime.now(UTC)
        repository.save(db, session)
        db.commit()  # 异常账号的会话立即撤销
        raise UnauthorizedError("账号状态异常，请重新登录")

    if not repository.revoke_if_active(db, session.id, now):
        # 并发轮换：另一个请求抢先一步用掉了这个刷新令牌（宽限期内，不撤销家族）
        raise UnauthorizedError("登录已失效，请重新登录")

    access_token = create_access_token(subject=str(user.id), role=user.role)
    new_refresh_token, expires_in = _start_session(
        db,
        user.id,
        session.user_agent,
        family_id=session.family_id,
        device_id=session.device_id,
        remember=session.remember,
    )
    if session.device_id:
        # 顺带刷新设备的活跃时间（同一事务）：设备列表的「最近活跃」由此更新
        repository.touch_binding(
            db,
            user_id=session.user_id,
            device_id=session.device_id,
            label=None,
            ip=ip,
            user_agent=session.user_agent,
            now=now,
        )
    db.commit()  # 撤销旧会话 + 建立新会话 + 设备活跃时间同一事务（轮换原子化）
    return access_token, new_refresh_token, expires_in


def change_password(
    db: Session,
    user: User,
    *,
    old_password: str,
    new_password: str,
    user_agent: str | None = None,
    device_id: str | None = None,
    remember: bool = True,
) -> tuple[str, str, int]:
    """修改密码：校验原密码 → 更新哈希 → **撤销该用户全部会话** → 为当前端新开会话。

    返回新的 (access_token, refresh_token, refresh_expires_in)：当前端继续可用，
    其他设备（含浏览器里其它登录）下次刷新即失效，需要重新登录。
    当前端若上报了 device_id，新会话继续绑定该设备（否则会退化成"未绑定"会话）。
    """
    if not users_service.check_password(user, old_password):
        raise UnauthorizedError("原密码不正确")
    if users_service.check_password(user, new_password):
        raise BadRequestError("新密码不能与原密码相同")
    users_service.set_password(db, user, new_password)
    repository.revoke_all_for_user(db, user.id, datetime.now(UTC))
    access_token = create_access_token(subject=str(user.id), role=user.role)
    # remember 需与登录时一致：否则「不记住我」的短期会话会被改密码悄悄拉长到 30 天
    refresh_token, expires_in = _start_session(
        db, user.id, user_agent, device_id=device_id, remember=remember
    )
    db.commit()  # 新密码 + 撤销全部会话 + 当前端新会话
    return access_token, refresh_token, expires_in


def list_devices(
    db: Session, user: User, *, current_device_id: str | None = None
) -> list[tuple[DeviceBinding, bool]]:
    """已登录设备（仍有效的绑定，按最近活跃倒序），并标注哪条是当前设备。

    被移除的设备在重新登录后重新出现（显式登录即重新激活绑定）。
    """
    return [
        (binding, binding.device_id == current_device_id)
        for binding in repository.list_bindings(db, user.id)
    ]


def revoke_device(db: Session, user: User, *, binding_id: int) -> DeviceBinding:
    """移除一台已登录设备：撤销绑定 + 撤销该设备名下全部会话（该设备需重新登录）。

    只能操作自己的设备；他人 / 不存在的设备一律 404（不泄漏存在性）；
    审计与状态变更同事务（admin.service.record_action，commit=False）。
    """
    binding = repository.get_binding_by_id(db, binding_id)
    if binding is None or binding.user_id != user.id:
        raise NotFoundError("设备不存在")
    now = datetime.now(UTC)
    repository.revoke_binding(db, binding, now)
    revoked_sessions = repository.revoke_sessions_for_device(
        db, user_id=user.id, device_id=binding.device_id, revoked_at=now
    )
    admin_service.record_action(
        db,
        actor_id=user.id,
        action="device.revoke",
        target_type="device",
        target_id=binding.id,
        detail=(
            f"移除设备「{binding.device_label or binding.device_id[:8]}」，"
            f"撤销 {revoked_sessions} 个会话"
        ),
        commit=False,
    )
    db.commit()
    return binding


def cleanup_expired_sessions(db: Session) -> int:
    """清理无用的登录会话与设备绑定（Celery 定时任务调用，见 app/worker.py）。

    会话删两类：已过期的；已撤销且超过保留期（_REVOKED_RETENTION_SECONDS）的——
    保留期内的撤销记录是重放检测的依据，不能提前删。
    设备绑定删「已撤销且超过保留期」的（移除记录保留期同会话；重新登录会重新激活绑定，
    清理任务不能早于保留期，否则用户刚移除就被重新登录复活成未撤销记录）。
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=_REVOKED_RETENTION_SECONDS)
    deleted = repository.delete_stale(db, now=now, revoked_cutoff=cutoff)
    deleted += repository.delete_stale_bindings(db, revoked_cutoff=cutoff)
    db.commit()
    return deleted


def logout(db: Session, refresh_token: str) -> None:
    """撤销刷新令牌。幂等；令牌不存在也返回成功，不泄漏其是否存在。"""
    session = repository.get_by_token_hash(db, _hash_token(refresh_token))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        repository.save(db, session)
        db.commit()

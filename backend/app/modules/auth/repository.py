"""认证模块数据访问层。

仅供本模块 service 调用，禁止被其他模块 import；用户数据访问走
app.modules.users.service，本层只负责 sessions / device_bindings 两张表。
本层只 flush 不 commit：事务边界由 service 统一控制（如刷新轮换的
「撤销旧会话 + 创建新会话」在同一事务内完成）。
"""

from datetime import datetime

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import DeviceBinding, LoginSession


def create_session(db: Session, session: LoginSession) -> LoginSession:
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def get_by_token_hash(db: Session, token_hash: str) -> LoginSession | None:
    return db.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash))


def revoke_if_active(db: Session, session_id: int, revoked_at: datetime) -> bool:
    """原子撤销：仅当会话尚未撤销时置位，返回是否成功。

    并发轮换时（同一刷新令牌被两个请求同时使用）只有一个能拿到 True，
    避免"先查后写"导致同一令牌换出两条有效会话链。
    """
    result = db.execute(
        update(LoginSession)
        .where(LoginSession.id == session_id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )
    db.flush()
    return result.rowcount == 1


def revoke_family(db: Session, family_id: str, revoked_at: datetime) -> int:
    """撤销一个轮换家族内所有仍活跃的会话（重放检测的处置动作），返回撤销条数。"""
    result = db.execute(
        update(LoginSession)
        .where(LoginSession.family_id == family_id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )
    db.flush()
    return result.rowcount or 0


def delete_stale(db: Session, *, now: datetime, revoked_cutoff: datetime) -> int:
    """删除明显无用的会话：已过期，或撤销已超过保留期（重放检测窗口之外）。

    保留期内的已撤销会话要留着——它们是"轮换后令牌被延迟重放"的检测依据。
    """
    result = db.execute(
        delete(LoginSession).where(
            or_(
                LoginSession.expires_at <= now,
                and_(
                    LoginSession.revoked_at.is_not(None),
                    LoginSession.revoked_at <= revoked_cutoff,
                ),
            )
        )
    )
    db.flush()
    return result.rowcount or 0


def revoke_all_for_user(db: Session, user_id: int, revoked_at: datetime) -> int:
    """撤销某用户所有仍有效的会话（改密码后强制其他端重新登录），返回撤销条数。"""
    result = db.execute(
        update(LoginSession)
        .where(LoginSession.user_id == user_id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )
    db.flush()
    return result.rowcount or 0


def revoke_sessions_for_device(
    db: Session, *, user_id: int, device_id: str, revoked_at: datetime
) -> int:
    """撤销某设备名下所有仍活跃的会话（用户移除该设备时调用），返回撤销条数。"""
    result = db.execute(
        update(LoginSession)
        .where(
            LoginSession.user_id == user_id,
            LoginSession.device_id == device_id,
            LoginSession.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
    db.flush()
    return result.rowcount or 0


def save(db: Session, session: LoginSession) -> LoginSession:
    """落库对已加载会话对象的字段修改（只 flush；提交由 service 控制）。"""
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


# ---------- 设备绑定（需求 4.2） ----------


def get_binding(db: Session, *, user_id: int, device_id: str) -> DeviceBinding | None:
    return db.scalar(
        select(DeviceBinding).where(
            DeviceBinding.user_id == user_id, DeviceBinding.device_id == device_id
        )
    )


def get_binding_by_id(db: Session, binding_id: int) -> DeviceBinding | None:
    return db.get(DeviceBinding, binding_id)


def list_bindings(db: Session, user_id: int) -> list[DeviceBinding]:
    """该用户仍有效的设备绑定（按最近活跃倒序）。"""
    return list(
        db.scalars(
            select(DeviceBinding)
            .where(DeviceBinding.user_id == user_id, DeviceBinding.revoked_at.is_(None))
            .order_by(DeviceBinding.last_seen_at.desc(), DeviceBinding.id.desc())
        ).all()
    )


def touch_binding(
    db: Session,
    *,
    user_id: int,
    device_id: str,
    label: str | None,
    ip: str | None,
    user_agent: str | None,
    now: datetime,
) -> DeviceBinding:
    """登录成功后的设备绑定：新建或更新活跃信息（曾被撤销的设备重新登录即重新激活）。

    并发首绑（同一设备双提交）撞 (user_id, device_id) 唯一约束时，用 SAVEPOINT 只回滚
    这一行再复用先到者——外层事务（会话创建）不受影响。
    """
    binding = get_binding(db, user_id=user_id, device_id=device_id)
    if binding is None:
        new_binding = DeviceBinding(
            user_id=user_id,
            device_id=device_id,
            device_label=label,
            last_ip=ip,
            last_user_agent=user_agent,
            first_seen_at=now,
            last_seen_at=now,
        )
        try:
            with db.begin_nested():
                db.add(new_binding)
                db.flush()
        except IntegrityError:
            # 并发首绑：回落到复用先到者；若先到者也不存在（非本次预期的冲突）原样抛出
            binding = get_binding(db, user_id=user_id, device_id=device_id)
            if binding is None:
                raise
        else:
            binding = new_binding
    binding.device_label = label or binding.device_label
    binding.last_ip = ip or binding.last_ip
    binding.last_user_agent = user_agent or binding.last_user_agent
    binding.last_seen_at = now
    binding.revoked_at = None
    db.flush()
    return binding


def delete_stale_bindings(db: Session, *, revoked_cutoff: datetime) -> int:
    """删除已撤销且超过保留期的设备绑定（清理任务调用），返回条数。

    保留期内的撤销记录要留着——重新登录时会据它判断「重新激活」语义；
    未撤销的绑定永不删除（那是用户当前的登录设备）。
    """
    result = db.execute(
        delete(DeviceBinding).where(
            DeviceBinding.revoked_at.is_not(None),
            DeviceBinding.revoked_at <= revoked_cutoff,
        )
    )
    db.flush()
    return result.rowcount or 0


def revoke_binding(db: Session, binding: DeviceBinding, revoked_at: datetime) -> DeviceBinding:
    binding.revoked_at = revoked_at
    db.flush()
    return binding

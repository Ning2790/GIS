"""用户业务逻辑层。

其他模块只能调用本层，不得直接访问 users 的 repository / models。
"""

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import pagination
from app.core.errors import BadRequestError, ConflictError, NotFoundError, UnauthorizedError
from app.core.pagination import PageQuery
from app.core.security import hash_password, verify_password
from app.modules.files import service as files_service
from app.modules.users import repository
from app.modules.users.models import Address, User, UserRole, UserStatus

# 手机号不存在时也做一次等价的 bcrypt 校验，避免用响应耗时区分"手机号是否已注册"。
_DUMMY_PASSWORD_HASH = hash_password("timing-equalizer-not-a-real-password")

# 平台文件引用格式（受控上传产物，见 files 模块）
_PLATFORM_FILE_REF = re.compile(r"/api/v1/files/(\d+)")


def register(
    db: Session,
    phone: str,
    password: str,
    role: str = UserRole.TOURIST,
    nickname: str | None = None,
    license_no: str | None = None,
    license_file: str | None = None,
) -> User:
    """注册用户。

    游客注册后即可用；商户 / 企业必须提供营业执照号，注册后状态为待审核，
    需 admin 模块审核通过后才能登录。license_file 支持平台文件引用
    （``/api/v1/files/{id}``，须真实存在）或外部 URL 字符串。
    """
    if repository.get_by_phone(db, phone) is not None:
        raise ConflictError("该手机号已注册")

    if license_file:
        match = _PLATFORM_FILE_REF.fullmatch(license_file.strip())
        if match and not files_service.file_exists(db, int(match.group(1))):
            raise BadRequestError("license_file 引用的平台文件不存在，请先通过 /api/v1/files 上传")

    if role == UserRole.TOURIST:
        status = UserStatus.ACTIVE
    else:
        if not license_no:
            raise ConflictError("商户 / 企业注册必须提供营业执照号")
        status = UserStatus.PENDING_REVIEW

    user = User(
        phone=phone,
        password_hash=hash_password(password),
        role=role,
        status=status,
        nickname=nickname,
        license_no=license_no,
        license_file=license_file,
    )
    try:
        created = repository.create(db, user)
    except IntegrityError:
        # 并发同手机号注册：先查后插竞态由 phone 唯一索引兜底，按已注册处理
        db.rollback()
        raise ConflictError("该手机号已注册") from None
    db.commit()
    return created


def authenticate(db: Session, phone: str, password: str) -> User:
    """校验手机号 + 密码，返回可登录的用户。"""
    user = repository.get_by_phone(db, phone)
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise UnauthorizedError("手机号或密码错误")
    if not verify_password(password, user.password_hash):
        # 不区分"用户不存在"与"密码错误"，避免暴露手机号是否已注册
        raise UnauthorizedError("手机号或密码错误")
    if user.status == UserStatus.PENDING_REVIEW:
        raise UnauthorizedError("资质审核中，暂不可登录")
    if user.status == UserStatus.REJECTED:
        raise UnauthorizedError("资质审核未通过")
    if user.status == UserStatus.DISABLED:
        raise UnauthorizedError("账号已被禁用")
    return user


def update_profile(db: Session, user: User, *, nickname: str) -> User:
    """更新个人资料（昵称），返回更新后的用户。"""
    user.nickname = nickname
    saved = repository.save(db, user)
    db.commit()
    return saved


def check_password(user: User, raw_password: str) -> bool:
    """校验明文密码与用户当前密码是否匹配（供 auth 改密码等场景）。"""
    return verify_password(raw_password, user.password_hash)


def set_password(db: Session, user: User, new_password: str) -> User:
    """设置新密码（hash 后落库，提交由本函数负责），返回更新后的用户。"""
    user.password_hash = hash_password(new_password)
    saved = repository.save(db, user)
    db.commit()
    return saved


def get_user(db: Session, user_id: int) -> User:
    user = repository.get_by_id(db, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    return user


def list_users(
    db: Session,
    page: PageQuery,
    *,
    role: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
) -> tuple[list[User], int]:
    """分页查询用户（管理视图），返回 (当页用户, 总数)。

    按 role / status 精确过滤；keyword 模糊匹配手机号或昵称。
    """
    stmt = repository.user_list_query(role=role, status=status, keyword=keyword)
    return pagination.paginate(db, stmt, page)


def count_users(db: Session, *, role: str | None = None, status: str | None = None) -> int:
    """用户计数（控制台首页概览 / 待审核数用）。"""
    return repository.count_users(db, role=role, status=status)


def list_active_admin_ids(db: Session) -> list[int]:
    """启用状态的管理员 id（跨模块通知平台介入时使用）。"""
    return repository.list_active_admin_ids(db)


def display_names(db: Session, user_ids: list[int]) -> dict[int, str]:
    """批量取“昵称（兜底手机号）”，供导出等需要商户名称的场景使用。"""
    return {
        user.id: (user.nickname or user.phone)
        for user in repository.get_by_ids(db, list(set(user_ids)))
    }


def create_admin(
    db: Session,
    phone: str,
    password: str,
    nickname: str | None = None,
) -> User:
    """创建管理员账号（供 scripts/seed_admin.py 初始化首个管理员；重复创建报冲突）。"""
    if repository.get_by_phone(db, phone) is not None:
        raise ConflictError("该手机号已注册")

    user = User(
        phone=phone,
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        nickname=nickname,
    )
    created = repository.create(db, user)
    db.commit()
    return created


def approve(db: Session, user_id: int) -> User:
    """资质审核通过：待审核 → 正常（此后可登录）。"""
    user = get_user(db, user_id)
    if user.status != UserStatus.PENDING_REVIEW:
        raise ConflictError("该用户不在待审核状态")
    user.status = UserStatus.ACTIVE
    saved = repository.save(db, user)
    db.commit()
    return saved


def reject(db: Session, user_id: int) -> User:
    """资质驳回：待审核 → 已驳回（不可登录）。"""
    user = get_user(db, user_id)
    if user.status != UserStatus.PENDING_REVIEW:
        raise ConflictError("该用户不在待审核状态")
    user.status = UserStatus.REJECTED
    saved = repository.save(db, user)
    db.commit()
    return saved


def disable(db: Session, user_id: int) -> User:
    """禁用账号：正常 → 禁用（不可登录）。管理员账号不可被禁用。"""
    user = get_user(db, user_id)
    if user.role == UserRole.ADMIN:
        raise ConflictError("管理员账号不可被禁用")
    if user.status != UserStatus.ACTIVE:
        raise ConflictError("仅正常状态的账号可被禁用")
    user.status = UserStatus.DISABLED
    saved = repository.save(db, user)
    db.commit()
    return saved


def enable(db: Session, user_id: int) -> User:
    """解除禁用：禁用 → 正常（可登录）。"""
    user = get_user(db, user_id)
    if user.status != UserStatus.DISABLED:
        raise ConflictError("仅被禁用的账号可被启用")
    user.status = UserStatus.ACTIVE
    saved = repository.save(db, user)
    db.commit()
    return saved


# ---------- 收货地址（个人中心，需求 2.3 交付环节） ----------

# 单个用户的地址数量上限（个人中心维护，避免被当成无限存储用）
MAX_ADDRESSES_PER_USER = 20


def list_addresses(db: Session, user: User) -> list[Address]:
    """我的收货地址（默认地址在前）。"""
    return repository.list_addresses(db, user.id)


def create_address(
    db: Session,
    user: User,
    *,
    receiver_name: str,
    receiver_phone: str,
    address: str,
    is_default: bool = False,
) -> Address:
    """新增收货地址：首个地址自动设为默认；设为默认时清掉其他默认标记。

    并发首建（两个请求都读到「还没有地址」）会同时争默认位，靠数据库偏索引
    uq_user_addresses_default 兜底：撞唯一冲突则重读状态重试一次。
    """
    for attempt in range(2):
        if repository.count_addresses(db, user.id) >= MAX_ADDRESSES_PER_USER:
            raise BadRequestError(f"最多保存 {MAX_ADDRESSES_PER_USER} 个收货地址")
        make_default = is_default or repository.count_addresses(db, user.id) == 0
        if make_default:
            repository.clear_default(db, user.id)
        try:
            created = repository.create_address(
                db,
                Address(
                    user_id=user.id,
                    receiver_name=receiver_name,
                    receiver_phone=receiver_phone,
                    address=address,
                    is_default=make_default,
                ),
            )
            db.commit()
            return created
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise ConflictError("地址保存冲突，请重试") from None
    raise ConflictError("地址保存冲突，请重试")  # pragma: no cover（循环内已返回或抛出）


def _get_own_address(db: Session, user: User, address_id: int) -> Address:
    """取自己的地址；他人 / 不存在一律 404（不泄漏存在性）。"""
    found = repository.get_address(db, address_id)
    if found is None or found.user_id != user.id:
        raise NotFoundError("地址不存在")
    return found


def _mark_default(db: Session, user: User, found: Address) -> Address:
    """把该地址设为默认：清旧默认 → 置位 → 提交。

    并发切换（两个标签页同时设默认）可能撞数据库偏索引 uq_user_addresses_default，
    这里回滚重试一次以收敛；仍冲突返回 409 让客户端重试。
    """
    for attempt in range(2):
        repository.clear_default(db, user.id)
        found.is_default = True
        try:
            repository.save_address(db, found)
            db.commit()
            return found
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise ConflictError("默认地址切换冲突，请重试") from None
    raise ConflictError("默认地址切换冲突，请重试")  # pragma: no cover


def update_address(
    db: Session,
    user: User,
    address_id: int,
    *,
    receiver_name: str,
    receiver_phone: str,
    address: str,
    is_default: bool = False,
) -> Address:
    """更新收货地址（全量字段）。取消默认需通过另一地址设为默认，保证始终有一个默认。"""
    found = _get_own_address(db, user, address_id)
    found.receiver_name = receiver_name
    found.receiver_phone = receiver_phone
    found.address = address
    if is_default and not found.is_default:
        return _mark_default(db, user, found)
    repository.save_address(db, found)
    db.commit()
    return found


def set_default_address(db: Session, user: User, address_id: int) -> Address:
    return _mark_default(db, user, _get_own_address(db, user, address_id))


def delete_address(db: Session, user: User, address_id: int) -> None:
    """删除地址；若删的是默认地址，则把最新的一个补为默认（保持始终有一个默认）。"""
    found = _get_own_address(db, user, address_id)
    was_default = found.is_default
    repository.delete_address(db, found)
    db.flush()
    if was_default:
        remaining = repository.list_addresses(db, user.id)
        if remaining:
            remaining[0].is_default = True
    db.commit()

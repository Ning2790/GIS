"""用户数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
"""

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.users.models import Address, User, UserRole, UserStatus


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def list_active_admin_ids(db: Session) -> list[int]:
    """启用状态的管理员 id（支付异常等需要平台介入的通知用）。"""
    return list(
        db.scalars(
            select(User.id).where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
        ).all()
    )


def get_by_phone(db: Session, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == phone))


def get_by_ids(db: Session, user_ids: list[int]) -> list[User]:
    """批量取用户（导出时补商户名称，避免逐条查询）。"""
    if not user_ids:
        return []
    return list(db.scalars(select(User).where(User.id.in_(user_ids))).all())


def _like_pattern(keyword: str) -> str:
    """转义 LIKE 通配符（% _ \\），避免用户输入被当通配符扫描全表。"""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def user_list_query(
    *,
    role: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
) -> Select[tuple[User]]:
    """用户列表查询（管理视图用）：role / status 精确过滤，keyword 模糊匹配手机号或昵称。"""
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if keyword:
        pattern = _like_pattern(keyword)
        stmt = stmt.where(
            or_(
                User.phone.like(pattern, escape="\\"),
                User.nickname.like(pattern, escape="\\"),
            )
        )
    return stmt.order_by(User.id.desc())


def count_users(db: Session, *, role: str | None = None, status: str | None = None) -> int:
    """用户计数（控制台首页概览 / 待审核数用）。"""
    stmt = select(func.count()).select_from(User)
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    return db.scalar(stmt) or 0


def create(db: Session, user: User) -> User:
    """新增用户（只 flush；提交由 service 统一控制）。"""
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def save(db: Session, user: User) -> User:
    """落库对已加载用户对象的字段修改（只 flush；提交由 service 控制）。"""
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


# ---------- 收货地址（个人中心） ----------


def list_addresses(db: Session, user_id: int) -> list[Address]:
    """该用户的收货地址（默认地址在前，其余按新到旧）。"""
    return list(
        db.scalars(
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.is_default.desc(), Address.id.desc())
        ).all()
    )


def count_addresses(db: Session, user_id: int) -> int:
    return (
        db.scalar(select(func.count()).select_from(Address).where(Address.user_id == user_id)) or 0
    )


def get_address(db: Session, address_id: int) -> Address | None:
    return db.get(Address, address_id)


def create_address(db: Session, address: Address) -> Address:
    db.add(address)
    db.flush()
    db.refresh(address)
    return address


def delete_address(db: Session, address: Address) -> None:
    db.delete(address)
    db.flush()


def save_address(db: Session, address: Address) -> Address:
    """落库对已加载地址对象的字段修改（只 flush；提交由 service 控制）。"""
    db.add(address)
    db.flush()
    db.refresh(address)
    return address


def clear_default(db: Session, user_id: int) -> None:
    """清掉该用户的默认标记（设置新默认前调用，保证默认地址唯一）。"""
    db.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
    )
    db.flush()

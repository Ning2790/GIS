"""用户 ORM 模型。

users 表由本模块独占。其他模块如需用户数据，请调用 app.modules.users.service。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole:
    """用户角色。

    游客可访问旅游 / 装备 / 商城；商户与企业可额外访问 B2B 信息平台；admin 为平台运营。
    """

    TOURIST = "tourist"
    MERCHANT = "merchant"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"


class UserStatus:
    """账号状态。商户 / 企业注册后需资质审核，默认待审核，审核通过方可登录。"""

    ACTIVE = "active"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.TOURIST, index=True)
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE)
    nickname: Mapped[str | None] = mapped_column(String(64), default=None)

    # 商户 / 企业资质（预留字段，审核流程后续在 admin 模块实现）
    license_no: Mapped[str | None] = mapped_column(String(64), default=None)
    license_file: Mapped[str | None] = mapped_column(String(255), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Address(Base):
    """常用收货地址（个人中心维护）。

    下单时把地址**快照**进订单（receiver_name / receiver_phone / receiver_address），
    因此修改或删除地址不影响历史订单。
    """

    __tablename__ = "user_addresses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    receiver_name: Mapped[str] = mapped_column(String(32))
    receiver_phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # 数据库层兜底：每个用户至多一个默认地址（PG / SQLite 都支持部分唯一索引）。
    # 服务层的「清旧默认 → 置新默认」在并发下可能写偏斜，靠这条索引收敛。
    __table_args__ = (
        Index(
            "uq_user_addresses_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default"),
        ),
    )

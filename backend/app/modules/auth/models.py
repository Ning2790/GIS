"""认证模块 ORM 模型。

登录会话（sessions）由本模块独占：一次 login 建立一条，refresh 轮换，logout 撤销。
用户数据仍由 users 模块独占，认证所需的用户读写一律通过 app.modules.users.service。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginSession(Base):
    """登录会话。

    只存刷新令牌的 SHA-256 哈希（不存明文）；同一用户可同时存在多条（多设备登录）。
    family_id 标识一条"轮换链"（一次登录 = 一个家族，refresh 轮换继承同族）：
    检测到已轮换令牌被延迟重放时整族撤销（见 service.refresh 的重放检测）。
    device_id 为该会话绑定的设备（可为空 = 未上报设备的旧客户端）：
    刷新时会话与设备必须匹配，设备被撤销则其名下会话一并失效（见 service.refresh）。
    remember 记录登录时的「记住我」选择：影响轮换时新会话的有效期（长 / 短两档）。
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), default=None)
    device_id: Mapped[str | None] = mapped_column(String(64), default=None)
    remember: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class DeviceBinding(Base):
    """设备绑定（需求 4.2「二次访问自动登录」的落地形态）。

    device_id 由客户端生成并持久化（随机 ID；不采集硬件指纹，规避个人信息合规风险）。
    它只作"设备标识 + 风控信号"，真正的凭据仍是刷新令牌——刷新时会话与设备必须匹配。
    用户可查看已登录设备并逐个撤销；撤销会同时撤销该设备名下的全部会话。
    显式重新登录即重新激活（revoked_at 复位），换设备 / 清缓存则回落到重新登录。
    """

    __tablename__ = "device_bindings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    device_label: Mapped[str | None] = mapped_column(String(64), default=None)
    last_ip: Mapped[str | None] = mapped_column(String(45), default=None)
    last_user_agent: Mapped[str | None] = mapped_column(String(255), default=None)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # 保留期 / 清理按 last_seen_at 过滤（数据增长方案）
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_device_bindings_user_device"),
    )

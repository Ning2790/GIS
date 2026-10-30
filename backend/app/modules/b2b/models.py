"""b2b ORM 模型。

需求 2.4：供需信息撮合——**平台只提供信息服务、不做交易**，
本模块的表里不出现订单 / 支付字段。
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class B2bStatus:
    """发布信息状态。"""

    OPEN = "open"
    CLOSED = "closed"


class B2bSupply(Base):
    """供给信息（农户 / 企业发布：我能提供什么）。"""

    __tablename__ = "b2b_supplies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)  # 发布者（商户 / 企业）
    title: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), index=True)  # 品类
    region: Mapped[str] = mapped_column(String(64), index=True)  # 地区 / 州
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(16), default="吨")
    price_expect: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=B2bStatus.OPEN, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class B2bDemand(Base):
    """需求信息（加工企业发布：我需要什么）。"""

    __tablename__ = "b2b_demands"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), index=True)
    region: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(16), default="吨")
    price_expect: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=B2bStatus.OPEN, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class B2bMatch(Base):
    """匹配记录（规则匹配结果；仅信息撮合，不含任何交易字段）。"""

    __tablename__ = "b2b_matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(index=True)
    supply_id: Mapped[int] = mapped_column(index=True)
    score: Mapped[int]  # 匹配分（0-100）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("demand_id", "supply_id", name="uq_b2b_match"),)

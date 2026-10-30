"""gear ORM 模型。

新增或修改表后，需生成 Alembic 迁移：
    uv run alembic revision --autogenerate -m "描述"
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeatherSnapshot(Base):
    """某城市某日的环境快照（气象 / 土壤 / 海拔 / 气压；当前由模拟源采集）。"""

    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    soil_moisture_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    altitude_m: Mapped[int]
    pressure_hpa: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    source: Mapped[str] = mapped_column(String(32), default="mock")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("city", "snapshot_date", name="uq_weather_city_date"),)


class GearRecommendation(Base):
    """装备建议（按快照缓存：同一快照只生成一次）。items 存 JSON 数组文本。"""

    __tablename__ = "gear_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(unique=True)
    items: Mapped[str] = mapped_column(Text)  # JSON 数组，如 ["防晒霜（SPF50+）", ...]
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

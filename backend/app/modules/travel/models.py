"""travel ORM 模型。

新增或修改表后，需生成 Alembic 迁移：
    uv run alembic revision --autogenerate -m "描述"
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attraction(Base):
    """景点。

    地理字段先用经纬度 float；PostGIS 几何列在 map 阶段以新迁移补充。
    """

    __tablename__ = "attractions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    city: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[float | None] = mapped_column(default=None)
    longitude: Mapped[float | None] = mapped_column(default=None)
    cover_image: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Ticket(Base):
    """景点门票。"""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Itinerary(Base):
    """游客行程（AI 生成，可增删排序停靠点）。"""

    __tablename__ = "itineraries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(128))
    days: Mapped[int]
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2), default=None)
    preferences: Mapped[str] = mapped_column(Text, default="")
    fitness: Mapped[str | None] = mapped_column(String(64), default=None)
    risk_notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ItineraryStop(Base):
    """行程停靠点，按 (day, position) 排序。"""

    __tablename__ = "itinerary_stops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id"), index=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), index=True)
    day: Mapped[int] = mapped_column(default=1)
    position: Mapped[int] = mapped_column(default=1)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # 同日同序号的停靠点唯一：并发全量替换的最后防线（应用层另有行锁串行化）。
    __table_args__ = (
        UniqueConstraint("itinerary_id", "day", "position", name="uq_itinerary_stop_day_pos"),
    )


class Route(Base):
    """预设路线：运营维护的经典线路，游客可整体套用为个人行程。

    与个人行程（itineraries）分开存：路线是平台资产、所有人可浏览；
    套用时复制一份到 itineraries + itinerary_stops，之后互不影响。
    """

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    theme: Mapped[str] = mapped_column(String(32), default="", index=True)  # 环湖 / 人文 / 摄影…
    days: Mapped[int]
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2), default=None)  # 人均预估
    description: Mapped[str] = mapped_column(Text, default="")
    cover_image: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RouteStop(Base):
    """预设路线停靠点，按 (day, position) 排序；note 为当日玩法 / 提示。"""

    __tablename__ = "route_stops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), index=True)
    day: Mapped[int] = mapped_column(default=1)
    position: Mapped[int] = mapped_column(default=1)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

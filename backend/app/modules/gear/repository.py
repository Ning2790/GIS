"""gear 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
"""

from datetime import date

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.modules.gear.models import GearRecommendation, WeatherSnapshot


def get_snapshot(db: Session, *, city: str, snapshot_date: date) -> WeatherSnapshot | None:
    stmt = select(WeatherSnapshot).where(
        WeatherSnapshot.city == city, WeatherSnapshot.snapshot_date == snapshot_date
    )
    return db.scalar(stmt)


def snapshot_list_query(
    *,
    city: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Select[tuple[WeatherSnapshot]]:
    stmt = select(WeatherSnapshot)
    if city:
        stmt = stmt.where(WeatherSnapshot.city == city)
    if date_from is not None:
        stmt = stmt.where(WeatherSnapshot.snapshot_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(WeatherSnapshot.snapshot_date <= date_to)
    return stmt.order_by(WeatherSnapshot.snapshot_date.asc(), WeatherSnapshot.city.asc())


def create_snapshot(db: Session, snapshot: WeatherSnapshot) -> WeatherSnapshot:
    db.add(snapshot)
    db.flush()
    db.refresh(snapshot)
    return snapshot


def get_recommendation_by_snapshot(db: Session, snapshot_id: int) -> GearRecommendation | None:
    stmt = select(GearRecommendation).where(GearRecommendation.snapshot_id == snapshot_id)
    return db.scalar(stmt)


def create_recommendation(db: Session, recommendation: GearRecommendation) -> GearRecommendation:
    db.add(recommendation)
    db.flush()
    db.refresh(recommendation)
    return recommendation


def delete_snapshots_in_range(db: Session, *, cities: list[str], start: date, end: date) -> int:
    """删除指定城市在 [start, end] 内的快照及基于其生成的建议（--refresh 重采用）。

    返回删除的快照条数；建议随快照一并删除，避免指向已删快照成为孤儿缓存。
    由调用方提交事务（repository 只 flush / 执行语句）。
    """
    ids = db.scalars(
        select(WeatherSnapshot.id).where(
            WeatherSnapshot.city.in_(cities),
            WeatherSnapshot.snapshot_date >= start,
            WeatherSnapshot.snapshot_date <= end,
        )
    ).all()
    if not ids:
        return 0
    db.execute(delete(GearRecommendation).where(GearRecommendation.snapshot_id.in_(ids)))
    db.execute(delete(WeatherSnapshot).where(WeatherSnapshot.id.in_(ids)))
    return len(ids)

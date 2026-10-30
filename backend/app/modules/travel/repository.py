"""travel 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
"""

from sqlalchemy import Select, delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.modules.travel.models import (
    Attraction,
    Itinerary,
    ItineraryStop,
    Route,
    RouteStop,
    Ticket,
)


def _like_pattern(keyword: str) -> str:
    """转义 LIKE 通配符（% _ \\），避免用户输入被当通配符扫描全表。"""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def attraction_list_query(
    *,
    city: str | None = None,
    keyword: str | None = None,
) -> Select[tuple[Attraction]]:
    """景点列表查询：city 精确过滤，keyword 模糊匹配名称或城市。"""
    stmt = select(Attraction)
    if city:
        stmt = stmt.where(Attraction.city == city)
    if keyword:
        pattern = _like_pattern(keyword)
        stmt = stmt.where(
            or_(
                Attraction.name.like(pattern, escape="\\"),
                Attraction.city.like(pattern, escape="\\"),
            )
        )
    return stmt.order_by(Attraction.id.desc())


def get_attraction(db: Session, attraction_id: int) -> Attraction | None:
    return db.get(Attraction, attraction_id)


def list_tickets(db: Session, attraction_id: int) -> list[Ticket]:
    stmt = select(Ticket).where(Ticket.attraction_id == attraction_id).order_by(Ticket.id.asc())
    return list(db.scalars(stmt).all())


def list_attractions_for_planning(db: Session) -> list[Attraction]:
    """行程规划候选景点（按 id 升序，保证生成结果可复现）。"""
    return list(db.scalars(select(Attraction).order_by(Attraction.id.asc())).all())


def get_attractions_by_ids(db: Session, attraction_ids: list[int]) -> dict[int, Attraction]:
    if not attraction_ids:
        return {}
    rows = db.scalars(select(Attraction).where(Attraction.id.in_(attraction_ids))).all()
    return {row.id: row for row in rows}


def create_itinerary(db: Session, itinerary: Itinerary) -> Itinerary:
    db.add(itinerary)
    db.flush()
    db.refresh(itinerary)
    return itinerary


def save_itinerary(db: Session, itinerary: Itinerary) -> Itinerary:
    db.add(itinerary)
    db.flush()
    db.refresh(itinerary)
    return itinerary


def get_itinerary(db: Session, itinerary_id: int) -> Itinerary | None:
    return db.get(Itinerary, itinerary_id)


def delete_itinerary(db: Session, itinerary: Itinerary) -> None:
    """删除行程：先删停靠点再删行程（PG 强制外键，SQLite 默认不校验）。"""
    db.execute(delete(ItineraryStop).where(ItineraryStop.itinerary_id == itinerary.id))
    db.delete(itinerary)
    db.flush()


def itinerary_list_query(user_id: int) -> Select[tuple[Itinerary]]:
    return select(Itinerary).where(Itinerary.user_id == user_id).order_by(Itinerary.id.desc())


def route_list_query(*, theme: str | None = None) -> Select[tuple[Route]]:
    """预设路线列表：theme 精确过滤。"""
    stmt = select(Route)
    if theme:
        stmt = stmt.where(Route.theme == theme)
    return stmt.order_by(Route.id.desc())


def get_route(db: Session, route_id: int) -> Route | None:
    return db.get(Route, route_id)


def create_route(db: Session, route: Route) -> Route:
    db.add(route)
    db.flush()
    db.refresh(route)
    return route


def save_route(db: Session, route: Route) -> Route:
    db.add(route)
    db.flush()
    db.refresh(route)
    return route


def delete_route(db: Session, route: Route) -> None:
    """删除路线：先删停靠点再删路线（与行程删除同因：PG 强制外键）。"""
    db.execute(delete(RouteStop).where(RouteStop.route_id == route.id))
    db.delete(route)
    db.flush()


def replace_route_stops(db: Session, route_id: int, stops: list[RouteStop]) -> None:
    """全量替换路线停靠点（先删后插；提交由 service 负责）。"""
    db.execute(delete(RouteStop).where(RouteStop.route_id == route_id))
    for stop in stops:
        db.add(stop)
    db.flush()


def list_route_stops(db: Session, route_id: int) -> list[RouteStop]:
    stmt = (
        select(RouteStop)
        .where(RouteStop.route_id == route_id)
        .order_by(RouteStop.day.asc(), RouteStop.position.asc(), RouteStop.id.asc())
    )
    return list(db.scalars(stmt).all())


def stop_counts_by_route(db: Session, route_ids: list[int]) -> dict[int, int]:
    """按路线统计停靠点数量（列表页展示用，避免逐条查询）。"""
    if not route_ids:
        return {}
    rows = db.execute(
        select(RouteStop.route_id, func.count())
        .where(RouteStop.route_id.in_(route_ids))
        .group_by(RouteStop.route_id)
    ).all()
    return {route_id: count for route_id, count in rows}


def list_stops(db: Session, itinerary_id: int) -> list[ItineraryStop]:
    stmt = (
        select(ItineraryStop)
        .where(ItineraryStop.itinerary_id == itinerary_id)
        .order_by(ItineraryStop.day.asc(), ItineraryStop.position.asc(), ItineraryStop.id.asc())
    )
    return list(db.scalars(stmt).all())


def replace_stops(db: Session, itinerary_id: int, stops: list[ItineraryStop]) -> bool:
    """全量替换停靠点（先删后插，同一事务；提交由 service 负责）。

    先对行程行加排他锁，把同一行程的并发替换串行化，避免先删后插的
    两边都插入（静默重复）或撞唯一约束；SQLite 会忽略 FOR UPDATE（无碍，
    唯一约束仍兜底），PostgreSQL 生效。
    返回 False 表示行程已不存在（锁不到行，例如被并发删除）。
    """
    locked = db.execute(
        select(Itinerary.id).where(Itinerary.id == itinerary_id).with_for_update()
    ).first()
    if locked is None:
        return False
    db.execute(delete(ItineraryStop).where(ItineraryStop.itinerary_id == itinerary_id))
    for stop in stops:
        db.add(stop)
    db.flush()
    return True


def attraction_points_query(
    db: Session,
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> Select[tuple[Attraction]]:
    """点位查询：只含坐标齐全的景点。

    bbox 为 (min_lng, min_lat, max_lng, max_lat)。PostgreSQL 走 PostGIS 的 geom 列
    （GIST 索引 + && 包围盒相交）；其他方言（测试用 SQLite）退化为经纬度范围过滤。
    """
    stmt = select(Attraction).where(
        Attraction.latitude.is_not(None), Attraction.longitude.is_not(None)
    )
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = bbox
        if db.get_bind().dialect.name == "postgresql":
            stmt = stmt.where(
                text(
                    "attractions.geom && ST_MakeEnvelope("
                    ":min_lng, :min_lat, :max_lng, :max_lat, 4326)"
                ).bindparams(min_lng=min_lng, min_lat=min_lat, max_lng=max_lng, max_lat=max_lat)
            )
        else:
            stmt = stmt.where(
                Attraction.latitude.between(min_lat, max_lat),
                Attraction.longitude.between(min_lng, max_lng),
            )
    return stmt.order_by(Attraction.id.asc())


def backfill_geom(db: Session) -> int:
    """把经纬度回填到 PostGIS 的 geom 列（仅 PostgreSQL；SQLite 返回 0）。

    当前没有景点 CRUD 接口（仅 seed 脚本直插），新增景点后由调用方执行本函数；
    将来加管理端 CRUD 时需在写入路径同步 geom（或改为数据库触发器）。
    """
    if db.get_bind().dialect.name != "postgresql":
        return 0
    result = db.execute(
        text(
            "UPDATE attractions SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
            "WHERE geom IS NULL AND longitude IS NOT NULL AND latitude IS NOT NULL"
        )
    )
    db.flush()
    return result.rowcount or 0

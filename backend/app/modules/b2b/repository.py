"""b2b 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
"""

from sqlalchemy import Select, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.b2b.models import B2bDemand, B2bMatch, B2bStatus, B2bSupply


def _like_pattern(keyword: str) -> str:
    """转义 LIKE 通配符（% _ \\），避免用户输入被当通配符扫描全表。"""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def create_supply(db: Session, supply: B2bSupply) -> B2bSupply:
    db.add(supply)
    db.flush()
    db.refresh(supply)
    return supply


def get_supply(db: Session, supply_id: int) -> B2bSupply | None:
    return db.get(B2bSupply, supply_id)


def save_supply(db: Session, supply: B2bSupply) -> B2bSupply:
    db.add(supply)
    db.flush()
    db.refresh(supply)
    return supply


def open_supplies_query(
    *, category: str | None = None, region: str | None = None
) -> Select[tuple[B2bSupply]]:
    stmt = select(B2bSupply).where(B2bSupply.status == B2bStatus.OPEN)
    if category:
        stmt = stmt.where(B2bSupply.category == category)
    if region:
        stmt = stmt.where(B2bSupply.region == region)
    return stmt


def supply_list_query(
    *,
    category: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
) -> Select[tuple[B2bSupply]]:
    stmt = open_supplies_query(category=category, region=region)
    if keyword:
        pattern = _like_pattern(keyword)
        stmt = stmt.where(
            or_(
                B2bSupply.title.like(pattern, escape="\\"),
                B2bSupply.category.like(pattern, escape="\\"),
            )
        )
    return stmt.order_by(B2bSupply.id.desc())


def get_supplies_by_ids(db: Session, supply_ids: list[int]) -> dict[int, B2bSupply]:
    if not supply_ids:
        return {}
    rows = db.scalars(select(B2bSupply).where(B2bSupply.id.in_(supply_ids))).all()
    return {row.id: row for row in rows}


def create_demand(db: Session, demand: B2bDemand) -> B2bDemand:
    db.add(demand)
    db.flush()
    db.refresh(demand)
    return demand


def get_demand(db: Session, demand_id: int) -> B2bDemand | None:
    return db.get(B2bDemand, demand_id)


def save_demand(db: Session, demand: B2bDemand) -> B2bDemand:
    db.add(demand)
    db.flush()
    db.refresh(demand)
    return demand


def demand_list_query(
    *,
    category: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
) -> Select[tuple[B2bDemand]]:
    stmt = select(B2bDemand).where(B2bDemand.status == B2bStatus.OPEN)
    if category:
        stmt = stmt.where(B2bDemand.category == category)
    if region:
        stmt = stmt.where(B2bDemand.region == region)
    if keyword:
        pattern = _like_pattern(keyword)
        stmt = stmt.where(
            or_(
                B2bDemand.title.like(pattern, escape="\\"),
                B2bDemand.category.like(pattern, escape="\\"),
            )
        )
    return stmt.order_by(B2bDemand.id.desc())


def replace_matches(db: Session, demand_id: int, matches: list[B2bMatch]) -> bool:
    """全量替换某需求的匹配记录（先删后插；提交由 service 负责）。

    并发下另一请求可能已提交同 (demand_id, supply_id) 的记录，插入会撞
    唯一约束 uq_b2b_match：此时回滚保留先到者的结果——匹配是确定性规则，
    并发请求算出的集合等价，串行语义（后写覆盖）由下一次匹配达成。
    返回 False 表示撞唯一约束、本请求的替换已整体回滚。
    """
    db.execute(delete(B2bMatch).where(B2bMatch.demand_id == demand_id))
    for match in matches:
        db.add(match)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def list_matches(db: Session, demand_id: int) -> list[B2bMatch]:
    stmt = (
        select(B2bMatch)
        .where(B2bMatch.demand_id == demand_id)
        .order_by(B2bMatch.score.desc(), B2bMatch.supply_id.asc())
    )
    return list(db.scalars(stmt).all())

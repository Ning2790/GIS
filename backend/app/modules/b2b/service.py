"""b2b 业务逻辑层。

需求 2.4：农户 ↔ 企业供需信息撮合，**平台只提供信息服务、不做交易**。
匹配为确定性规则：品类必须一致；基础 60 分 + 地区一致 20 分 + 数量满足 20 分。
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core import pagination
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageQuery
from app.modules.b2b import repository
from app.modules.b2b.models import B2bDemand, B2bMatch, B2bStatus, B2bSupply
from app.modules.users.models import User

MATCH_LIMIT = 10


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def create_supply(
    db: Session,
    user: User,
    *,
    title: str,
    category: str,
    region: str,
    quantity: float,
    unit: str = "吨",
    price_expect: float | None = None,
    description: str = "",
) -> B2bSupply:
    supply = B2bSupply(
        user_id=user.id,
        title=title,
        category=category,
        region=region,
        quantity=_to_decimal(quantity),
        unit=unit,
        price_expect=_to_decimal(price_expect) if price_expect is not None else None,
        description=description,
    )
    created = repository.create_supply(db, supply)
    db.commit()
    return created


def create_demand(
    db: Session,
    user: User,
    *,
    title: str,
    category: str,
    region: str,
    quantity: float,
    unit: str = "吨",
    price_expect: float | None = None,
    description: str = "",
) -> B2bDemand:
    demand = B2bDemand(
        user_id=user.id,
        title=title,
        category=category,
        region=region,
        quantity=_to_decimal(quantity),
        unit=unit,
        price_expect=_to_decimal(price_expect) if price_expect is not None else None,
        description=description,
    )
    created = repository.create_demand(db, demand)
    db.commit()
    return created


def list_supplies(
    db: Session,
    page: PageQuery,
    *,
    category: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
) -> tuple[list[B2bSupply], int]:
    stmt = repository.supply_list_query(category=category, region=region, keyword=keyword)
    return pagination.paginate(db, stmt, page)


def get_supply_detail(db: Session, supply_id: int) -> B2bSupply:
    supply = repository.get_supply(db, supply_id)
    if supply is None:
        raise NotFoundError("供给信息不存在")
    return supply


def close_supply(db: Session, user: User, supply_id: int) -> B2bSupply:
    supply = get_supply_detail(db, supply_id)
    if supply.user_id != user.id:
        raise ForbiddenError("只有发布者可以关闭该信息")
    if supply.status == B2bStatus.CLOSED:
        raise ConflictError("该信息已关闭")
    supply.status = B2bStatus.CLOSED
    saved = repository.save_supply(db, supply)
    db.commit()
    return saved


def list_demands(
    db: Session,
    page: PageQuery,
    *,
    category: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
) -> tuple[list[B2bDemand], int]:
    stmt = repository.demand_list_query(category=category, region=region, keyword=keyword)
    return pagination.paginate(db, stmt, page)


def get_demand_detail(db: Session, demand_id: int) -> B2bDemand:
    demand = repository.get_demand(db, demand_id)
    if demand is None:
        raise NotFoundError("需求信息不存在")
    return demand


def close_demand(db: Session, user: User, demand_id: int) -> B2bDemand:
    demand = get_demand_detail(db, demand_id)
    if demand.user_id != user.id:
        raise ForbiddenError("只有发布者可以关闭该信息")
    if demand.status == B2bStatus.CLOSED:
        raise ConflictError("该信息已关闭")
    demand.status = B2bStatus.CLOSED
    saved = repository.save_demand(db, demand)
    db.commit()
    return saved


def _require_owner(user: User, demand: B2bDemand) -> None:
    if demand.user_id != user.id:
        raise ForbiddenError("只有需求发布者可以查看 / 发起匹配")


def match_demand(
    db: Session, user: User, demand_id: int
) -> tuple[B2bDemand, list[B2bMatch], dict[int, B2bSupply]]:
    """对需求跑一次规则匹配并落库（全量替换该需求的匹配记录）。"""
    demand = get_demand_detail(db, demand_id)
    _require_owner(user, demand)
    if demand.status != B2bStatus.OPEN:
        raise ConflictError("需求已关闭，不能发起匹配")

    candidates = list(db.scalars(repository.open_supplies_query(category=demand.category)).all())
    scored: list[tuple[int, B2bSupply]] = []
    for supply in candidates:
        score = 60
        if supply.region == demand.region:
            score += 20
        if supply.quantity >= demand.quantity:
            score += 20
        scored.append((score, supply))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    top = scored[:MATCH_LIMIT]

    # 撞唯一约束时 replace_matches 已把本次替换整体回滚（保留先到者的结果），
    # 此处的 commit 两种情况都安全：赢则落库，输则空提交。
    repository.replace_matches(
        db,
        demand.id,
        [B2bMatch(demand_id=demand.id, supply_id=supply.id, score=score) for score, supply in top],
    )
    db.commit()
    matches = repository.list_matches(db, demand.id)
    supplies = repository.get_supplies_by_ids(db, [match.supply_id for match in matches])
    return demand, matches, supplies


def list_demand_matches(
    db: Session, user: User, demand_id: int
) -> tuple[B2bDemand, list[B2bMatch], dict[int, B2bSupply]]:
    """查看某需求已有的匹配记录（仅发布者）。"""
    demand = get_demand_detail(db, demand_id)
    _require_owner(user, demand)
    matches = repository.list_matches(db, demand.id)
    supplies = repository.get_supplies_by_ids(db, [match.supply_id for match in matches])
    return demand, matches, supplies

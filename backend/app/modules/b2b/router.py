"""b2b 模块路由：供需信息与规则匹配（需求 2.4，浏览公开、发布与匹配需资质）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.b2b import service
from app.modules.b2b.models import B2bDemand, B2bMatch, B2bSupply
from app.modules.b2b.schemas import (
    B2bDemandPublic,
    B2bMatchItem,
    B2bMatchResult,
    B2bSupplyPublic,
    DemandCreateRequest,
    SupplyCreateRequest,
)
from app.modules.users.models import User

router = APIRouter(prefix="/b2b", tags=["b2b"])

# 发布需商户 / 企业资质（写法见 app/api/deps.py 的 require_roles）。
PublisherUser = Annotated[User, Depends(require_roles("merchant", "enterprise"))]


def _match_result(
    demand: B2bDemand, matches: list[B2bMatch], supplies: dict[int, B2bSupply]
) -> dict:
    items = []
    for match in matches:
        supply = supplies.get(match.supply_id)
        if supply is None:
            continue
        items.append(B2bMatchItem(score=match.score, supply=B2bSupplyPublic.model_validate(supply)))
    data = B2bMatchResult(
        demand=B2bDemandPublic.model_validate(demand),
        matches=items,
    )
    return data.model_dump(mode="json")


# ---------- 供给 ----------


@router.post("/supplies", summary="发布供给信息（商户 / 企业）")
def create_supply(payload: SupplyCreateRequest, db: DbSession, publisher: PublisherUser) -> dict:
    supply = service.create_supply(
        db,
        publisher,
        title=payload.title,
        category=payload.category,
        region=payload.region,
        quantity=payload.quantity,
        unit=payload.unit,
        price_expect=payload.price_expect,
        description=payload.description,
    )
    return ok(B2bSupplyPublic.model_validate(supply).model_dump(mode="json"), msg="已发布")


@router.get("/supplies", summary="供给列表（公开，仅开放中）")
def list_supplies(
    db: DbSession,
    page: PageParams,
    category: Annotated[str | None, Query(max_length=64, description="按品类过滤")] = None,
    region: Annotated[str | None, Query(max_length=64, description="按地区过滤")] = None,
    keyword: Annotated[
        str | None, Query(max_length=64, description="按标题 / 品类模糊搜索")
    ] = None,
) -> dict:
    rows, total = service.list_supplies(db, page, category=category, region=region, keyword=keyword)
    items = [B2bSupplyPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/supplies/{supply_id}", summary="供给详情（公开）")
def get_supply(supply_id: int, db: DbSession) -> dict:
    supply = service.get_supply_detail(db, supply_id)
    return ok(B2bSupplyPublic.model_validate(supply).model_dump(mode="json"))


@router.post("/supplies/{supply_id}/close", summary="关闭供给信息（发布者）")
def close_supply(supply_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    supply = service.close_supply(db, current_user, supply_id)
    return ok(B2bSupplyPublic.model_validate(supply).model_dump(mode="json"), msg="已关闭")


# ---------- 需求 ----------


@router.post("/demands", summary="发布需求信息（商户 / 企业）")
def create_demand(payload: DemandCreateRequest, db: DbSession, publisher: PublisherUser) -> dict:
    demand = service.create_demand(
        db,
        publisher,
        title=payload.title,
        category=payload.category,
        region=payload.region,
        quantity=payload.quantity,
        unit=payload.unit,
        price_expect=payload.price_expect,
        description=payload.description,
    )
    return ok(B2bDemandPublic.model_validate(demand).model_dump(mode="json"), msg="已发布")


@router.get("/demands", summary="需求列表（公开，仅开放中）")
def list_demands(
    db: DbSession,
    page: PageParams,
    category: Annotated[str | None, Query(max_length=64, description="按品类过滤")] = None,
    region: Annotated[str | None, Query(max_length=64, description="按地区过滤")] = None,
    keyword: Annotated[
        str | None, Query(max_length=64, description="按标题 / 品类模糊搜索")
    ] = None,
) -> dict:
    rows, total = service.list_demands(db, page, category=category, region=region, keyword=keyword)
    items = [B2bDemandPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/demands/{demand_id}", summary="需求详情（公开）")
def get_demand(demand_id: int, db: DbSession) -> dict:
    demand = service.get_demand_detail(db, demand_id)
    return ok(B2bDemandPublic.model_validate(demand).model_dump(mode="json"))


@router.post("/demands/{demand_id}/close", summary="关闭需求信息（发布者）")
def close_demand(demand_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    demand = service.close_demand(db, current_user, demand_id)
    return ok(B2bDemandPublic.model_validate(demand).model_dump(mode="json"), msg="已关闭")


# ---------- 匹配（仅信息撮合，不含交易） ----------


@router.post("/demands/{demand_id}/match", summary="发起规则匹配（需求发布者）")
def match_demand(demand_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    demand, matches, supplies = service.match_demand(db, current_user, demand_id)
    return ok(_match_result(demand, matches, supplies), msg="匹配完成")


@router.get("/demands/{demand_id}/matches", summary="查看匹配记录（需求发布者）")
def list_matches(demand_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    demand, matches, supplies = service.list_demand_matches(db, current_user, demand_id)
    return ok(_match_result(demand, matches, supplies))

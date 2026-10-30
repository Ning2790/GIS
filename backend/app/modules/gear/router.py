"""gear 模块路由：环境快照与装备建议（需求 2.2，公开接口）。"""

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.gear import service
from app.modules.gear.schemas import GearAdvicePublic, WeatherSnapshotPublic

router = APIRouter(prefix="/gear", tags=["gear"])


@router.get("/snapshots", summary="环境快照列表（公开）")
def list_snapshots(
    db: DbSession,
    page: PageParams,
    city: Annotated[str | None, Query(max_length=64, description="按城市 / 州过滤")] = None,
    date_from: Annotated[date | None, Query(description="起始日期")] = None,
    date_to: Annotated[date | None, Query(description="结束日期")] = None,
) -> dict:
    rows, total = service.list_snapshots(db, page, city=city, date_from=date_from, date_to=date_to)
    items = [WeatherSnapshotPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/advice", summary="装备建议（公开，按城市 / 日期）")
def get_advice(
    db: DbSession,
    city: Annotated[str, Query(max_length=64, description="城市 / 州")],
    date_: Annotated[date | None, Query(alias="date", description="出行日期，默认今天")] = None,
) -> dict:
    snapshot, recommendation = service.get_advice(db, city=city, day=date_)
    data = GearAdvicePublic(
        city=city,
        date=snapshot.snapshot_date,
        snapshot=WeatherSnapshotPublic.model_validate(snapshot),
        items=json.loads(recommendation.items),
        notes=recommendation.notes,
    )
    return ok(data.model_dump(mode="json"))

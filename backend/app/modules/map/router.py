"""map 模块路由：三图底图配置与点位查询（需求 2.1）。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.response import ok
from app.modules.map import service
from app.modules.map.schemas import MapLayerPublic, MapPointPublic

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/config", summary="底图配置（卫星 / 行政 / 地形，公开）")
def get_config() -> dict:
    layers = [MapLayerPublic(**layer) for layer in service.list_layers()]
    return ok(
        {
            "layers": [layer.model_dump(mode="json") for layer in layers],
            "default": service.DEFAULT_LAYER,
        }
    )


@router.get("/points", summary="点位查询（公开，可按视野 bbox 过滤）")
def list_points(
    db: DbSession,
    bbox: Annotated[str | None, Query(description="视野范围 minLng,minLat,maxLng,maxLat")] = None,
) -> dict:
    points = service.list_points(db, bbox=bbox)
    items = [MapPointPublic.model_validate(point).model_dump(mode="json") for point in points]
    return ok({"points": items, "total": len(items)})

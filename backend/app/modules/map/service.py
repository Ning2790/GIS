"""map 业务逻辑层。

三图底图配置由平台维护（前端据此加载瓦片）；点位数据来自 travel 模块的景点
（跨模块只走对方 service）。本模块无自有数据表。
"""

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.modules.travel import service as travel_service
from app.modules.travel.models import Attraction

# 免 key 的瓦片源（前端直接把 url_template 交给地图库加载）。
# 如需天地图等带 key 的服务，替换这里即可，不动接口形状。
LAYERS: list[dict[str, str]] = [
    {
        "key": "satellite",
        "name": "卫星影像",
        "url_template": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attribution": "Esri World Imagery",
    },
    {
        "key": "street",
        "name": "行政底图",
        "url_template": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
    },
    {
        "key": "terrain",
        "name": "地形",
        "url_template": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenTopoMap (CC-BY-SA)",
    },
]

DEFAULT_LAYER = "street"


def list_layers() -> list[dict[str, str]]:
    return LAYERS


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    """解析 bbox（minLng,minLat,maxLng,maxLat），非法时抛业务错误。"""
    parts = raw.split(",")
    if len(parts) != 4:
        raise BadRequestError("bbox 格式应为 minLng,minLat,maxLng,maxLat")
    try:
        min_lng, min_lat, max_lng, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise BadRequestError("bbox 必须是四个数字") from exc
    in_range = (
        -180 <= min_lng <= 180
        and -180 <= max_lng <= 180
        and -90 <= min_lat <= 90
        and -90 <= max_lat <= 90
    )
    if not in_range:
        raise BadRequestError("bbox 的取值范围不合法")
    if min_lng >= max_lng or min_lat >= max_lat:
        raise BadRequestError("bbox 需要满足 minLng < maxLng 且 minLat < maxLat")
    return min_lng, min_lat, max_lng, max_lat


def list_points(db: Session, *, bbox: str | None = None) -> list[Attraction]:
    """点位查询：可按视野 bbox 过滤（公开）。"""
    parsed = parse_bbox(bbox) if bbox else None
    return travel_service.list_attraction_points(db, bbox=parsed)

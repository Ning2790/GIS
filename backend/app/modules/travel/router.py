"""travel 模块路由：景点与门票（公开）、行程规划（登录用户）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core import cache
from app.core.config import get_settings
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.travel import service
from app.modules.travel.models import Attraction, Itinerary, ItineraryStop, Route, RouteStop
from app.modules.travel.schemas import (
    AttractionDetail,
    AttractionPublic,
    ItineraryDetail,
    ItineraryGenerateRequest,
    ItineraryPublic,
    ItineraryStopPublic,
    ItineraryStopsReplaceRequest,
    RouteDetail,
    RoutePublic,
    RouteSaveRequest,
    RouteStopPublic,
    TicketPublic,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/travel", tags=["travel"])

# 运营后台专用（路线维护仅管理员）
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("/attractions", summary="景点列表（公开）")
def list_attractions(
    db: DbSession,
    page: PageParams,
    city: Annotated[str | None, Query(max_length=64, description="按城市过滤")] = None,
    keyword: Annotated[
        str | None, Query(max_length=64, description="按名称 / 城市模糊搜索")
    ] = None,
    near: Annotated[
        str | None, Query(description="按距离排序：lng,lat（距离由计算核心给出）")
    ] = None,
) -> dict:
    def _payload() -> dict:
        rows, total, distances = service.list_attractions(
            db, page, city=city, keyword=keyword, near=near
        )
        items = []
        for row in rows:
            data = AttractionPublic.model_validate(row).model_dump(mode="json")
            if distances is not None:
                distance = distances.get(row.id)
                data["distance_km"] = round(distance, 1) if distance is not None else None
            items.append(data)
        return ok(page_data(items, total, page))

    if near is None:
        # 热点：标准分页列表按（城市 / 关键词 / 页码）缓存 60s（P1 承载能力）；
        # near 距离排序随请求坐标变化，不缓存。
        key_parts = f"{city or '-'}:{keyword or '-'}:{page.page}:{page.page_size}"
        return cache.cached(
            "travel:attractions", key_parts, get_settings().cache_ttl_seconds, _payload
        )
    return _payload()


@router.get("/attractions/{attraction_id}", summary="景点详情（含票种，公开）")
def get_attraction(attraction_id: int, db: DbSession) -> dict:
    attraction, tickets = service.get_attraction_detail(db, attraction_id)
    data = AttractionDetail(
        **AttractionPublic.model_validate(attraction).model_dump(),
        tickets=[TicketPublic.model_validate(ticket) for ticket in tickets],
    ).model_dump(mode="json")
    return ok(data)


def _stop_public(stop: ItineraryStop, attractions: dict[int, Attraction]) -> ItineraryStopPublic:
    attraction = attractions.get(stop.attraction_id)
    return ItineraryStopPublic(
        id=stop.id,
        attraction_id=stop.attraction_id,
        attraction_name=attraction.name if attraction else None,
        day=stop.day,
        position=stop.position,
        note=stop.note,
    )


def _itinerary_detail_public(
    itinerary: Itinerary,
    stops: list[ItineraryStop],
    attractions: dict[int, Attraction],
) -> dict:
    data = ItineraryDetail(
        **ItineraryPublic.model_validate(itinerary).model_dump(),
        stops=[_stop_public(stop, attractions) for stop in stops],
        total_distance_km=_rounded_distance(service.total_distance_km(stops, attractions)),
    )
    return data.model_dump(mode="json")


@router.get("/routes", summary="预设路线列表（公开）")
def list_routes(
    db: DbSession,
    page: PageParams,
    theme: Annotated[str | None, Query(max_length=32, description="按主题过滤")] = None,
) -> dict:
    def _payload() -> dict:
        rows, total, counts = service.list_routes(db, page, theme=theme)
        items = []
        for row in rows:
            data = RoutePublic.model_validate(row).model_dump(mode="json")
            data["stop_count"] = counts.get(row.id, 0)
            items.append(data)
        return ok(page_data(items, total, page))

    # 热点：与景点列表同样按（主题 / 页码）缓存 60s（P1 承载能力）
    key_parts = f"{theme or '-'}:{page.page}:{page.page_size}"
    return cache.cached("travel:routes", key_parts, get_settings().cache_ttl_seconds, _payload)


def _route_stop_public(stop: RouteStop, attractions: dict[int, Attraction]) -> RouteStopPublic:
    attraction = attractions.get(stop.attraction_id)
    return RouteStopPublic(
        id=stop.id,
        attraction_id=stop.attraction_id,
        attraction_name=attraction.name if attraction else None,
        city=attraction.city if attraction else None,
        latitude=attraction.latitude if attraction else None,
        longitude=attraction.longitude if attraction else None,
        day=stop.day,
        position=stop.position,
        note=stop.note,
    )


def _route_detail_public(
    route: Route,
    stops: list[RouteStop],
    attractions: dict[int, Attraction],
) -> dict:
    base = RoutePublic.model_validate(route).model_dump()
    # 列表接口已注入 stop_count；详情 / 新建 / 更新响应同样要与 stops 一致
    base["stop_count"] = len(stops)
    data = RouteDetail(
        **base,
        stops=[_route_stop_public(stop, attractions) for stop in stops],
        total_distance_km=_rounded_distance(service.total_distance_km(stops, attractions)),
    )
    return data.model_dump(mode="json")


@router.get("/routes/{route_id}", summary="预设路线详情（含停靠点，公开）")
def get_route(route_id: int, db: DbSession) -> dict:
    route, stops, attractions = service.get_route_detail(db, route_id)
    return ok(_route_detail_public(route, stops, attractions))


def _rounded_distance(distance: float | None) -> float | None:
    """全程里程保留 1 位小数（与景点列表 distance_km 口径一致）；缺坐标时保持 None。"""
    return round(distance, 1) if distance is not None else None


def _route_items(payload: RouteSaveRequest) -> list[tuple[int, int, str | None]]:
    return [(item.attraction_id, item.day, item.note) for item in payload.stops]


@router.post("/routes", summary="新建预设路线（管理员 / 运营）")
def create_route(payload: RouteSaveRequest, db: DbSession, admin: AdminUser) -> dict:
    route = service.create_route(
        db,
        admin,
        name=payload.name,
        theme=payload.theme,
        days=payload.days,
        budget=payload.budget,
        description=payload.description,
        items=_route_items(payload),
    )
    route, stops, attractions = service.get_route_detail(db, route.id)
    return ok(_route_detail_public(route, stops, attractions), msg="路线已创建")


@router.put("/routes/{route_id}", summary="更新预设路线（全量，含停靠点；管理员）")
def update_route(route_id: int, payload: RouteSaveRequest, db: DbSession, admin: AdminUser) -> dict:
    service.update_route(
        db,
        admin,
        route_id,
        name=payload.name,
        theme=payload.theme,
        days=payload.days,
        budget=payload.budget,
        description=payload.description,
        items=_route_items(payload),
    )
    route, stops, attractions = service.get_route_detail(db, route_id)
    return ok(_route_detail_public(route, stops, attractions), msg="路线已保存")


@router.delete("/routes/{route_id}", summary="删除预设路线（管理员）")
def delete_route(route_id: int, db: DbSession, admin: AdminUser) -> dict:
    service.delete_route(db, admin, route_id)
    return ok(None, msg="路线已删除")


@router.post("/routes/{route_id}/apply", summary="套用预设路线为我的行程（登录用户）")
def apply_route(route_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    itinerary = service.apply_route(db, current_user, route_id)
    itinerary, stops, attractions = service.get_itinerary_detail(db, itinerary.id, current_user)
    return ok(_itinerary_detail_public(itinerary, stops, attractions), msg="已套用为我的行程")


@router.post("/itineraries", summary="生成个性化行程（AI，登录用户）")
def generate_itinerary(
    payload: ItineraryGenerateRequest, db: DbSession, current_user: CurrentUser
) -> dict:
    itinerary = service.generate_itinerary(
        db,
        current_user,
        days=payload.days,
        budget=payload.budget,
        preferences=payload.preferences,
        fitness=payload.fitness,
    )
    itinerary, stops, attractions = service.get_itinerary_detail(db, itinerary.id, current_user)
    return ok(_itinerary_detail_public(itinerary, stops, attractions), msg="行程已生成")


@router.get("/itineraries", summary="我的行程列表")
def list_my_itineraries(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_my_itineraries(db, current_user, page)
    items = [ItineraryPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/itineraries/{itinerary_id}", summary="行程详情（含停靠点）")
def get_itinerary(itinerary_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    itinerary, stops, attractions = service.get_itinerary_detail(db, itinerary_id, current_user)
    return ok(_itinerary_detail_public(itinerary, stops, attractions))


@router.put(
    "/itineraries/{itinerary_id}/stops",
    summary="替换行程停靠点（增 / 删 / 排序一次完成）",
)
def replace_stops(
    itinerary_id: int,
    payload: ItineraryStopsReplaceRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    service.replace_itinerary_stops(
        db,
        itinerary_id,
        current_user,
        [(item.attraction_id, item.day, item.note) for item in payload.stops],
    )
    itinerary, stops, attractions = service.get_itinerary_detail(db, itinerary_id, current_user)
    return ok(_itinerary_detail_public(itinerary, stops, attractions), msg="已保存")


@router.delete("/itineraries/{itinerary_id}", summary="删除行程")
def delete_itinerary(itinerary_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    service.delete_itinerary(db, itinerary_id, current_user)
    return ok(None, msg="已删除")

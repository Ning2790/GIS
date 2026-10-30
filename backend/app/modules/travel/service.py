"""travel 业务逻辑层。

跨模块调用只能走本模块 service，禁止其他模块 import 本模块 repository / models。
"""

from sqlalchemy.orm import Session

from app.core import cache, compute, llm, pagination
from app.core.errors import BadRequestError, NotFoundError
from app.core.pagination import PageQuery
from app.modules.admin import service as admin_service
from app.modules.travel import repository
from app.modules.travel.models import (
    Attraction,
    Itinerary,
    ItineraryStop,
    Route,
    RouteStop,
    Ticket,
)
from app.modules.users.models import User, UserRole


def parse_near(raw: str) -> tuple[float, float]:
    """解析 near（lng,lat），非法时抛业务错误。"""
    parts = raw.split(",")
    if len(parts) != 2:
        raise BadRequestError("near 格式应为 lng,lat")
    try:
        lng, lat = (float(part) for part in parts)
    except ValueError as exc:
        raise BadRequestError("near 必须是两个数字") from exc
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise BadRequestError("near 的取值范围不合法")
    return lng, lat


def list_attractions(
    db: Session,
    page: PageQuery,
    *,
    city: str | None = None,
    keyword: str | None = None,
    near: str | None = None,
) -> tuple[list[Attraction], int, dict[int, float | None] | None]:
    """景点列表（分页），返回 (当页景点, 总数, {景点 id: 距离 km} 或 None)。

    传 near（lng,lat）时：按直线距离升序排序（距离计算走计算核心封装
    app/core/compute.py），距离在内存中计算并分页，无坐标的景点排在最后；
    不传 near 时走标准分页，第三个返回值为 None。
    """
    stmt = repository.attraction_list_query(city=city, keyword=keyword)
    if near is None:
        rows, total = pagination.paginate(db, stmt, page)
        return rows, total, None

    lng, lat = parse_near(near)
    candidates = list(db.scalars(stmt).all())
    ranked: list[tuple[float | None, Attraction]] = []
    for attraction in candidates:
        distance: float | None = None
        if attraction.latitude is not None and attraction.longitude is not None:
            distance = compute.haversine_km(lat, lng, attraction.latitude, attraction.longitude)
        ranked.append((distance, attraction))
    ranked.sort(key=lambda item: (item[0] is None, item[0] or 0.0, item[1].id))

    start = (page.page - 1) * page.page_size
    page_rows = [attraction for _distance, attraction in ranked[start : start + page.page_size]]
    distances = {attraction.id: distance for distance, attraction in ranked}
    return page_rows, len(ranked), distances


def get_attraction_detail(db: Session, attraction_id: int) -> tuple[Attraction, list[Ticket]]:
    """景点详情（含票种）。"""
    attraction = repository.get_attraction(db, attraction_id)
    if attraction is None:
        raise NotFoundError("景点不存在")
    return attraction, repository.list_tickets(db, attraction.id)


_FALLBACK_RISK_NOTES = (
    "高原地区注意防晒防寒、多饮水；初到 1-2 天避免剧烈运动，"
    "如出现明显头痛、胸闷等高原反应请及时休息或就医。"
)


def _pick_candidates(
    all_attractions: list[Attraction], preferences: str, limit: int
) -> list[Attraction]:
    """确定性候选排序：按偏好相关性打分降序（同分按 id 升序），取前 limit 个。

    打分为偏好匹配加权（名称 / 城市命中 + 覆盖度），计算下沉到 C++ 计算核心
    （app/core/compute.py 封装，未编译时自动回退等价 Python 实现）。
    mock 阶段的选点策略；接入真实模型后可改为由模型直接产出结构化行程（改这一处）。
    """
    keyword = preferences.strip()
    scores = compute.planning_scores(
        [attraction.name for attraction in all_attractions],
        [attraction.city for attraction in all_attractions],
        keyword,
    )
    ranked = sorted(
        zip(scores, all_attractions, strict=True), key=lambda item: (-item[0], item[1].id)
    )
    return [attraction for _score, attraction in ranked[:limit]]


def generate_itinerary(
    db: Session,
    user: User,
    *,
    days: int,
    budget: float | None = None,
    preferences: str = "",
    fitness: str | None = None,
) -> Itinerary:
    """生成个性化行程：确定性选点排程（每天 2 个）+ 模型生成风险提示（失败有兜底）。"""
    candidates = _pick_candidates(
        repository.list_attractions_for_planning(db), preferences, days * 2
    )
    # 模型调用放在事务外：外部调用不应占着数据库连接与写锁（mock 很快，真实模型可能数秒）
    try:
        notes = llm.chat(
            [
                {"role": "system", "content": "你是青海旅游行程规划助手。"},
                {
                    "role": "user",
                    "content": (
                        f"为一位游客规划 {days} 天行程（预算 {budget or '不限'}，"
                        f"偏好：{preferences or '无'}，体力：{fitness or '未说明'}），"
                        "请用一两句话给出高原旅行风险提示。"
                    ),
                },
            ]
        )
    except Exception:  # 模型不可用时用兜底文案，不阻断生成
        notes = _FALLBACK_RISK_NOTES

    itinerary = Itinerary(
        user_id=user.id,
        title=f"{days} 天青海行程",
        days=days,
        budget=budget,
        preferences=preferences,
        fitness=fitness,
        risk_notes=notes,
    )
    created = repository.create_itinerary(db, itinerary)
    repository.replace_stops(
        db,
        created.id,
        [
            ItineraryStop(
                itinerary_id=created.id,
                attraction_id=attraction.id,
                day=index // 2 + 1,
                position=index % 2 + 1,
            )
            for index, attraction in enumerate(candidates)
        ],
    )
    db.commit()  # 行程、停靠点、风险提示同一事务落库（repository 只 flush）
    return created


def list_my_itineraries(db: Session, user: User, page: PageQuery) -> tuple[list[Itinerary], int]:
    """我的行程列表（分页）。"""
    return pagination.paginate(db, repository.itinerary_list_query(user.id), page)


def _get_visible_itinerary(db: Session, itinerary_id: int, user: User) -> Itinerary:
    """可见性：行程归属游客 / 管理员；其余按不存在处理，不泄漏。"""
    itinerary = repository.get_itinerary(db, itinerary_id)
    if itinerary is None or not (itinerary.user_id == user.id or user.role == UserRole.ADMIN):
        raise NotFoundError("行程不存在")
    return itinerary


def get_itinerary_detail(
    db: Session, itinerary_id: int, user: User
) -> tuple[Itinerary, list[ItineraryStop], dict[int, Attraction]]:
    """行程详情：返回 (行程, 停靠点, 景点映射)。"""
    itinerary = _get_visible_itinerary(db, itinerary_id, user)
    stops = repository.list_stops(db, itinerary.id)
    attractions = repository.get_attractions_by_ids(db, [stop.attraction_id for stop in stops])
    return itinerary, stops, attractions


def replace_itinerary_stops(
    db: Session,
    itinerary_id: int,
    user: User,
    items: list[tuple[int, int, str | None]],
) -> Itinerary:
    """全量替换停靠点：一次完成增 / 删 / 排序。

    position 是「同日内序号」（与生成时一致）：数组顺序决定同一天内的先后，
    跨天按 day 升序读取；day 不得超过行程天数。
    """
    itinerary = _get_visible_itinerary(db, itinerary_id, user)
    found = repository.get_attractions_by_ids(db, [item[0] for item in items])
    missing = [item[0] for item in items if item[0] not in found]
    if missing:
        raise NotFoundError(f"景点不存在：{missing[0]}")
    if any(day > itinerary.days for _attraction_id, day, _note in items):
        raise BadRequestError(f"停靠点天数不能超过行程天数（共 {itinerary.days} 天）")

    day_counters: dict[int, int] = {}
    stops: list[ItineraryStop] = []
    for attraction_id, day, note in items:
        day_counters[day] = day_counters.get(day, 0) + 1
        stops.append(
            ItineraryStop(
                itinerary_id=itinerary.id,
                attraction_id=attraction_id,
                day=day,
                position=day_counters[day],
                note=note,
            )
        )
    if not repository.replace_stops(db, itinerary.id, stops):
        # 锁不到行程行：校验后被并发删除的窗口，按不存在处理（未提交的改动随会话回滚）
        raise NotFoundError("行程不存在")
    db.commit()
    return itinerary


def delete_itinerary(db: Session, itinerary_id: int, user: User) -> None:
    itinerary = _get_visible_itinerary(db, itinerary_id, user)
    repository.delete_itinerary(db, itinerary)
    db.commit()


def total_distance_km(
    stops: list[ItineraryStop] | list[RouteStop], attractions: dict[int, Attraction]
) -> float | None:
    """停靠点全程里程（公里）：任一停靠点缺景点或坐标则返回 None（不做假数据）。

    距离计算走计算核心封装（app/core/compute.py，C++ 未编译时回退 Python）。
    """
    points: list[tuple[float, float]] = []
    for stop in stops:
        attraction = attractions.get(stop.attraction_id)
        if attraction is None or attraction.latitude is None or attraction.longitude is None:
            return None
        points.append((attraction.latitude, attraction.longitude))
    if len(points) < 2:
        return 0.0
    return compute.path_length_km(points)


def list_routes(
    db: Session, page: PageQuery, *, theme: str | None = None
) -> tuple[list[Route], int, dict[int, int]]:
    """预设路线列表（分页），返回 (当页路线, 总数, {路线 id: 停靠点数量})。"""
    rows, total = pagination.paginate(db, repository.route_list_query(theme=theme), page)
    counts = repository.stop_counts_by_route(db, [route.id for route in rows])
    return rows, total, counts


def _route_stops_from_items(
    db: Session, days: int, items: list[tuple[int, int, str | None]]
) -> list[RouteStop]:
    """校验并构造路线停靠点：景点必须存在、day 不超过天数；position 按数组顺序推导。"""
    found = repository.get_attractions_by_ids(db, [item[0] for item in items])
    missing = [item[0] for item in items if item[0] not in found]
    if missing:
        raise NotFoundError(f"景点不存在：{missing[0]}")
    if any(day > days for _attraction_id, day, _note in items):
        raise BadRequestError(f"停靠点天数不能超过路线天数（共 {days} 天）")
    day_counters: dict[int, int] = {}
    stops: list[RouteStop] = []
    for attraction_id, day, note in items:
        day_counters[day] = day_counters.get(day, 0) + 1
        stops.append(
            RouteStop(
                attraction_id=attraction_id,
                day=day,
                position=day_counters[day],
                note=note,
            )
        )
    return stops


def create_route(
    db: Session,
    actor: User,
    *,
    name: str,
    theme: str,
    days: int,
    budget: float | None,
    description: str,
    items: list[tuple[int, int, str | None]],
) -> Route:
    """新建预设路线（运营后台，管理员）：路线、停靠点与审计日志同一事务落库。"""
    route = Route(name=name, theme=theme, days=days, budget=budget, description=description)
    created = repository.create_route(db, route)
    stops = _route_stops_from_items(db, days, items)
    for stop in stops:
        stop.route_id = created.id
    repository.replace_route_stops(db, created.id, stops)
    admin_service.record_action(
        db,
        actor_id=actor.id,
        action=admin_service.ACTION_ROUTE_CREATE,
        target_type="route",
        target_id=created.id,
        detail=f"{actor.phone} 新建路线「{name}」（{days} 天 / {len(stops)} 个停靠点）",
        commit=False,  # 与路线写入同一事务
    )
    db.commit()
    cache.bump_version("travel:routes")
    return created


def update_route(
    db: Session,
    actor: User,
    route_id: int,
    *,
    name: str,
    theme: str,
    days: int,
    budget: float | None,
    description: str,
    items: list[tuple[int, int, str | None]],
) -> Route:
    """全量更新预设路线（含停靠点整体替换，运营后台用）。"""
    route = repository.get_route(db, route_id)
    if route is None:
        raise NotFoundError("预设路线不存在")
    stops = _route_stops_from_items(db, days, items)
    route.name = name
    route.theme = theme
    route.days = days
    route.budget = budget
    route.description = description
    saved = repository.save_route(db, route)
    for stop in stops:
        stop.route_id = saved.id
    repository.replace_route_stops(db, saved.id, stops)
    admin_service.record_action(
        db,
        actor_id=actor.id,
        action=admin_service.ACTION_ROUTE_UPDATE,
        target_type="route",
        target_id=saved.id,
        detail=f"{actor.phone} 更新路线「{name}」（{days} 天 / {len(stops)} 个停靠点）",
        commit=False,
    )
    db.commit()
    cache.bump_version("travel:routes")
    return saved


def delete_route(db: Session, actor: User, route_id: int) -> None:
    """删除预设路线（含停靠点）。"""
    route = repository.get_route(db, route_id)
    if route is None:
        raise NotFoundError("预设路线不存在")
    name = route.name
    repository.delete_route(db, route)
    admin_service.record_action(
        db,
        actor_id=actor.id,
        action=admin_service.ACTION_ROUTE_DELETE,
        target_type="route",
        target_id=route_id,
        detail=f"{actor.phone} 删除路线「{name}」",
        commit=False,
    )
    db.commit()
    cache.bump_version("travel:routes")


def get_route_detail(
    db: Session, route_id: int
) -> tuple[Route, list[RouteStop], dict[int, Attraction]]:
    """预设路线详情：返回 (路线, 停靠点, 景点映射)。"""
    route = repository.get_route(db, route_id)
    if route is None:
        raise NotFoundError("预设路线不存在")
    stops = repository.list_route_stops(db, route.id)
    attractions = repository.get_attractions_by_ids(db, [stop.attraction_id for stop in stops])
    return route, stops, attractions


def apply_route(db: Session, user: User, route_id: int) -> Itinerary:
    """把预设路线套用为「我的行程」（复制一份，之后互不影响）。

    风险提示直接用兜底文案：套用是确定性复制，不依赖模型可用性；
    stop 的 day / position 原样复制，后续用户可自由增删排序。
    """
    route, stops, _attractions = get_route_detail(db, route_id)
    itinerary = Itinerary(
        user_id=user.id,
        title=route.name,
        days=route.days,
        budget=route.budget,
        preferences=f"套用预设路线：{route.name}",
        risk_notes=_FALLBACK_RISK_NOTES,
    )
    created = repository.create_itinerary(db, itinerary)
    repository.replace_stops(
        db,
        created.id,
        [
            ItineraryStop(
                itinerary_id=created.id,
                attraction_id=stop.attraction_id,
                day=stop.day,
                position=stop.position,
                note=stop.note,
            )
            for stop in stops
        ],
    )
    db.commit()  # 行程与停靠点同一事务落库（repository 只 flush）
    return created


def list_attraction_points(
    db: Session, *, bbox: tuple[float, float, float, float] | None = None
) -> list[Attraction]:
    """点位查询（供 map 模块使用）：返回坐标齐全的景点，可按视野范围过滤。"""
    return list(db.scalars(repository.attraction_points_query(db, bbox=bbox)).all())

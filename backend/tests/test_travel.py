"""travel 模块：景点与行程测试。"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import compute
from app.db.session import SessionLocal
from app.modules.travel.models import Attraction, Route, RouteStop, Ticket


def _seed(
    name: str,
    city: str,
    *,
    ticket_price: float | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> int:
    """直接落库一个景点（可带一张门票 / 坐标），返回景点 id。"""
    with SessionLocal() as db:
        attraction = Attraction(
            name=name,
            city=city,
            description=f"{name} 简介",
            latitude=latitude,
            longitude=longitude,
        )
        db.add(attraction)
        db.flush()
        if ticket_price is not None:
            db.add(Ticket(attraction_id=attraction.id, name=f"{name}门票", price=ticket_price))
        db.commit()
        return attraction.id


def test_attractions_list_public_with_pagination(client: TestClient) -> None:
    _seed("测试景点甲", "测试市")
    _seed("测试景点乙", "测试市")

    # 公开接口：无需登录
    resp = client.get("/api/v1/travel/attractions?page=1&page_size=50")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["total"] >= 2
    assert set(data["items"][0]) >= {
        "id",
        "name",
        "city",
        "description",
        "latitude",
        "longitude",
        "cover_image",
        "created_at",
    }


def test_attractions_filters(client: TestClient) -> None:
    _seed("海北测试湖", "测试州甲")
    _seed("测试州乙景区", "测试州乙")

    resp = client.get("/api/v1/travel/attractions?city=测试州甲")
    items = resp.json()["data"]["items"]
    assert items
    assert all(item["city"] == "测试州甲" for item in items)

    resp = client.get("/api/v1/travel/attractions?keyword=测试州乙景区")
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["name"] == "测试州乙景区"


def test_attraction_detail_with_tickets(client: TestClient) -> None:
    attraction_id = _seed("测试景点丙", "测试市", ticket_price=88.5)

    resp = client.get(f"/api/v1/travel/attractions/{attraction_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == attraction_id
    assert data["name"] == "测试景点丙"
    assert len(data["tickets"]) == 1
    assert data["tickets"][0]["price"] == 88.5


def test_attraction_detail_missing_returns_404(client: TestClient) -> None:
    resp = client.get("/api/v1/travel/attractions/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40400


def _login_tourist(client: TestClient) -> str:
    """注册并登录一个游客，返回访问令牌。"""
    phone = "13" + str(uuid.uuid4().int)[:9]
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def test_itinerary_generation_and_detail(client: TestClient) -> None:
    _seed("测试规划景点甲", "测试市")
    _seed("测试规划景点乙", "测试市")
    _seed("测试规划景点丙", "测试市")

    # 未登录 401
    assert client.post("/api/v1/travel/itineraries", json={"days": 2}).status_code == 401

    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v1/travel/itineraries",
        json={"days": 2, "budget": 3000, "preferences": "测试规划景点乙", "fitness": "轻松"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["days"] == 2
    assert data["budget"] == 3000
    assert data["risk_notes"]

    stops = data["stops"]
    assert len(stops) == 4  # 每天 2 个
    assert stops[0]["attraction_name"] == "测试规划景点乙"  # 偏好中提到的景点优先
    assert {stop["day"] for stop in stops} == {1, 2}
    assert [stop["position"] for stop in stops] == [1, 2, 1, 2]

    # 详情与列表
    itinerary_id = data["id"]
    resp = client.get(f"/api/v1/travel/itineraries/{itinerary_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["stops"]) == 4
    resp = client.get("/api/v1/travel/itineraries?page=1&page_size=5", headers=headers)
    assert any(item["id"] == itinerary_id for item in resp.json()["data"]["items"])


def test_itinerary_stops_edit_and_ownership(client: TestClient) -> None:
    _seed("测试编辑景点甲", "测试市")
    _seed("测试编辑景点乙", "测试市")
    token_a = _login_tourist(client)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    resp = client.post(
        "/api/v1/travel/itineraries",
        json={"days": 1, "preferences": "测试编辑"},
        headers=headers_a,
    )
    itinerary_id = resp.json()["data"]["id"]
    stops = resp.json()["data"]["stops"]
    first, second = stops[0], stops[1]

    # 全量替换：换顺序 + 备注
    resp = client.put(
        f"/api/v1/travel/itineraries/{itinerary_id}/stops",
        json={
            "stops": [
                {"attraction_id": second["attraction_id"], "day": 1, "note": "先去乙"},
                {"attraction_id": first["attraction_id"], "day": 1},
            ]
        },
        headers=headers_a,
    )
    assert resp.status_code == 200, resp.text
    new_stops = resp.json()["data"]["stops"]
    assert [s["attraction_id"] for s in new_stops] == [
        second["attraction_id"],
        first["attraction_id"],
    ]
    assert [s["position"] for s in new_stops] == [1, 2]
    assert new_stops[0]["note"] == "先去乙"

    # 引用不存在的景点 → 404
    resp = client.put(
        f"/api/v1/travel/itineraries/{itinerary_id}/stops",
        json={"stops": [{"attraction_id": 999999, "day": 1}]},
        headers=headers_a,
    )
    assert resp.status_code == 404

    # 他人不可见 / 不可改 / 不可删
    token_b = _login_tourist(client)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    resp = client.get(f"/api/v1/travel/itineraries/{itinerary_id}", headers=headers_b)
    assert resp.status_code == 404
    resp = client.put(
        f"/api/v1/travel/itineraries/{itinerary_id}/stops",
        json={"stops": []},
        headers=headers_b,
    )
    assert resp.status_code == 404
    resp = client.delete(f"/api/v1/travel/itineraries/{itinerary_id}", headers=headers_b)
    assert resp.status_code == 404

    # 本人删除后 404
    resp = client.delete(f"/api/v1/travel/itineraries/{itinerary_id}", headers=headers_a)
    assert resp.status_code == 200
    resp = client.get(f"/api/v1/travel/itineraries/{itinerary_id}", headers=headers_a)
    assert resp.status_code == 404


def test_stop_day_bounds_and_position_semantics(client: TestClient) -> None:
    """day 不得超过行程天数；position 是「同日内序号」。"""
    _seed("测试日程景点甲", "测试市")
    _seed("测试日程景点乙", "测试市")
    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1 天行程塞进第 5 天 → 400
    resp = client.post(
        "/api/v1/travel/itineraries", json={"days": 1, "preferences": "测试日程"}, headers=headers
    )
    one_day = resp.json()["data"]
    resp = client.put(
        f"/api/v1/travel/itineraries/{one_day['id']}/stops",
        json={"stops": [{"attraction_id": one_day["stops"][0]["attraction_id"], "day": 5}]},
        headers=headers,
    )
    assert resp.status_code == 400

    # 跨天替换：读取顺序按 (day, position)，position 为同日内序号
    resp = client.post(
        "/api/v1/travel/itineraries", json={"days": 2, "preferences": "测试日程"}, headers=headers
    )
    data = resp.json()["data"]
    stop_a = data["stops"][0]["attraction_id"]
    stop_b = data["stops"][1]["attraction_id"]

    resp = client.put(
        f"/api/v1/travel/itineraries/{data['id']}/stops",
        json={
            "stops": [
                {"attraction_id": stop_a, "day": 2},
                {"attraction_id": stop_b, "day": 1},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    stops = resp.json()["data"]["stops"]
    assert [(s["day"], s["position"]) for s in stops] == [(1, 1), (2, 1)]
    assert stops[0]["attraction_id"] == stop_b


def _seed_route(
    name: str,
    *,
    theme: str = "环湖",
    days: int = 2,
    budget: float | None = 1000,
    stops: list[tuple[int, int, int, str | None]] | None = None,
) -> int:
    """直接落库一条预设路线（含停靠点），返回路线 id。

    stops 元素为 (attraction_id, day, position, note)。
    """
    with SessionLocal() as db:
        route = Route(
            name=name,
            theme=theme,
            days=days,
            budget=budget,
            description=f"{name} 简介",
        )
        db.add(route)
        db.flush()
        for attraction_id, day, position, note in stops or []:
            db.add(
                RouteStop(
                    route_id=route.id,
                    attraction_id=attraction_id,
                    day=day,
                    position=position,
                    note=note,
                )
            )
        db.commit()
        return route.id


def test_routes_list_and_detail_public(client: TestClient) -> None:
    """预设路线：列表 / 详情公开，含停靠点数量与景点信息。"""
    attraction_a = _seed("测试路线景点甲", "测试市", latitude=36.6, longitude=101.8)
    attraction_b = _seed("测试路线景点乙", "测试市")
    route_id = _seed_route(
        "测试环湖两日线",
        theme="测试主题",
        days=2,
        stops=[
            (attraction_a, 1, 1, "第一天上午"),
            (attraction_b, 2, 1, None),
        ],
    )

    # 公开接口：无需登录
    resp = client.get("/api/v1/travel/routes", params={"theme": "测试主题", "page_size": 50})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    item = next(row for row in data["items"] if row["id"] == route_id)
    assert item["stop_count"] == 2
    assert item["days"] == 2
    assert item["budget"] == 1000
    assert data["total"] == 1  # 主题过滤生效

    resp = client.get(f"/api/v1/travel/routes/{route_id}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["name"] == "测试环湖两日线"
    # 详情 / 新建 / 更新的 stop_count 必须与 stops 数量一致（此前恒为 0）
    assert detail["stop_count"] == len(detail["stops"]) == 2
    assert [(stop["day"], stop["position"]) for stop in detail["stops"]] == [(1, 1), (2, 1)]
    assert detail["stops"][0]["attraction_name"] == "测试路线景点甲"
    assert detail["stops"][0]["city"] == "测试市"
    assert detail["stops"][0]["latitude"] == 36.6
    assert detail["stops"][0]["note"] == "第一天上午"

    resp = client.get("/api/v1/travel/routes/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40400


def test_apply_route_creates_my_itinerary(client: TestClient) -> None:
    """套用预设路线：复制成我的行程（含停靠点），不影响路线本身；未登录 401。"""
    attraction_a = _seed("测试套用景点甲", "测试市")
    attraction_b = _seed("测试套用景点乙", "测试市")
    route_id = _seed_route(
        "测试套用路线",
        days=2,
        budget=1500,
        stops=[
            (attraction_a, 1, 1, "上午"),
            (attraction_b, 2, 1, None),
        ],
    )

    assert client.post(f"/api/v1/travel/routes/{route_id}/apply").status_code == 401

    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(f"/api/v1/travel/routes/{route_id}/apply", headers=headers)
    assert resp.status_code == 200, resp.text
    itinerary = resp.json()["data"]
    assert itinerary["title"] == "测试套用路线"
    assert itinerary["days"] == 2
    assert itinerary["budget"] == 1500
    assert itinerary["risk_notes"]
    assert [stop["attraction_id"] for stop in itinerary["stops"]] == [attraction_a, attraction_b]
    assert [(stop["day"], stop["position"]) for stop in itinerary["stops"]] == [(1, 1), (2, 1)]
    assert itinerary["stops"][0]["note"] == "上午"

    # 出现在「我的行程」里，路线停靠点未被改动
    resp = client.get("/api/v1/travel/itineraries", headers=headers)
    assert any(item["id"] == itinerary["id"] for item in resp.json()["data"]["items"])
    resp = client.get(f"/api/v1/travel/routes/{route_id}")
    assert len(resp.json()["data"]["stops"]) == 2

    # 不存在的路线 → 404
    resp = client.post("/api/v1/travel/routes/999999/apply", headers=headers)
    assert resp.status_code == 404


def test_keyword_wildcards_are_escaped(client: TestClient) -> None:
    """列表的 % / _ 应作为字面量搜索，不能当通配符命中全表。"""
    _seed("测试转义景点", "测试市")

    resp = client.get("/api/v1/travel/attractions", params={"keyword": "%"})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0

    resp = client.get("/api/v1/travel/attractions", params={"keyword": "测试转义景点"})
    assert resp.json()["data"]["total"] == 1


def test_attractions_near_sorting(client: TestClient) -> None:
    """near 参数：按距离升序排序并返回 distance_km（距离计算走计算核心封装）。"""
    _seed("测试近点", "测试市", latitude=36.60, longitude=101.80)
    _seed("测试远点", "测试市", latitude=36.90, longitude=100.20)

    resp = client.get(
        "/api/v1/travel/attractions", params={"near": "101.80,36.60", "page_size": 50}
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    by_name = {item["name"]: item for item in items}

    # 整体按距离升序；无坐标的排最后（其它用例也会在同一测试库播种带坐标景点）
    distances = [item["distance_km"] for item in items]
    numeric = [distance for distance in distances if distance is not None]
    assert numeric == sorted(numeric)
    assert distances[-1] is None
    assert by_name["测试近点"]["distance_km"] == 0.0
    assert by_name["测试远点"]["distance_km"] > 100
    assert items.index(by_name["测试近点"]) < items.index(by_name["测试远点"])

    # 非法 near → 400 信封
    resp = client.get("/api/v1/travel/attractions", params={"near": "abc"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 40000


def _admin_headers(client: TestClient) -> dict[str, str]:
    """创建（幂等）并登录测试管理员，返回请求头。"""
    from app.core.errors import ConflictError
    from app.modules.users import service as users_service

    with SessionLocal() as db:
        try:
            users_service.create_admin(db, phone="13700000002", password="admin123456")
        except ConflictError:
            pass
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13700000002", "password": "admin123456"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def test_route_admin_crud(client: TestClient) -> None:
    """运营后台：新建 / 全量更新 / 删除预设路线（仅管理员）。"""
    attraction_a = _seed("测试运营景点甲", "测试市")
    attraction_b = _seed("测试运营景点乙", "测试市")
    admin_headers = _admin_headers(client)

    # 非管理员不可维护（游客 403）
    token = _login_tourist(client)
    tourist_headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "测试运营路线",
        "theme": "测试主题",
        "days": 2,
        "budget": 500,
        "description": "运营创建的路线",
        "stops": [
            {"attraction_id": attraction_a, "day": 1, "note": "上午"},
            {"attraction_id": attraction_b, "day": 2},
        ],
    }
    assert client.post("/api/v1/travel/routes", json=payload).status_code == 401
    assert (
        client.post("/api/v1/travel/routes", json=payload, headers=tourist_headers).status_code
        == 403
    )

    # 管理员新建 → 详情带停靠点（position 按数组顺序推导）
    resp = client.post("/api/v1/travel/routes", json=payload, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    route = resp.json()["data"]
    route_id = route["id"]
    assert route["name"] == "测试运营路线"
    assert [(s["day"], s["position"]) for s in route["stops"]] == [(1, 1), (2, 1)]

    # 校验：不存在的景点 404；day 超过天数 400
    bad = dict(payload, stops=[{"attraction_id": 999999, "day": 1}])
    assert client.post("/api/v1/travel/routes", json=bad, headers=admin_headers).status_code == 404
    bad_day = dict(payload, days=1, stops=[{"attraction_id": attraction_a, "day": 2}])
    assert (
        client.post("/api/v1/travel/routes", json=bad_day, headers=admin_headers).status_code == 400
    )

    # 公开列表可见（缓存已 bump）
    listed = client.get("/api/v1/travel/routes", params={"theme": "测试主题", "page_size": 50})
    assert route_id in [item["id"] for item in listed.json()["data"]["items"]]

    # 全量更新：改名 / 改天数（压缩到 1 天）/ 停靠点重排
    updated = dict(
        payload,
        name="测试运营路线（改）",
        days=1,
        stops=[
            {"attraction_id": attraction_b, "day": 1, "note": "改后第一站"},
            {"attraction_id": attraction_a, "day": 1},
        ],
    )
    resp = client.put(f"/api/v1/travel/routes/{route_id}", json=updated, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "测试运营路线（改）"
    assert [(s["day"], s["position"], s["attraction_id"]) for s in data["stops"]] == [
        (1, 1, attraction_b),
        (1, 2, attraction_a),
    ]

    # 更新不存在的路线 404
    resp = client.put("/api/v1/travel/routes/999999", json=payload, headers=admin_headers)
    assert resp.status_code == 404

    # 删除 → 详情 404、列表不再返回
    assert (
        client.delete(f"/api/v1/travel/routes/{route_id}", headers=admin_headers).status_code == 200
    )
    assert client.get(f"/api/v1/travel/routes/{route_id}").status_code == 404
    listed = client.get("/api/v1/travel/routes", params={"theme": "测试主题", "page_size": 50})
    assert route_id not in [item["id"] for item in listed.json()["data"]["items"]]
    # 重复删除 404
    assert (
        client.delete(f"/api/v1/travel/routes/{route_id}", headers=admin_headers).status_code == 404
    )


def test_route_changes_are_audited(client: TestClient) -> None:
    """路线增删改写入审计日志（actor = 管理员，target_type=route），可按类型过滤。"""
    from sqlalchemy import func

    from app.modules.admin.models import AuditLog

    attraction_a = _seed("测试审计景点", "测试市")
    admin_headers = _admin_headers(client)
    admin_id = client.get("/api/v1/users/me", headers=admin_headers).json()["data"]["id"]
    # SQLite 删除后会复用最大 id，按「基线之后新增的审计行」判定，避免与其它用例串行
    with SessionLocal() as db:
        baseline = db.scalar(select(func.max(AuditLog.id))) or 0

    payload = {
        "name": "审计路线",
        "theme": "审计",
        "days": 1,
        "budget": 100,
        "description": "",
        "stops": [{"attraction_id": attraction_a, "day": 1}],
    }
    route_id = client.post("/api/v1/travel/routes", json=payload, headers=admin_headers).json()[
        "data"
    ]["id"]
    client.put(
        f"/api/v1/travel/routes/{route_id}",
        json={**payload, "name": "审计路线（改）"},
        headers=admin_headers,
    )
    client.delete(f"/api/v1/travel/routes/{route_id}", headers=admin_headers)

    with SessionLocal() as db:
        logs = db.scalars(
            select(AuditLog)
            .where(AuditLog.id > baseline, AuditLog.target_type == "route")
            .order_by(AuditLog.id.asc())
        ).all()
    assert [log.action for log in logs] == ["route.create", "route.update", "route.delete"]
    assert {log.target_id for log in logs} == {route_id}
    assert all(log.actor_id == admin_id for log in logs)
    assert "审计路线" in (logs[0].detail or "")

    # 管理员可按 target_type 过滤查到路线维度的记录
    resp = client.get(
        "/api/v1/admin/audit-logs?target_type=route&page_size=10", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert all(item["target_type"] == "route" for item in items) and items


def test_detail_includes_total_distance(client: TestClient) -> None:
    """路线 / 行程详情给出全程里程：停靠点都有坐标时计算，缺坐标则为 None。"""
    # 两个带坐标 + 一个无坐标的景点
    near = _seed("里程景点甲", "测试市", latitude=36.60, longitude=101.80)
    far = _seed("里程景点乙", "测试市", latitude=36.90, longitude=100.20)
    no_coord = _seed("里程景点丙", "测试市")

    admin_headers = _admin_headers(client)
    route_id = client.post(
        "/api/v1/travel/routes",
        json={
            "name": "里程路线",
            "theme": "测试",
            "days": 2,
            "budget": 0,
            "description": "",
            "stops": [
                {"attraction_id": near, "day": 1},
                {"attraction_id": far, "day": 2},
            ],
        },
        headers=admin_headers,
    ).json()["data"]["id"]

    detail = client.get(f"/api/v1/travel/routes/{route_id}").json()["data"]
    expected = compute.path_length_km([(36.60, 101.80), (36.90, 100.20)])
    assert detail["total_distance_km"] == pytest.approx(round(expected, 1), abs=0.05)
    assert detail["total_distance_km"] > 100  # 西宁到青海湖量级

    # 换成含无坐标停靠点的路线 → None（不猜假数据）
    route2 = client.post(
        "/api/v1/travel/routes",
        json={
            "name": "里程路线（缺坐标）",
            "theme": "测试",
            "days": 1,
            "budget": 0,
            "description": "",
            "stops": [
                {"attraction_id": near, "day": 1},
                {"attraction_id": no_coord, "day": 1},
            ],
        },
        headers=admin_headers,
    ).json()["data"]["id"]
    detail2 = client.get(f"/api/v1/travel/routes/{route2}").json()["data"]
    assert detail2["total_distance_km"] is None

    # 行程详情同样带里程（套用带坐标的路线）
    token = _login_tourist(client)
    itinerary = client.post(
        f"/api/v1/travel/routes/{route_id}/apply",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    assert itinerary["total_distance_km"] == pytest.approx(round(expected, 1), abs=0.05)

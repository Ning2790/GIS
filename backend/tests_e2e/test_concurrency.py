"""并发回归：复跑 2026-10-13 并发审计的全部场景。

每个用例对应 `docs/代码审计报告.md` 中一处已修复的并发缺陷：修复前这些
场景会返回 500 / 静默丢更新 / 重复数据，本套件把它们固化为可重复验证。

需要真实 PostgreSQL + Redis（见 conftest）；环境不满足时自动跳过。
数据均带 e2e 前缀，不影响其他功能。
"""

import uuid

import httpx
import pytest
from sqlalchemy import text

from tests_e2e.helpers import (
    PASSWORD,
    RECEIVER,
    create_product,
    login,
    register_merchant,
    register_tourist,
    run_concurrently,
    unique_phone,
    user_id_of,
)


def test_concurrent_idempotent_order(api: httpx.Client, db) -> None:
    """4 并发同幂等键下单：全部 200（重放同一订单）、只扣一次库存。"""
    merchant = register_merchant(api, db)
    mh = login(api, merchant)
    product = create_product(api, mh, stock=10)
    tourist = register_tourist(api)
    th = login(api, tourist)
    idem = f"e2e-idem-{uuid.uuid4().hex}"

    def fire(index: int) -> httpx.Response:
        return api.post(
            "/shop/orders",
            headers=th,
            json={"product_id": product["id"], "quantity": 1, "idem_key": idem, **RECEIVER},
        )

    results = run_concurrently(fire, 4)
    assert [r.status_code for r in results] == [200] * 4, [r.text for r in results]
    assert len({r.json()["data"]["id"] for r in results}) == 1
    assert api.get(f"/shop/products/{product['id']}").json()["data"]["stock"] == 9
    with db() as session:
        count = session.execute(
            text("SELECT count(*) FROM orders WHERE idem_key = :k"), {"k": idem}
        ).scalar_one()
    assert count == 1


def test_concurrent_last_stock(api: httpx.Client, db) -> None:
    """抢最后一件库存：1×200 + 1×409，无超卖。"""
    merchant = register_merchant(api, db)
    mh = login(api, merchant)
    product = create_product(api, mh, stock=1)
    buyers = [login(api, register_tourist(api)) for _ in range(2)]

    def fire(index: int) -> httpx.Response:
        return api.post(
            "/shop/orders",
            headers=buyers[index],
            json={
                "product_id": product["id"],
                "quantity": 1,
                "idem_key": f"e2e-grab-{uuid.uuid4().hex}",
                **RECEIVER,
            },
        )

    results = run_concurrently(fire, 2)
    assert sorted(r.status_code for r in results) == [200, 409]
    assert api.get(f"/shop/products/{product['id']}").json()["data"]["stock"] == 0


def test_concurrent_cart_add(api: httpx.Client, db) -> None:
    """购物车 4 并发各 +1：全部 200，数量精确累加为 4（不丢失更新）。"""
    merchant = register_merchant(api, db)
    mh = login(api, merchant)
    product = create_product(api, mh, stock=100)
    tourist = register_tourist(api)
    th = login(api, tourist)

    def fire(index: int) -> httpx.Response:
        return api.post(
            "/shop/cart/items",
            headers=th,
            json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        )

    results = run_concurrently(fire, 4)
    assert [r.status_code for r in results] == [200] * 4, [r.text for r in results]
    items = api.get("/shop/cart", headers=th).json()["data"]["items"]
    quantity = next(it["quantity"] for it in items if it["product_id"] == product["id"])
    assert quantity == 4


def test_concurrent_checkout_same_cart(api: httpx.Client, db) -> None:
    """同购物车不同幂等键 2 并发结算：1×200 + 1×409，不双下单、购物车清空。"""
    merchant = register_merchant(api, db)
    mh = login(api, merchant)
    product = create_product(api, mh, stock=100)
    tourist = register_tourist(api)
    th = login(api, tourist)
    uid = user_id_of(db, tourist)
    api.post(
        "/shop/cart/items",
        headers=th,
        json={"product_id": product["id"], "quantity": 2, **RECEIVER},
    )

    def fire(index: int) -> httpx.Response:
        return api.post(
            "/shop/cart/checkout",
            headers=th,
            json={"idem_key": f"e2e-co-{uuid.uuid4().hex}", **RECEIVER},
        )

    results = run_concurrently(fire, 2)
    assert sorted(r.status_code for r in results) == [200, 409]
    assert api.get("/shop/cart", headers=th).json()["data"]["items"] == []
    with db() as session:
        count = session.execute(
            text("SELECT count(*) FROM orders WHERE user_id = :u"), {"u": uid}
        ).scalar_one()
    assert count == 1  # 该用户本次测试只产生 1 个订单（并发结算被正确拒绝）


def test_concurrent_registration(api: httpx.Client) -> None:
    """同手机号 4 并发注册：1×200 + 3×409（唯一索引兜底，不再 500）。"""
    phone = unique_phone()

    def fire(index: int) -> httpx.Response:
        return api.post("/auth/register/tourist", json={"phone": phone, "password": PASSWORD})

    results = run_concurrently(fire, 4)
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409]


def test_concurrent_b2b_match(api: httpx.Client, db) -> None:
    """4 并发发起匹配：全部 200，匹配记录无重复。"""
    enterprise = register_merchant(api, db, role="enterprise")
    eh = login(api, enterprise)
    tag = uuid.uuid4().hex[:6]
    demand = api.post(
        "/b2b/demands",
        headers=eh,
        json={
            "title": f"e2e需求{tag}",
            "category": f"e2e品类{tag}",
            "region": "西宁市",
            "quantity": 10,
        },
    ).json()["data"]
    assert demand["id"]
    for i in range(2):
        resp = api.post(
            "/b2b/supplies",
            headers=eh,
            json={
                "title": f"e2e供给{tag}-{i}",
                "category": f"e2e品类{tag}",
                "region": "西宁市",
                "quantity": 20,
            },
        )
        assert resp.status_code == 200, resp.text

    def fire(index: int) -> httpx.Response:
        return api.post(f"/b2b/demands/{demand['id']}/match", headers=eh)

    results = run_concurrently(fire, 4)
    assert [r.status_code for r in results] == [200] * 4, [r.text for r in results]
    matches = api.get(f"/b2b/demands/{demand['id']}/matches", headers=eh).json()["data"]["matches"]
    assert len(matches) == 2  # 无重复匹配行
    with db() as session:
        count = session.execute(
            text("SELECT count(*) FROM b2b_matches WHERE demand_id = :d"), {"d": demand["id"]}
        ).scalar_one()
    assert count == 2


def test_concurrent_stops_replace(api: httpx.Client) -> None:
    """4 并发替换停靠点：全部 200，最终停靠点无重复。"""
    tourist = register_tourist(api)
    th = login(api, tourist)
    attractions = api.get("/travel/attractions", params={"page": 1, "page_size": 5}).json()["data"][
        "items"
    ]
    if len(attractions) < 3:
        pytest.skip("景点样例不足 3 个（先运行 scripts/seed_travel.py）")
    itinerary = api.post(
        "/travel/itineraries", headers=th, json={"days": 2, "preferences": "e2e"}
    ).json()["data"]
    body = {
        "stops": [
            {"attraction_id": attraction["id"], "day": 1 + index // 2, "note": None}
            for index, attraction in enumerate(attractions[:3])
        ]
    }

    def fire(index: int) -> httpx.Response:
        return api.put(f"/travel/itineraries/{itinerary['id']}/stops", headers=th, json=body)

    results = run_concurrently(fire, 4)
    assert [r.status_code for r in results] == [200] * 4, [r.text for r in results]
    stops = api.get(f"/travel/itineraries/{itinerary['id']}", headers=th).json()["data"]["stops"]
    assert len(stops) == 3

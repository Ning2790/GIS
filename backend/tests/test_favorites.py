"""收藏 / 浏览历史 / 首页推荐（增强项）测试。

覆盖：收藏幂等与权限、我的收藏列表、详情收藏态、浏览历史写入与去重、清空历史、
商户侧收藏数、推荐的两条路径（personal 兴趣打分 / popular 全站热度）。
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.shop import service
from app.modules.shop.models import Favorite, Product, ProductStatus, ProductView
from app.modules.users.models import User, UserStatus


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录，返回 (phone, token, user_id)。商户跳过审核（同 test_shop 的做法）。"""
    phone = _phone()
    if role == "tourist":
        client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    else:
        client.post(
            "/api/v1/auth/register/enterprise",
            json={
                "phone": phone,
                "password": "secret123",
                "license_no": f"91{uuid.uuid4().int % 10**16:016d}",
                "role": role,
            },
        )
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.phone == phone))
            user.status = UserStatus.ACTIVE
            db.commit()
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return phone, data["access_token"], data["user"]["id"]


def _merchant(client: TestClient) -> dict[str, str]:
    _p, token, _u = _user(client, "merchant")
    return {"Authorization": f"Bearer {token}"}


def _product(client: TestClient, headers: dict[str, str], name: str, price: float) -> int:
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": name, "description": "测试用", "price": price, "stock": 10},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["data"]["id"])


def test_favorite_requires_login_and_product_must_be_on_sale(client: TestClient) -> None:
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"收藏用例-{uuid.uuid4().hex[:6]}", 50.0)

    # 未登录 401
    assert client.post(f"/api/v1/shop/favorites/{product_id}").status_code == 401
    assert client.get("/api/v1/shop/favorites").status_code == 401

    _p, token, _u = _user(client)
    headers = {"Authorization": f"Bearer {token}"}
    # 不存在的商品 404
    assert client.post("/api/v1/shop/favorites/999999", headers=headers).status_code == 404

    # 下架商品不可收藏
    client.post(
        f"/api/v1/shop/products/{product_id}/status",
        json={"status": "off_shelf"},
        headers=merchant_headers,
    )
    assert client.post(f"/api/v1/shop/favorites/{product_id}", headers=headers).status_code == 404


def test_favorite_toggle_is_idempotent(client: TestClient) -> None:
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"收藏幂等-{uuid.uuid4().hex[:6]}", 88.0)
    _p, token, user_id = _user(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 重复收藏：都成功，库里只有一条
    for _ in range(3):
        resp = client.post(f"/api/v1/shop/favorites/{product_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_favorited"] is True
    with SessionLocal() as db:
        rows = db.scalars(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        ).all()
        assert len(rows) == 1

    # 我的收藏里能看到
    listing = client.get("/api/v1/shop/favorites", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["data"]["items"]] == [product_id]

    # 重复取消：都成功
    for _ in range(2):
        resp = client.delete(f"/api/v1/shop/favorites/{product_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_favorited"] is False
    assert client.get("/api/v1/shop/favorites", headers=headers).json()["data"]["total"] == 0


def test_favorite_list_filters_by_user_and_keeps_off_shelf(client: TestClient) -> None:
    """收藏清单按人隔离；已下架商品仍在清单里（用户可自行取关）。"""
    merchant_headers = _merchant(client)
    on_sale = _product(client, merchant_headers, f"在售-{uuid.uuid4().hex[:6]}", 10.0)
    off_shelf = _product(client, merchant_headers, f"下架-{uuid.uuid4().hex[:6]}", 20.0)
    _p, token_a, _ua = _user(client)
    _p, token_b, _ub = _user(client)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    client.post(f"/api/v1/shop/favorites/{on_sale}", headers=headers_a)
    client.post(f"/api/v1/shop/favorites/{off_shelf}", headers=headers_a)
    client.post(f"/api/v1/shop/favorites/{on_sale}", headers=headers_b)

    items_a = client.get("/api/v1/shop/favorites", headers=headers_a).json()["data"]["items"]
    assert [item["id"] for item in items_a] == [off_shelf, on_sale]  # 最近收藏在前
    items_b = client.get("/api/v1/shop/favorites", headers=headers_b).json()["data"]["items"]
    assert [item["id"] for item in items_b] == [on_sale]

    client.post(
        f"/api/v1/shop/products/{off_shelf}/status",
        json={"status": "off_shelf"},
        headers=merchant_headers,
    )
    items_after = client.get("/api/v1/shop/favorites", headers=headers_a).json()["data"]["items"]
    assert {item["id"] for item in items_after} == {on_sale, off_shelf}  # 下架不下掉收藏项


def test_product_detail_favorite_state(client: TestClient) -> None:
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"详情收藏态-{uuid.uuid4().hex[:6]}", 66.0)
    _p, token, _u = _user(client)
    headers = {"Authorization": f"Bearer {token}"}

    detail = client.get(f"/api/v1/shop/products/{product_id}").json()["data"]
    assert detail["is_favorited"] is False  # 匿名：恒为未收藏
    assert detail["favorite_count"] == 0

    client.post(f"/api/v1/shop/favorites/{product_id}", headers=headers)
    detail_logged_in = client.get(f"/api/v1/shop/products/{product_id}", headers=headers).json()[
        "data"
    ]
    assert detail_logged_in["is_favorited"] is True
    assert detail_logged_in["favorite_count"] == 1

    # 收藏数公开：另一个未登录 / 他人视角也能看到计数，但 is_favorited 为 False
    other_detail = client.get(f"/api/v1/shop/products/{product_id}").json()["data"]
    assert other_detail["is_favorited"] is False
    assert other_detail["favorite_count"] == 1


def test_history_recorded_dedup_and_clear(client: TestClient) -> None:
    merchant_headers = _merchant(client)
    first = _product(client, merchant_headers, f"历史甲-{uuid.uuid4().hex[:6]}", 30.0)
    second = _product(client, merchant_headers, f"历史乙-{uuid.uuid4().hex[:6]}", 40.0)
    _p, token, user_id = _user(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 匿名浏览不记录（按商品维度断言：其它用例的登录浏览不干扰）
    client.get(f"/api/v1/shop/products/{first}")
    with SessionLocal() as db:
        anon_rows = db.scalars(select(ProductView).where(ProductView.product_id == first)).all()
        assert anon_rows == []

    client.get(f"/api/v1/shop/products/{first}", headers=headers)
    client.get(f"/api/v1/shop/products/{second}", headers=headers)
    client.get(f"/api/v1/shop/products/{first}", headers=headers)  # 再看一次：去重 + 次数累加

    with SessionLocal() as db:
        rows = db.scalars(select(ProductView).where(ProductView.user_id == user_id)).all()
        assert len(rows) == 2  # 同一商品只留一条
        counts = {row.product_id: row.view_count for row in rows}
        assert counts == {first: 2, second: 1}

    items = client.get("/api/v1/shop/history", headers=headers).json()["data"]["items"]
    assert [item["id"] for item in items] == [first, second]  # 最近浏览在前

    cleared = client.delete("/api/v1/shop/history", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["data"]["deleted"] == 2
    assert client.get("/api/v1/shop/history", headers=headers).json()["data"]["total"] == 0


def test_merchant_product_list_exposes_favorite_count(client: TestClient) -> None:
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"商户收藏数-{uuid.uuid4().hex[:6]}", 12.0)
    _p, token, _u = _user(client)
    client.post(
        f"/api/v1/shop/favorites/{product_id}", headers={"Authorization": f"Bearer {token}"}
    )

    resp = client.get("/api/v1/shop/merchant/products", headers=merchant_headers)
    assert resp.status_code == 200
    row = next(item for item in resp.json()["data"]["items"] if item["id"] == product_id)
    assert row["favorite_count"] == 1


def test_interest_keywords_from_product_names() -> None:
    """兴趣关键词提炼：剥离括号规格 + 提取品名核心（尾部片段），去重保序。"""
    keywords = service._interest_keywords(["柴达木黑枸杞（100g 礼盒）", "青海雪菊 (80g)"])

    assert keywords[0] == "柴达木黑枸杞"  # 完整名（去规格）在前，命中「同一商品再买」
    assert "黑枸杞" in keywords  # 品名核心（尾部 3 字）
    assert "雪菊" in keywords  # 尾部 2 字：短品名也要能命中
    assert all("礼盒" not in kw and "80g" not in kw for kw in keywords)  # 规格不参与匹配
    assert keywords == list(dict.fromkeys(keywords))  # 去重保序
    assert service._interest_keywords(["（无核心）", ""]) == []


def test_recommendations_personal_path_prefers_relevant_and_similar_price(
    client: TestClient,
) -> None:
    """有行为数据：名称相关性（复用计算核心 planning_score）与价格接近度共同决定排序。"""
    merchant_headers = _merchant(client)
    token = uuid.uuid4().hex[:8]
    # 前缀放随机串：品名核心仍落在尾部（黑枸杞），且不同用例之间不会互相命中关键词
    interest = _product(client, merchant_headers, f"{token}甲组黑枸杞", 100.0)
    relevant = _product(client, merchant_headers, f"{token}乙组黑枸杞（测试装）", 90.0)  # 名称相关
    cheap = _product(client, merchant_headers, f"{token}无关丙", 100.0)  # 价格贴合但名称无关
    pricey = _product(client, merchant_headers, f"{token}无关丁", 1000.0)  # 名称无关且价格远

    _p, user_token, _u = _user(client)
    headers = {"Authorization": f"Bearer {user_token}"}
    client.get(f"/api/v1/shop/products/{interest}", headers=headers)  # 产生浏览历史

    # 接口形状（basis 供前端定标题）
    resp = client.get("/api/v1/shop/recommendations?limit=20", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["basis"] == "personal"
    assert relevant in [item["id"] for item in resp.json()["data"]["items"]]

    # 排序断言走服务层（接口 limit 上限 20，测试库商品更多时会被截断）
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == _u))
        products, basis = service.recommend_products(db, user, limit=200)
    assert basis == "personal"
    ids = [product.id for product in products]
    # 名称相关的排在「名称无关但价格贴合」前，后者又排在「名称无关且价格远」前
    assert ids.index(relevant) < ids.index(cheap) < ids.index(pricey)


def test_recommendations_popular_path_for_anonymous_and_new_user(client: TestClient) -> None:
    """游客 / 无行为用户：全站热度兜底（收藏 × 2 + 浏览次数）。"""
    merchant_headers = _merchant(client)
    token = uuid.uuid4().hex[:6]
    hot = _product(client, merchant_headers, f"热门甲{token}", 55.0)
    cold = _product(client, merchant_headers, f"冷门乙{token}", 60.0)

    # 两个不同用户制造热度：hot 被收藏 2 次
    for _ in range(2):
        _p, t, _u = _user(client)
        client.post(f"/api/v1/shop/favorites/{hot}", headers={"Authorization": f"Bearer {t}"})

    resp = client.get("/api/v1/shop/recommendations?limit=20")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["basis"] == "popular"

    # 排序断言走服务层（不受接口 limit 截断影响）
    with SessionLocal() as db:
        products, basis = service.recommend_products(db, None, limit=200)
        scores = __import__(
            "app.modules.shop.repository", fromlist=["popularity_scores"]
        ).popularity_scores(db, [hot, cold])
    assert basis == "popular"
    ids = [product.id for product in products]
    assert ids.index(hot) < ids.index(cold)
    assert scores.get(hot, 0) >= 4 > scores.get(cold, 0)  # 收藏 × 2 + 浏览

    # 新用户（有账号但无行为）同样走 popular
    _p, fresh_token, _u = _user(client)
    fresh = client.get(
        "/api/v1/shop/recommendations", headers={"Authorization": f"Bearer {fresh_token}"}
    ).json()["data"]
    assert fresh["basis"] == "popular"


def test_recommendations_skip_off_shelf_products(client: TestClient) -> None:
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"推荐下架-{uuid.uuid4().hex[:6]}", 70.0)
    client.post(
        f"/api/v1/shop/products/{product_id}/status",
        json={"status": "off_shelf"},
        headers=merchant_headers,
    )

    items = client.get("/api/v1/shop/recommendations?limit=20").json()["data"]["items"]
    assert product_id not in [item["id"] for item in items]

    with SessionLocal() as db:
        assert db.get(Product, product_id).status == ProductStatus.OFF_SHELF


def test_interest_keywords_strips_generic_suffixes() -> None:
    """通用后缀（礼盒 / 特产 / 特级）不能成为关键词——否则所有礼盒类商品都会命中。"""
    keywords = service._interest_keywords(["青海黑枸杞礼盒", "西北特产大礼包"])
    assert "礼盒" not in keywords
    assert "礼包" not in keywords
    assert "特产" not in keywords
    assert "黑枸杞" in keywords  # 真正的品名核心仍被提取
    # 只剩通用词的名字：剥到保底 1 字也不崩
    assert service._interest_keywords(["礼盒"]) == ["礼盒"]


def test_recommendations_ignore_generic_suffix_matches(client: TestClient) -> None:
    """回归（复审 P1）：看过「…礼盒」后，同品类商品要排在无关的礼盒类商品之前。"""
    merchant_headers = _merchant(client)
    token = uuid.uuid4().hex[:8]
    interest = _product(client, merchant_headers, f"{token}青海黑枸杞礼盒", 200.0)
    same_category = _product(client, merchant_headers, f"{token}昆仑山黑枸杞", 190.0)
    other_gift_a = _product(client, merchant_headers, f"{token}西北特产礼盒", 188.0)
    other_gift_b = _product(client, merchant_headers, f"{token}青稞酒礼盒", 168.0)

    _p, user_token, user_id = _user(client)
    headers = {"Authorization": f"Bearer {user_token}"}
    client.get(f"/api/v1/shop/products/{interest}", headers=headers)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id))
        products, basis = service.recommend_products(db, user, limit=200)
    assert basis == "personal"
    ids = [product.id for product in products]
    # keywords 里不该出现「礼盒」→ 两个无关礼盒商品的相关分为 0，被同品类商品压过
    assert ids.index(same_category) < ids.index(other_gift_a)
    assert ids.index(same_category) < ids.index(other_gift_b)


def test_add_favorite_duplicate_does_not_rollback_prior_writes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发重复收藏撞唯一约束时只回滚那一条插入（SAVEPOINT），不牵连同一请求内的其它写。"""
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"回滚边界-{uuid.uuid4().hex[:6]}", 60.0)
    _p, token, user_id = _user(client)
    client.post(
        f"/api/v1/shop/favorites/{product_id}", headers={"Authorization": f"Bearer {token}"}
    )

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id))
        product = db.get(Product, product_id)
        product.stock = 999  # 同一请求里的另一笔待提交写
        db.flush()

        # 屏蔽「先查是否已收藏」：强制走插入路径，撞唯一约束（模拟并发重复收藏）
        from app.modules.shop import repository

        monkeypatch.setattr(repository, "get_favorite", lambda *args, **kwargs: None)
        count = service.add_favorite(db, user, product_id)

    assert count == 1  # 收藏仍只有一条
    with SessionLocal() as db:
        assert db.get(Product, product_id).stock == 999  # 待提交写未被连带回滚


def test_public_detail_ignores_invalid_token(client: TestClient) -> None:
    """公开接口带无效 / 过期令牌时按匿名处理（不能用 401 把公开页面变成错误页）。"""
    merchant_headers = _merchant(client)
    product_id = _product(client, merchant_headers, f"令牌容错-{uuid.uuid4().hex[:6]}", 45.0)

    bad = {"Authorization": "Bearer not-a-real-token"}
    detail = client.get(f"/api/v1/shop/products/{product_id}", headers=bad)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["is_favorited"] is False

    recs = client.get("/api/v1/shop/recommendations", headers=bad)
    assert recs.status_code == 200
    assert recs.json()["data"]["basis"] == "popular"

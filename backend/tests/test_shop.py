"""shop 模块：商品上架 / 列表 / 详情与下单扣库存测试。"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import ConflictError
from app.db.session import SessionLocal
from app.modules.shop import service as shop_service
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus
from tests.conftest import RECEIVER, FakeMinio


def _unique_phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录一个可用的用户，返回 (phone, token, user_id)。

    商户 / 企业正常流程需 admin 审核；测试夹具直接改状态（同 test_cs 的做法）。
    """
    phone = _unique_phone()
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


def _create_product(
    client: TestClient, merchant_headers: dict, name: str, price: float, stock: int
) -> dict:
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": name, "description": "测试用", "price": price, "stock": stock},
        headers=merchant_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_product_creation_requires_merchant_role(client: TestClient) -> None:
    assert client.post("/api/v1/shop/products", json={"name": "x", "price": 1}).status_code == 401

    _p, token, _u = _register_active_user(client)
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "x", "price": 1, "stock": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300


def test_product_list_detail_and_filters(client: TestClient) -> None:
    _p, m_token, m_id = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试牦牛肉干", 68.0, 20)

    # 公开列表（无需登录）+ 分页形状
    resp = client.get("/api/v1/shop/products?page=1&page_size=5")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert set(data["items"][0]) >= {
        "id",
        "merchant_id",
        "name",
        "description",
        "price",
        "stock",
        "status",
        "created_at",
    }

    # 关键词 + 商户过滤
    resp = client.get("/api/v1/shop/products?keyword=牦牛肉干")
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["name"] == "测试牦牛肉干"

    resp = client.get(f"/api/v1/shop/products?merchant_id={m_id}")
    assert all(item["merchant_id"] == m_id for item in resp.json()["data"]["items"])

    # 详情与 404
    resp = client.get(f"/api/v1/shop/products/{product['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["price"] == 68.0
    assert client.get("/api/v1/shop/products/999999").status_code == 404


def test_order_decreases_stock_and_blocks_oversell(client: TestClient) -> None:
    _p, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试青稞酒", 39.9, 5)
    pid = product["id"]

    # 未登录下单 401
    resp = client.post("/api/v1/shop/orders", json={"product_id": pid, "quantity": 1, **RECEIVER})
    assert resp.status_code == 401

    _p2, b_token, b_id = _register_active_user(client)
    buyer_headers = {"Authorization": f"Bearer {b_token}"}

    # 下单成功：金额、归属正确，库存减少
    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": pid, "quantity": 2, **RECEIVER},
        headers=buyer_headers,
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()["data"]
    assert order["items"][0]["quantity"] == 2
    assert order["amount"] == 79.8
    assert order["user_id"] == b_id
    assert order["merchant_id"] == product["merchant_id"]
    resp = client.get(f"/api/v1/shop/products/{pid}")
    assert resp.json()["data"]["stock"] == 3

    # 超卖拦截：剩 3 件买 4 件 → 409，库存不变
    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": pid, "quantity": 4, **RECEIVER},
        headers=buyer_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == 40900
    resp = client.get(f"/api/v1/shop/products/{pid}")
    assert resp.json()["data"]["stock"] == 3

    # 买光后不能再下单
    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": pid, "quantity": 3, **RECEIVER},
        headers=buyer_headers,
    )
    assert resp.status_code == 200
    resp = client.get(f"/api/v1/shop/products/{pid}")
    assert resp.json()["data"]["stock"] == 0
    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": pid, "quantity": 1, **RECEIVER},
        headers=buyer_headers,
    )
    assert resp.status_code == 409


def test_product_value_bounds(client: TestClient) -> None:
    """价格 / 库存超过上界应在参数校验阶段返回 422（此前会溢出成 500）。"""
    _p, m_token, _mid = _register_active_user(client, "merchant")
    headers = {"Authorization": f"Bearer {m_token}"}

    resp = client.post(
        "/api/v1/shop/products", json={"name": "x", "price": 1e12, "stock": 1}, headers=headers
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/shop/products", json={"name": "x", "price": 10, "stock": 10**10}, headers=headers
    )
    assert resp.status_code == 422


def test_order_amount_over_cap_rejected(client: TestClient) -> None:
    """单笔金额超过上限 → 400，且校验发生在扣库存之前。"""
    _p, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试天价商品", 99_999_999, 10)

    _p2, b_token, _bid = _register_active_user(client)
    buyer_headers = {"Authorization": f"Bearer {b_token}"}

    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 2, **RECEIVER},
        headers=buyer_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40000

    resp = client.get(f"/api/v1/shop/products/{product['id']}")
    assert resp.json()["data"]["stock"] == 10

    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=buyer_headers,
    )
    assert resp.status_code == 200


def _admin_headers(client: TestClient) -> dict[str, str]:
    """创建（幂等）并登录测试管理员，返回请求头。"""
    with SessionLocal() as db:
        try:
            users_service.create_admin(db, phone="13700000000", password="admin123456")
        except ConflictError:
            pass
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13700000000", "password": "admin123456"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


class _FakeRedis:
    """最小 Redis 桩：只覆盖库存闸门用到的方法（exists/set/expire/decrby/incrby）。"""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    def exists(self, key: str) -> bool:
        return key in self.store

    def set(self, key: str, value: int, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = int(value)
        return True

    def expire(self, key: str, seconds: int) -> bool:
        return True

    def decrby(self, key: str, amount: int) -> int:
        self.store[key] -= amount
        return self.store[key]

    def incrby(self, key: str, amount: int) -> int:
        self.store[key] += amount
        return self.store[key]


def test_cart_flow_and_checkout(client: TestClient) -> None:
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    p1 = _create_product(client, merchant_headers, "测试购物车甲", 10.5, 50)
    p2 = _create_product(client, merchant_headers, "测试购物车乙", 3.25, 50)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}

    # 加入（同商品两次合并数量）
    client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": p1["id"], "quantity": 2, **RECEIVER},
        headers=uh,
    )
    resp = client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": p1["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    )
    cart = resp.json()["data"]
    assert cart["items"][0]["quantity"] == 3
    assert cart["items"][0]["amount"] == 31.5

    resp = client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": p2["id"], "quantity": 4, **RECEIVER},
        headers=uh,
    )
    cart = resp.json()["data"]
    assert len(cart["items"]) == 2
    assert cart["total_amount"] == 44.5

    # 修改数量 / 移除
    item_id = cart["items"][1]["id"]
    resp = client.put(f"/api/v1/shop/cart/items/{item_id}", json={"quantity": 2}, headers=uh)
    assert resp.json()["data"]["total_amount"] == 38.0
    resp = client.delete(f"/api/v1/shop/cart/items/{item_id}", headers=uh)
    assert len(resp.json()["data"]["items"]) == 1

    # 结算：订单金额正确、库存扣减、购物车清空
    resp = client.post("/api/v1/shop/cart/checkout", json=dict(RECEIVER), headers=uh)
    assert resp.status_code == 200, resp.text
    order = resp.json()["data"]
    assert order["amount"] == 31.5
    assert len(order["items"]) == 1
    assert client.get(f"/api/v1/shop/products/{p1['id']}").json()["data"]["stock"] == 47
    assert client.get("/api/v1/shop/cart", headers=uh).json()["data"]["items"] == []

    # 空购物车结算 → 409
    assert (
        client.post("/api/v1/shop/cart/checkout", json=dict(RECEIVER), headers=uh).status_code
        == 409
    )


def test_checkout_rejects_multi_merchant(client: TestClient) -> None:
    _m1p, m1_token, _m1 = _register_active_user(client, "merchant")
    _m2p, m2_token, _m2 = _register_active_user(client, "merchant")
    p1 = _create_product(client, {"Authorization": f"Bearer {m1_token}"}, "测试跨店甲", 5, 10)
    p2 = _create_product(client, {"Authorization": f"Bearer {m2_token}"}, "测试跨店乙", 6, 10)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}
    client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": p1["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    )
    client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": p2["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    )

    resp = client.post("/api/v1/shop/cart/checkout", json=dict(RECEIVER), headers=uh)
    assert resp.status_code == 400
    assert "同一商户" in resp.json()["msg"]
    # 购物车与库存均未被改动
    assert len(client.get("/api/v1/shop/cart", headers=uh).json()["data"]["items"]) == 2
    assert client.get(f"/api/v1/shop/products/{p1['id']}").json()["data"]["stock"] == 10


def test_order_idempotency(client: TestClient) -> None:
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试幂等商品", 20, 10)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}

    # 直接下单：同一幂等键重复提交 → 同一订单、库存只扣一次
    body = {
        "product_id": product["id"],
        "quantity": 2,
        "idem_key": "test-idem-key-0001",
        **RECEIVER,
    }
    first = client.post("/api/v1/shop/orders", json=body, headers=uh).json()["data"]
    second = client.post("/api/v1/shop/orders", json=body, headers=uh).json()["data"]
    assert first["id"] == second["id"]
    assert client.get(f"/api/v1/shop/products/{product['id']}").json()["data"]["stock"] == 8

    # 购物车结算幂等
    client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    )
    checkout = {"idem_key": "test-checkout-key-0001", **RECEIVER}
    third = client.post("/api/v1/shop/cart/checkout", json=checkout, headers=uh).json()["data"]
    fourth = client.post("/api/v1/shop/cart/checkout", json=checkout, headers=uh).json()["data"]
    assert third["id"] == fourth["id"]
    assert client.get(f"/api/v1/shop/products/{product['id']}").json()["data"]["stock"] == 7


def test_idempotency_key_reuse_with_different_params_rejected(client: TestClient) -> None:
    """幂等键已用于其他参数（商品 / 数量不同）时按 409 处理，不静默返回旧订单。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    p1 = _create_product(client, merchant_headers, "幂等参数商品甲", 10, 10)
    p2 = _create_product(client, merchant_headers, "幂等参数商品乙", 10, 10)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}

    key = f"reuse-{uuid.uuid4().hex}"
    first = client.post(
        "/api/v1/shop/orders",
        json={"product_id": p1["id"], "quantity": 1, "idem_key": key, **RECEIVER},
        headers=uh,
    )
    assert first.status_code == 200

    # 同键不同数量 / 不同商品 → 409，不返回旧订单
    assert (
        client.post(
            "/api/v1/shop/orders",
            json={"product_id": p1["id"], "quantity": 2, "idem_key": key, **RECEIVER},
            headers=uh,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/shop/orders",
            json={"product_id": p2["id"], "quantity": 1, "idem_key": key, **RECEIVER},
            headers=uh,
        ).status_code
        == 409
    )

    # 完全相同的参数重放仍返回首单（正常幂等语义不受影响）
    replay = client.post(
        "/api/v1/shop/orders",
        json={"product_id": p1["id"], "quantity": 1, "idem_key": key, **RECEIVER},
        headers=uh,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]


def test_redis_gate_blocks_oversell(client: TestClient, monkeypatch) -> None:
    """Redis 预扣闸门：闸门判定不足时直接 409，且不触碰数据库库存。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试闸门商品", 10, 10)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}

    fake = _FakeRedis()
    fake.store[f"shop:stock:{product['id']}"] = 1  # 闸门里只剩 1 件
    monkeypatch.setattr(shop_service, "_get_redis", lambda: fake)

    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 2, **RECEIVER},
        headers=uh,
    )
    assert resp.status_code == 409
    assert client.get(f"/api/v1/shop/products/{product['id']}").json()["data"]["stock"] == 10

    # 充足时闸门放行，成功后 Redis 与数据库同步
    generous = _FakeRedis()
    monkeypatch.setattr(shop_service, "_get_redis", lambda: generous)
    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 3, **RECEIVER},
        headers=uh,
    )
    assert resp.status_code == 200
    assert generous.store[f"shop:stock:{product['id']}"] == 7


def test_orders_read_and_permissions(client: TestClient) -> None:
    _mp, m_token, m_id = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试订单读", 12, 10)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    ).json()["data"]

    # 买家：列表 + 详情
    resp = client.get("/api/v1/shop/orders?page=1&page_size=5", headers=uh)
    assert any(item["id"] == order["id"] for item in resp.json()["data"]["items"])
    resp = client.get(f"/api/v1/shop/orders/{order['id']}", headers=uh)
    assert resp.status_code == 200 and resp.json()["data"]["items"][0]["quantity"] == 1

    # 商家：自己的订单可见
    resp = client.get("/api/v1/shop/merchant/orders", headers=merchant_headers)
    assert any(item["id"] == order["id"] for item in resp.json()["data"]["items"])
    assert resp.json()["data"]["items"][0]["merchant_id"] == m_id

    # 无关用户 → 404；管理员可见
    _op, other_token, _oid = _register_active_user(client)
    oh = {"Authorization": f"Bearer {other_token}"}
    assert client.get(f"/api/v1/shop/orders/{order['id']}", headers=oh).status_code == 404
    admin_headers = _admin_headers(client)
    assert (
        client.get(f"/api/v1/shop/orders/{order['id']}", headers=admin_headers).status_code == 200
    )


def test_payment_flow(client: TestClient) -> None:
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "测试支付商品", 30, 5)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    ).json()["data"]

    # 创建支付单（占位）
    resp = client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=uh)
    assert resp.status_code == 200, resp.text
    payment = resp.json()["data"]
    assert payment["status"] == "created" and payment["amount"] == 30.0

    # 重复点击 / 重试：复用未处理支付单，不新开
    again = client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=uh)
    assert again.status_code == 200
    assert again.json()["data"]["id"] == payment["id"]

    # 他人不能为我的订单创建支付单
    _op, other_token, _oid = _register_active_user(client)
    oh = {"Authorization": f"Bearer {other_token}"}
    assert client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=oh).status_code == 404

    # 支付回调仅管理员可触发
    assert (
        client.post(
            f"/api/v1/shop/payments/{payment['id']}/callback",
            json={"success": True},
            headers=uh,
        ).status_code
        == 403
    )

    admin_headers = _admin_headers(client)
    resp = client.post(
        f"/api/v1/shop/payments/{payment['id']}/callback",
        json={"success": True, "trade_no": "MOCK-TRADE-0001"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "success"

    # 订单转为已支付；支付单重复回调 → 409；已支付订单不可再创建支付单
    resp = client.get(f"/api/v1/shop/orders/{order['id']}", headers=uh)
    detail = resp.json()["data"]
    assert (
        detail["status"] == "paid" and detail["paid_at"] and detail["payment_status"] == "success"
    )
    resp = client.post(
        f"/api/v1/shop/payments/{payment['id']}/callback",
        json={"success": True},
        headers=admin_headers,
    )
    assert resp.status_code == 409
    resp = client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=uh)
    assert resp.status_code == 409


def test_admin_order_visibility_and_simulated_callback(client: TestClient) -> None:
    """管理员可查看全平台订单；订单详情暴露 payment_id，供管理员模拟支付回调闭环。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "管理员订单视角商品", 10, 5)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    ).json()["data"]
    payment = client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=uh).json()["data"]

    # 详情带 payment_id（模拟回调入口）
    detail = client.get(f"/api/v1/shop/orders/{order['id']}", headers=uh).json()["data"]
    assert detail["payment_id"] == payment["id"]

    # 管理员在订单列表中能看到该订单（全平台视角）
    admin_headers = _admin_headers(client)
    listed = client.get("/api/v1/shop/merchant/orders", headers=admin_headers).json()["data"]
    assert any(item["id"] == order["id"] for item in listed["items"])

    # 管理员模拟回调 → 订单转已支付
    resp = client.post(
        f"/api/v1/shop/payments/{payment['id']}/callback",
        json={"success": True, "trade_no": "ADMIN-MOCK-0001"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    detail = client.get(f"/api/v1/shop/orders/{order['id']}", headers=uh).json()["data"]
    assert detail["status"] == "paid"


def test_product_off_shelf_flow(client: TestClient) -> None:
    """下架闭环：非归属商户 403；下架后公开不可见、加购被拦；可重新上架。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "下架流程商品", 10, 5)

    _op, other_token, _oid = _register_active_user(client, "merchant")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    resp = client.post(
        f"/api/v1/shop/products/{product['id']}/status",
        json={"status": "off_shelf"},
        headers=other_headers,
    )
    assert resp.status_code == 403

    resp = client.post(
        f"/api/v1/shop/products/{product['id']}/status",
        json={"status": "off_shelf"},
        headers=merchant_headers,
    )
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "off_shelf"

    # 公开详情 404、公开列表不含该商品
    assert client.get(f"/api/v1/shop/products/{product['id']}").status_code == 404
    listed = client.get(
        "/api/v1/shop/products", params={"merchant_id": _mid, "page_size": 50}
    ).json()["data"]
    assert all(item["id"] != product["id"] for item in listed["items"])

    # 加购被在售校验拦下
    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}
    assert (
        client.post(
            "/api/v1/shop/cart/items",
            json={"product_id": product["id"], "quantity": 1, **RECEIVER},
            headers=uh,
        ).status_code
        == 404
    )

    # 重新上架恢复可见
    resp = client.post(
        f"/api/v1/shop/products/{product['id']}/status",
        json={"status": "on_sale"},
        headers=merchant_headers,
    )
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "on_sale"
    assert client.get(f"/api/v1/shop/products/{product['id']}").status_code == 200


def test_order_cancel_flow(client: TestClient) -> None:
    """取消订单闭环：库存同事务回补、状态翻转、重复取消 409、已支付不可取消、他人 404。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "取消流程商品", 10, 10)

    _up, u_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {u_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 3, **RECEIVER},
        headers=uh,
    ).json()["data"]
    assert client.get(f"/api/v1/shop/products/{product['id']}").json()["data"]["stock"] == 7

    # 他人不可取消（按不存在处理）
    _op, other_token, _oid = _register_active_user(client)
    oh = {"Authorization": f"Bearer {other_token}"}
    assert client.post(f"/api/v1/shop/orders/{order['id']}/cancel", headers=oh).status_code == 404

    # 取消 → 库存回补
    resp = client.post(f"/api/v1/shop/orders/{order['id']}/cancel", headers=uh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "cancelled"
    assert client.get(f"/api/v1/shop/products/{product['id']}").json()["data"]["stock"] == 10

    # 重复取消 → 409
    assert client.post(f"/api/v1/shop/orders/{order['id']}/cancel", headers=uh).status_code == 409

    # 已支付订单不可取消
    order2 = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    ).json()["data"]
    payment = client.post(f"/api/v1/shop/orders/{order2['id']}/pay", headers=uh).json()["data"]
    admin_headers = _admin_headers(client)
    ok_resp = client.post(
        f"/api/v1/shop/payments/{payment['id']}/callback",
        json={"success": True},
        headers=admin_headers,
    )
    assert ok_resp.status_code == 200
    assert client.post(f"/api/v1/shop/orders/{order2['id']}/cancel", headers=uh).status_code == 409


def test_product_with_image(client: TestClient, fake_minio: FakeMinio) -> None:
    """商品主图：引用本人上传的公开图片 → 处处带 image_url，匿名可看图；
    引用他人 / 不存在的文件 → 404（不能引用别人的文件）。"""
    from tests.conftest import PNG_BYTES

    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    upload = client.post(
        "/api/v1/files",
        files={"file": ("主图.png", PNG_BYTES, "image/png")},
        data={"public": "true"},
        headers=mh,
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["data"]["id"]

    # 上架带图商品 → 响应带 image_url
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "带图商品", "price": 12.5, "stock": 7, "image_file_id": file_id},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    product = resp.json()["data"]
    assert product["image_url"] == f"/api/v1/files/{file_id}"

    # 列表 / 详情同样带图
    listed = client.get("/api/v1/shop/products", params={"keyword": "带图商品"})
    item = next(row for row in listed.json()["data"]["items"] if row["id"] == product["id"])
    assert item["image_url"] == f"/api/v1/files/{file_id}"
    detail = client.get(f"/api/v1/shop/products/{product['id']}")
    assert detail.json()["data"]["image_url"] == f"/api/v1/files/{file_id}"

    # 匿名（游客未登录）可读商品图
    assert client.get(f"/api/v1/files/{file_id}").status_code == 200

    # 引用他人文件 → 404
    _mp2, m2_token, _mid2 = _register_active_user(client, "merchant")
    m2h = {"Authorization": f"Bearer {m2_token}"}
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "盗图商品", "price": 1, "stock": 1, "image_file_id": file_id},
        headers=m2h,
    )
    assert resp.status_code == 404

    # 不存在的文件 id → 404
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "无图商品", "price": 1, "stock": 1, "image_file_id": 999999},
        headers=mh,
    )
    assert resp.status_code == 404

    # 不带图正常上架（image_url 为 None）
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "无图正常商品", "price": 1, "stock": 1},
        headers=mh,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["image_url"] is None


def test_update_product_owner_only_and_partial(client: TestClient, fake_minio: FakeMinio) -> None:
    """编辑商品：部分更新（只改提交的字段）、仅归属商户、换图 / 移除图、状态不可改。"""
    from tests.conftest import PNG_BYTES

    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    file_id = client.post(
        "/api/v1/files",
        files={"file": ("主图.png", PNG_BYTES, "image/png")},
        data={"public": "true"},
        headers=mh,
    ).json()["data"]["id"]

    product = client.post(
        "/api/v1/shop/products",
        json={"name": "待编辑商品", "price": 10, "stock": 5, "description": "原始描述"},
        headers=mh,
    ).json()["data"]
    pid = product["id"]

    # 部分更新：只改价格与库存，名称 / 描述不变，并可加图
    resp = client.put(
        f"/api/v1/shop/products/{pid}",
        json={"price": 12.5, "stock": 88, "image_file_id": file_id},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["price"] == 12.5
    assert data["stock"] == 88
    assert data["name"] == "待编辑商品"
    assert data["description"] == "原始描述"
    assert data["image_url"] == f"/api/v1/files/{file_id}"

    # 改名称 / 描述
    resp = client.put(
        f"/api/v1/shop/products/{pid}",
        json={"name": "改名商品", "description": "新描述"},
        headers=mh,
    )
    assert resp.json()["data"]["name"] == "改名商品"
    assert resp.json()["data"]["description"] == "新描述"

    # 移除主图：显式传 null
    resp = client.put(f"/api/v1/shop/products/{pid}", json={"image_file_id": None}, headers=mh)
    assert resp.json()["data"]["image_url"] is None

    # 公开列表能看到新价（缓存已 bump）
    listed = client.get("/api/v1/shop/products", params={"keyword": "改名商品"}).json()["data"]
    assert listed["items"][0]["price"] == 12.5

    # 空请求 400；非法价格 422
    assert client.put(f"/api/v1/shop/products/{pid}", json={}, headers=mh).status_code == 400
    invalid = client.put(f"/api/v1/shop/products/{pid}", json={"price": -1}, headers=mh)
    assert invalid.status_code == 422

    # 他人不能编辑（403）、不存在 404、游客 / 管理员被角色拦截（403）
    _mp2, m2_token, _mid2 = _register_active_user(client, "merchant")
    m2h = {"Authorization": f"Bearer {m2_token}"}
    forbidden = client.put(f"/api/v1/shop/products/{pid}", json={"price": 1}, headers=m2h)
    assert forbidden.status_code == 403
    assert (
        client.put("/api/v1/shop/products/999999", json={"price": 1}, headers=mh).status_code == 404
    )
    _tp, t_token, _tid = _register_active_user(client)
    assert (
        client.put(
            f"/api/v1/shop/products/{pid}",
            json={"price": 1},
            headers={"Authorization": f"Bearer {t_token}"},
        ).status_code
        == 403
    )

    # 引用他人文件 → 404
    other_file = client.post(
        "/api/v1/files",
        files={"file": ("别人的图.png", PNG_BYTES, "image/png")},
        data={"public": "true"},
        headers=m2h,
    ).json()["data"]["id"]
    resp = client.put(
        f"/api/v1/shop/products/{pid}", json={"image_file_id": other_file}, headers=mh
    )
    assert resp.status_code == 404


def test_merchant_products_status_filter(client: TestClient) -> None:
    """我的商品列表：按状态筛选只返回对应状态的商品；非法状态 400。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    on_sale = client.post(
        "/api/v1/shop/products", json={"name": "筛选在售商品", "price": 5, "stock": 5}, headers=mh
    ).json()["data"]["id"]
    off_shelf = client.post(
        "/api/v1/shop/products", json={"name": "筛选下架商品", "price": 5, "stock": 5}, headers=mh
    ).json()["data"]["id"]
    client.post(
        f"/api/v1/shop/products/{off_shelf}/status", json={"status": "off_shelf"}, headers=mh
    )

    def ids(**params: str) -> set[int]:
        resp = client.get("/api/v1/shop/merchant/products", params=params, headers=mh)
        assert resp.status_code == 200, resp.text
        return {row["id"] for row in resp.json()["data"]["items"]}

    all_ids = ids(page_size="50")
    assert {on_sale, off_shelf} <= all_ids
    assert off_shelf not in ids(status="on_sale", page_size="50")
    assert on_sale not in ids(status="off_shelf", page_size="50")
    assert ids(status="on_sale", page_size="50").isdisjoint(ids(status="off_shelf", page_size="50"))

    assert (
        client.get(
            "/api/v1/shop/merchant/products", params={"status": "bad"}, headers=mh
        ).status_code
        == 400
    )


def test_order_cancel_and_payment_callback_are_audited(client: TestClient) -> None:
    """订单取消（买家）与模拟支付回调（管理员）写入审计日志，可按目标类型查询。"""
    from app.modules.admin.models import AuditLog

    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    product_id = client.post(
        "/api/v1/shop/products",
        json={"name": "审计用例商品", "price": 9, "stock": 5},
        headers=mh,
    ).json()["data"]["id"]

    _tp, t_token, tourist_id = _register_active_user(client)
    th = {"Authorization": f"Bearer {t_token}"}

    # 1) 取消订单 → order.cancel（actor = 买家）
    order_id = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product_id, "quantity": 1, "idem_key": uuid.uuid4().hex, **RECEIVER},
        headers=th,
    ).json()["data"]["id"]
    assert client.post(f"/api/v1/shop/orders/{order_id}/cancel", headers=th).status_code == 200

    with SessionLocal() as db:
        logs = db.scalars(
            select(AuditLog)
            .where(AuditLog.target_type == "order", AuditLog.target_id == order_id)
            .order_by(AuditLog.id.asc())
        ).all()
    assert [log.action for log in logs] == ["order.cancel"]
    assert logs[0].actor_id == tourist_id
    assert "库存已回补" in (logs[0].detail or "")

    # 2) 管理员模拟支付回调 → payment.callback（actor = 管理员）
    order2 = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product_id, "quantity": 1, "idem_key": uuid.uuid4().hex, **RECEIVER},
        headers=th,
    ).json()["data"]
    payment = client.post(f"/api/v1/shop/orders/{order2['id']}/pay", headers=th).json()["data"]
    admin_headers = _admin_headers(client)
    admin_id = client.get("/api/v1/users/me", headers=admin_headers).json()["data"]["id"]
    resp = client.post(
        f"/api/v1/shop/payments/{payment['id']}/callback",
        json={"success": True, "trade_no": "AUDIT-1"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        logs = db.scalars(
            select(AuditLog).where(
                AuditLog.target_type == "payment", AuditLog.target_id == payment["id"]
            )
        ).all()
    assert [log.action for log in logs] == ["payment.callback"]
    assert logs[0].actor_id == admin_id
    assert "模拟支付回调" in (logs[0].detail or "")


def test_product_list_sort_and_price_filter(client: TestClient) -> None:
    """商品列表支持排序与价格区间（过滤/排序下推 SQL，分页 total 与条件一致）。"""
    _p, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    # 三个价位便于断言顺序
    cheap = _create_product(client, merchant_headers, "排序-便宜", 10.0, 5)
    mid = _create_product(client, merchant_headers, "排序-中等", 50.0, 5)
    pricey = _create_product(client, merchant_headers, "排序-昂贵", 99.0, 5)
    keyword = "排序-"

    def ids(params: str) -> list[int]:
        resp = client.get(f"/api/v1/shop/products?keyword={keyword}&page_size=20&{params}")
        assert resp.status_code == 200, resp.text
        return [item["id"] for item in resp.json()["data"]["items"]]

    # 默认 = 最新（id 倒序，本用例里恰好是 贵→中→便宜）
    assert ids("") == [pricey["id"], mid["id"], cheap["id"]]
    assert ids("sort=price_asc") == [cheap["id"], mid["id"], pricey["id"]]
    assert ids("sort=price_desc") == [pricey["id"], mid["id"], cheap["id"]]

    # 价格区间（含端点，下推 SQL；total 与筛选一致）
    resp = client.get(f"/api/v1/shop/products?keyword={keyword}&min_price=10&max_price=50")
    data = resp.json()["data"]
    assert data["total"] == 2, data
    assert {item["id"] for item in data["items"]} == {cheap["id"], mid["id"]}

    # 非法排序值 / 负价格 → 422（参数校验）
    assert client.get("/api/v1/shop/products?sort=whatever").status_code == 422
    assert client.get("/api/v1/shop/products?min_price=-1").status_code == 422
    # min > max → 400（业务校验）
    resp = client.get("/api/v1/shop/products?min_price=100&max_price=10")
    assert resp.status_code == 400, resp.text


def test_product_list_cache_does_not_mix_sort_and_price(client: TestClient) -> None:
    """缓存键必须带上排序与价格区间，否则不同查询会互相串结果（回归防线）。"""
    _p, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    cheap = _create_product(client, merchant_headers, "缓存-便宜", 10.0, 5)
    pricey = _create_product(client, merchant_headers, "缓存-昂贵", 90.0, 5)

    first = client.get("/api/v1/shop/products?keyword=缓存-&sort=price_asc").json()["data"]["items"]
    second = client.get("/api/v1/shop/products?keyword=缓存-&sort=price_desc").json()["data"][
        "items"
    ]
    assert [i["id"] for i in first] == [cheap["id"], pricey["id"]]
    assert [i["id"] for i in second] == [pricey["id"], cheap["id"]]

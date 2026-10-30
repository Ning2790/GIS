"""dashboard 模块：控制台首页概览（按角色聚合）测试。"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.users.models import User, UserStatus
from tests.conftest import RECEIVER


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录一个可用用户，返回 (phone, token, user_id)（同 test_shop 的做法）。"""
    phone = "13" + str(uuid.uuid4().int)[:9]
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


def _admin_headers(client: TestClient) -> dict[str, str]:
    from app.core.errors import ConflictError
    from app.modules.users import service as users_service

    with SessionLocal() as db:
        try:
            users_service.create_admin(db, phone="13700000001", password="admin123456")
        except ConflictError:
            pass
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13700000001", "password": "admin123456"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def test_dashboard_requires_console_role(client: TestClient) -> None:
    assert client.get("/api/v1/dashboard/summary").status_code == 401
    _tp, token, _tid = _register_active_user(client)
    resp = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403  # 游客无控制台


def test_dashboard_merchant_view(client: TestClient) -> None:
    """商户视角：只有自己的商品 / 订单计数 + 库存预警；不含管理员字段。"""
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}

    # 造数据：1 个在售（低库存）+ 1 个下架商品 + 1 个待支付订单
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "概览在售商品", "price": 10, "stock": 3},
        headers=mh,
    )
    product_id = resp.json()["data"]["id"]
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "概览下架商品", "price": 10, "stock": 100},
        headers=mh,
    )
    await_id = resp.json()["data"]["id"]
    client.post(
        f"/api/v1/shop/products/{await_id}/status", json={"status": "off_shelf"}, headers=mh
    )
    client.post(
        "/api/v1/shop/orders",
        json={"product_id": product_id, "quantity": 1, "idem_key": uuid.uuid4().hex, **RECEIVER},
        headers=mh,
    )

    data = client.get("/api/v1/dashboard/summary", headers=mh).json()["data"]
    assert data["role"] == "merchant"
    assert data["my_products"] == 2
    assert data["my_products_on_sale"] == 1
    assert data["my_products_off_shelf"] == 1
    assert data["my_orders_created"] == 1
    assert data["my_orders_paid"] == 0
    assert data["today_orders"] >= 1
    assert data["low_stock"] == 1  # 库存 3 ≤ 阈值 10
    assert data["low_stock_threshold"] == 10
    assert data["cs_queue"] is not None
    # 管理员专属字段为空
    assert data["users_total"] is None
    assert data["pending_reviews"] is None
    assert data["recent_logs"] == []


def test_dashboard_admin_view(client: TestClient) -> None:
    """管理员视角：全平台统计 + 用户 / 待审核 + 最近审计日志。"""
    ah = _admin_headers(client)
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    client.post(
        "/api/v1/shop/products",
        json={"name": "管理员概览商品", "price": 20, "stock": 50},
        headers=mh,
    )

    data = client.get("/api/v1/dashboard/summary", headers=ah).json()["data"]
    assert data["role"] == "admin"
    assert data["users_total"] and data["users_total"] > 0
    assert data["pending_reviews"] is not None
    assert data["products_total"] >= 1
    assert data["my_products"] == data["products_total"]  # 管理员看全平台
    assert isinstance(data["recent_logs"], list)


def test_dashboard_admin_sees_platform_orders_not_own(client: TestClient) -> None:
    """管理员在首页看到的是全平台订单（他人下的单也算），不是自己名下的。"""
    ah = _admin_headers(client)
    _tp, t_token, _tid = _register_active_user(client)
    th = {"Authorization": f"Bearer {t_token}"}
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    product_id = client.post(
        "/api/v1/shop/products",
        json={"name": "管理员订单概览商品", "price": 5, "stock": 9},
        headers=mh,
    ).json()["data"]["id"]

    before = client.get("/api/v1/dashboard/summary", headers=ah).json()["data"]
    client.post(
        "/api/v1/shop/orders",
        json={"product_id": product_id, "quantity": 1, "idem_key": uuid.uuid4().hex, **RECEIVER},
        headers=th,
    )
    after = client.get("/api/v1/dashboard/summary", headers=ah).json()["data"]
    assert after["my_orders_created"] == before["my_orders_created"] + 1

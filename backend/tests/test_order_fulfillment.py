"""订单履约（N3）：发货 → 签收 → 确认收货 / 自动确认收货。"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import ConflictError
from app.db.session import SessionLocal
from app.modules.admin.models import AuditLog
from app.modules.shop import service as shop_service
from app.modules.shop.models import Order, OrderStatus
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus
from tests.conftest import RECEIVER


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录一个可用账号（商户直接置为 active，同 test_shop 做法）。"""
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


def _paid_order(client: TestClient) -> tuple[dict, dict, int]:
    """建一个「已支付」订单：返回 (商户头, 买家头, 订单 id)。"""
    _mp, merchant_token, _mid = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {merchant_token}"}
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "履约测试商品", "description": "测试用", "price": 20, "stock": 5},
        headers=mh,
    ).json()["data"]

    _up, user_token, _uid = _register_active_user(client)
    uh = {"Authorization": f"Bearer {user_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "idem_key": uuid.uuid4().hex[:16],
            **RECEIVER,
        },
        headers=uh,
    ).json()["data"]
    payment = client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=uh).json()["data"]
    resp = client.post(
        f"/api/v1/shop/payments/{payment['id']}/callback",
        json={"success": True, "trade_no": f"MOCK-{uuid.uuid4().hex[:8]}"},
        headers=_admin_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return mh, uh, order["id"]


def _order_row(order_id: int) -> Order:
    with SessionLocal() as db:
        return db.get(Order, order_id)


def _shift(order_id: int, **offsets: timedelta) -> None:
    """把发货 / 签收时间拨到过去（模拟时间流逝）。"""
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        for field, delta in offsets.items():
            current = getattr(order, field) or datetime.now(UTC)
            setattr(order, field, current - delta)
        db.commit()


def test_ship_requires_paid_order_and_ownership(client: TestClient) -> None:
    _mp, merchant_token, _ = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {merchant_token}"}
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "未支付商品", "description": "t", "price": 5, "stock": 3},
        headers=mh,
    ).json()["data"]
    _up, user_token, _ = _register_active_user(client)
    uh = {"Authorization": f"Bearer {user_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=uh,
    ).json()["data"]

    body = {"carrier": "顺丰", "tracking_no": "SF1234567890"}
    # 待支付不可发货
    resp = client.post(f"/api/v1/shop/orders/{order['id']}/ship", json=body, headers=mh)
    assert resp.status_code == 409

    # 游客调不了（角色不符）
    resp = client.post(f"/api/v1/shop/orders/{order['id']}/ship", json=body, headers=uh)
    assert resp.status_code == 403

    # 其他商户：看不到我的订单（404）
    _mp2, other_token, _ = _register_active_user(client, "merchant")
    resp = client.post(
        f"/api/v1/shop/orders/{order['id']}/ship",
        json=body,
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_ship_requires_carrier_and_tracking_no(client: TestClient) -> None:
    mh, _uh, order_id = _paid_order(client)
    assert (
        client.post(f"/api/v1/shop/orders/{order_id}/ship", json={}, headers=mh).status_code == 422
    )
    assert (
        client.post(
            f"/api/v1/shop/orders/{order_id}/ship",
            json={"carrier": "顺丰", "tracking_no": "12"},
            headers=mh,
        ).status_code
        == 422
    )


def test_full_chain_ship_deliver_receive(client: TestClient) -> None:
    mh, uh, order_id = _paid_order(client)

    # 发货
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF1234567890"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "shipped"
    assert data["carrier"] == "顺丰" and data["tracking_no"] == "SF1234567890"
    assert data["shipped_at"] and not data["delivered_at"]

    # 重复发货 → 409
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF1234567890"},
        headers=mh,
    )
    assert resp.status_code == 409

    # 标记签收
    resp = client.post(f"/api/v1/shop/orders/{order_id}/deliver", headers=mh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["delivered_at"]
    # 重复标记 → 409
    assert client.post(f"/api/v1/shop/orders/{order_id}/deliver", headers=mh).status_code == 409

    # 买家确认收货 → 完成
    resp = client.post(f"/api/v1/shop/orders/{order_id}/receive", headers=uh)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "completed" and data["completed_at"]
    # 已完成再确认 → 409
    assert client.post(f"/api/v1/shop/orders/{order_id}/receive", headers=uh).status_code == 409

    # 审计留痕：发货 / 签收 / 确认收货
    with SessionLocal() as db:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.target_type == "order", AuditLog.target_id == order_id
                )
            ).all()
        )
    assert {"order.ship", "order.deliver", "order.receive"} <= actions


def test_receive_requires_buyer_and_shipped(client: TestClient) -> None:
    mh, uh, order_id = _paid_order(client)
    # 未发货：买家不能确认收货
    assert client.post(f"/api/v1/shop/orders/{order_id}/receive", headers=uh).status_code == 409
    client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "中通", "tracking_no": "ZT999888777"},
        headers=mh,
    )
    # 他人不能替我确认收货
    _up2, other_token, _ = _register_active_user(client)
    assert (
        client.post(
            f"/api/v1/shop/orders/{order_id}/receive",
            headers={"Authorization": f"Bearer {other_token}"},
        ).status_code
        == 404
    )


def test_auto_confirm_after_delivery_window(client: TestClient) -> None:
    mh, _uh, order_id = _paid_order(client)
    client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF0001112223"},
        headers=mh,
    )
    client.post(f"/api/v1/shop/orders/{order_id}/deliver", headers=mh)

    days = get_settings().order_auto_confirm_days
    _shift(order_id, delivered_at=timedelta(days=days, hours=1))

    with SessionLocal() as db:
        assert shop_service.auto_confirm_received_orders(db) == 1
        assert shop_service.auto_confirm_received_orders(db) == 0  # 幂等
    order = _order_row(order_id)
    assert order.status == OrderStatus.COMPLETED and order.completed_at is not None

    with SessionLocal() as db:
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "order.auto_confirm", AuditLog.target_id == order_id)
            .order_by(AuditLog.id.desc())
        )
    assert log is not None and log.actor_id is None  # 系统动作
    assert "签收后" in (log.detail or "")


def test_auto_confirm_fallback_when_not_delivered(client: TestClient) -> None:
    """商户一直未标记签收：发货后兜底天数到期也自动确认，订单不悬着。"""
    mh, _uh, order_id = _paid_order(client)
    client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "邮政", "tracking_no": "YZ555666777"},
        headers=mh,
    )
    settings = get_settings()
    _shift(
        order_id,
        shipped_at=timedelta(days=settings.order_auto_confirm_fallback_days, hours=1),
    )

    with SessionLocal() as db:
        assert shop_service.auto_confirm_received_orders(db) == 1
    order = _order_row(order_id)
    assert order.status == OrderStatus.COMPLETED and order.delivered_at is None
    with SessionLocal() as db:
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "order.auto_confirm", AuditLog.target_id == order_id)
            .order_by(AuditLog.id.desc())
        )
    assert log is not None
    assert "未标记签收" in (log.detail or "")


def test_auto_confirm_not_triggered_early(client: TestClient) -> None:
    mh, _uh, order_id = _paid_order(client)
    client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "圆通", "tracking_no": "YT123123123"},
        headers=mh,
    )
    client.post(f"/api/v1/shop/orders/{order_id}/deliver", headers=mh)
    _shift(order_id, delivered_at=timedelta(hours=2))

    with SessionLocal() as db:
        assert shop_service.auto_confirm_received_orders(db) == 0
    assert _order_row(order_id).status == OrderStatus.SHIPPED


def test_buyer_receive_wins_over_auto_confirm(client: TestClient) -> None:
    """买家先确认收货：自动任务不再处理（原子条件更新只有一个生效）。"""
    mh, uh, order_id = _paid_order(client)
    client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF8889990001"},
        headers=mh,
    )
    # 已完成收货
    assert client.post(f"/api/v1/shop/orders/{order_id}/receive", headers=uh).status_code == 200
    days = get_settings().order_auto_confirm_days
    _shift(order_id, shipped_at=timedelta(days=days * 3))  # 时间早已超过窗口

    with SessionLocal() as db:
        assert shop_service.auto_confirm_received_orders(db) == 0
    assert _order_row(order_id).status == OrderStatus.COMPLETED


def test_mark_delivered_requires_shipped(client: TestClient) -> None:
    mh, _uh, order_id = _paid_order(client)
    # 未发货不能标记签收
    assert client.post(f"/api/v1/shop/orders/{order_id}/deliver", headers=mh).status_code == 409


def test_worker_task_is_registered() -> None:
    from app.worker import celery_app

    assert "shop.auto_confirm_received_orders" in celery_app.tasks


def test_dashboard_stats_include_shipped_orders(client: TestClient) -> None:
    """回归：发货 / 完成后，概览的「已支付」与「今日成交额」不归零（含 shipped/completed）。"""
    mh, _uh, order_id = _paid_order(client)
    with SessionLocal() as db:
        before = shop_service.dashboard_counts(db, merchant_id=None)
    assert before["orders_paid"] >= 1
    assert float(before["today_revenue"]) > 0

    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF7778889990"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    with SessionLocal() as db:
        after = shop_service.dashboard_counts(db, merchant_id=None)
    assert after["orders_paid"] >= 1  # 修复前：发货后该订单从「已支付」里消失
    assert float(after["today_revenue"]) > 0

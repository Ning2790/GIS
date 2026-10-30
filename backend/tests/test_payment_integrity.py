"""支付一致性测试：取消 / 超时后迟到支付进入待退款、退款登记、支付单并发唯一性。"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError
from app.db.session import SessionLocal
from app.modules.notifications.models import Notification, NotificationType
from app.modules.shop import service as shop_service
from app.modules.shop.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentRefundStatus,
    PaymentStatus,
)
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus
from tests.conftest import RECEIVER


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[dict, int]:
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
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


def _admin(client: TestClient) -> tuple[dict, int]:
    with SessionLocal() as db:
        try:
            users_service.create_admin(db, phone="13700000000", password="admin123456")
        except ConflictError:
            pass
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13700000000", "password": "admin123456"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


def _order_with_payment(client: TestClient) -> tuple[dict, dict, int, int, int, int]:
    """返回 (商户头, 买家头, 商户 id, 买家 id, 订单 id, 支付单 id)。"""
    mh, merchant_id = _register_active_user(client, "merchant")
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "支付一致性商品", "description": "t", "price": 30, "stock": 5},
        headers=mh,
    ).json()["data"]
    uh, buyer_id = _register_active_user(client)
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
    return mh, uh, merchant_id, buyer_id, order["id"], payment["id"]


def _callback(client: TestClient, payment_id: int, *, headers: dict) -> dict:
    resp = client.post(
        f"/api/v1/shop/payments/{payment_id}/callback",
        json={"success": True, "trade_no": f"MOCK-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _notifications(user_id: int, type_: str, *, ref_id: int | None = None) -> int:
    with SessionLocal() as db:
        stmt = select(Notification).where(
            Notification.user_id == user_id, Notification.type == type_
        )
        if ref_id is not None:
            stmt = stmt.where(Notification.ref_id == ref_id)
        return len(db.scalars(stmt).all())


def test_cancel_then_payment_becomes_awaiting_refund(client: TestClient) -> None:
    mh, uh, merchant_id, buyer_id, order_id, payment_id = _order_with_payment(client)
    admin_headers, admin_id = _admin(client)

    resp = client.post(f"/api/v1/shop/orders/{order_id}/cancel", headers=uh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == OrderStatus.CANCELLED

    # 取消后迟到的支付回调：钱已收到 → 支付单成功 + 待退款，订单保持取消
    data = _callback(client, payment_id, headers=admin_headers)
    assert data["status"] == PaymentStatus.SUCCESS
    assert data["refund_status"] == PaymentRefundStatus.PENDING
    assert data["paid_at"]

    detail = client.get(f"/api/v1/shop/orders/{order_id}", headers=uh).json()["data"]
    assert detail["status"] == OrderStatus.CANCELLED
    assert detail["payment_status"] == PaymentStatus.SUCCESS
    assert detail["payment_refund_status"] == PaymentRefundStatus.PENDING

    # 买家 / 商户 / 管理员都收到“支付异常，需退款”通知
    assert _notifications(buyer_id, NotificationType.PAYMENT_EXCEPTION) == 1
    assert _notifications(merchant_id, NotificationType.PAYMENT_EXCEPTION) == 1
    assert _notifications(admin_id, NotificationType.PAYMENT_EXCEPTION, ref_id=order_id) == 1


def test_admin_refunds_exception_payment_and_notifies(client: TestClient) -> None:
    _mh, uh, merchant_id, buyer_id, order_id, payment_id = _order_with_payment(client)
    admin_headers, _admin_id = _admin(client)
    client.post(f"/api/v1/shop/orders/{order_id}/cancel", headers=uh)
    _callback(client, payment_id, headers=admin_headers)

    resp = client.post(
        f"/api/v1/shop/payments/{payment_id}/refund",
        json={"note": "线下原路退回"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["refund_status"] == PaymentRefundStatus.REFUNDED
    assert data["refunded_at"] and data["refund_note"] == "线下原路退回"

    for user_id in (buyer_id, merchant_id):
        assert _notifications(user_id, NotificationType.PAYMENT_REFUNDED) == 1

    # 重复登记 / 非管理员 → 409 / 403
    assert (
        client.post(
            f"/api/v1/shop/payments/{payment_id}/refund", json={}, headers=admin_headers
        ).status_code
        == 409
    )
    merchant_headers = _mh
    assert (
        client.post(
            f"/api/v1/shop/payments/{payment_id}/refund", json={}, headers=merchant_headers
        ).status_code
        == 403
    )


def test_expired_order_late_payment_is_awaiting_refund(client: TestClient) -> None:
    _mh, _uh, _merchant_id, _buyer_id, order_id, payment_id = _order_with_payment(client)
    admin_headers, _admin_id = _admin(client)

    with SessionLocal() as db:
        order = db.get(Order, order_id)
        order.expire_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
        assert shop_service.expire_unpaid_orders(db) == 1

    with SessionLocal() as db:
        payment = db.get(Payment, payment_id)
        # 超时不再把支付单置 failed：支付链接可能已被打开，迟到回调要能落账退款
        assert payment.status == PaymentStatus.CREATED

    data = _callback(client, payment_id, headers=admin_headers)
    assert data["refund_status"] == PaymentRefundStatus.PENDING
    with SessionLocal() as db:
        assert db.get(Order, order_id).status == OrderStatus.CANCELLED


def test_only_one_open_payment_per_order_at_db_level(client: TestClient) -> None:
    _mh, uh, _merchant_id, buyer_id, order_id, _payment_id = _order_with_payment(client)
    # 第一张是接口建的 created；直接再插一张应触发部分唯一索引
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        db.add(
            Payment(
                order_id=order.id,
                user_id=buyer_id,
                amount=order.amount,
                status=PaymentStatus.CREATED,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:  # pragma: no cover - 索引失效时给出明确失败
            raise AssertionError("同一订单不应允许两张 created 支付单")


def test_cancel_after_payment_keeps_single_open_payment(client: TestClient) -> None:
    _mh, uh, _merchant_id, _buyer_id, order_id, payment_id = _order_with_payment(client)
    client.post(f"/api/v1/shop/orders/{order_id}/cancel", headers=uh)
    # 已取消订单不能再创建支付单
    resp = client.post(f"/api/v1/shop/orders/{order_id}/pay", headers=uh)
    assert resp.status_code == 409
    with SessionLocal() as db:
        open_count = len(
            db.scalars(
                select(Payment).where(
                    Payment.order_id == order_id, Payment.status == PaymentStatus.CREATED
                )
            ).all()
        )
    assert open_count == 1 and payment_id > 0

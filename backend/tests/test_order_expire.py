"""订单超时自动取消（N1）：到期取消、库存回补、支付单保留待退款、审计与幂等 / 并发语义。"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.admin.models import AuditLog
from app.modules.shop import repository as shop_repository
from app.modules.shop import service as shop_service
from app.modules.shop.models import (
    CancelReason,
    InventoryMovement,
    InventoryReason,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
)
from app.modules.users.models import User, UserStatus
from tests.conftest import RECEIVER


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _login(client: TestClient, phone: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _active_merchant(client: TestClient) -> str:
    """注册商户并直接置为 active（同 test_shop 的做法），返回 token。"""
    phone = _phone()
    client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": phone,
            "password": "secret123",
            "license_no": f"91{uuid.uuid4().int % 10**16:016d}",
            "role": "merchant",
        },
    )
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone))
        user.status = UserStatus.ACTIVE
        db.commit()
    return _login(client, phone)["access_token"]


def _make_order(client: TestClient) -> tuple[dict, int, int]:
    """建一个待支付订单，返回 (买家登录数据, 订单 id, 商品 id)。"""
    merchant_token = _active_merchant(client)
    resp = client.post(
        "/api/v1/shop/products",
        json={"name": "超时测试商品", "description": "测试用", "price": 10, "stock": 5},
        headers={"Authorization": f"Bearer {merchant_token}"},
    )
    assert resp.status_code == 200, resp.text
    product_id = resp.json()["data"]["id"]

    buyer_phone = _phone()
    client.post(
        "/api/v1/auth/register/tourist", json={"phone": buyer_phone, "password": "secret123"}
    )
    buyer = _login(client, buyer_phone)
    resp = client.post(
        "/api/v1/shop/orders",
        json={
            "product_id": product_id,
            "quantity": 2,
            "idem_key": uuid.uuid4().hex[:16],
            **RECEIVER,
        },
        headers={"Authorization": f"Bearer {buyer['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    return buyer, resp.json()["data"]["id"], product_id


def _expire_now(order_id: int) -> None:
    """把订单的支付截止时间拨到过去（模拟已超时）。"""
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        order.expire_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()


def _stock_of(product_id: int) -> int:
    with SessionLocal() as db:
        return db.get(Product, product_id).stock


def _order_of(order_id: int) -> Order:
    with SessionLocal() as db:
        return db.get(Order, order_id)


def test_order_gets_expire_at_on_creation(client: TestClient) -> None:
    _buyer, order_id, _product_id = _make_order(client)
    order = _order_of(order_id)
    minutes = get_settings().order_expire_minutes
    assert order.expire_at is not None
    expected = datetime.now(UTC) + timedelta(minutes=minutes)
    assert abs((order.expire_at.replace(tzinfo=UTC) - expected).total_seconds()) < 300


def test_expire_cancels_order_restores_stock_and_keeps_payment(
    client: TestClient,
) -> None:
    buyer, order_id, product_id = _make_order(client)
    assert _stock_of(product_id) == 3  # 初始 5，下单扣 2

    # 创建支付单（超时时应置为 failed）
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/pay",
        headers={"Authorization": f"Bearer {buyer['access_token']}"},
    )
    assert resp.status_code == 200, resp.text

    _expire_now(order_id)
    with SessionLocal() as db:
        expired = shop_service.expire_unpaid_orders(db)
    assert expired == 1

    order = _order_of(order_id)
    assert order.status == OrderStatus.CANCELLED
    assert order.cancel_reason == CancelReason.EXPIRED
    assert _stock_of(product_id) == 5  # 库存已回补

    with SessionLocal() as db:
        movement = db.scalar(
            select(InventoryMovement).where(
                InventoryMovement.ref_id == order_id,
                InventoryMovement.reason == InventoryReason.EXPIRE,
            )
        )
        assert movement is not None and movement.change == 2
        payment = db.scalar(select(Payment).where(Payment.order_id == order_id))
        # 支付单不置 failed：支付链接可能已被打开，迟到回调要能落 success + 待退款
        assert payment.status == PaymentStatus.CREATED
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "order.expire", AuditLog.target_id == order_id)
            .order_by(AuditLog.id.desc())
        )
        assert log is not None
        assert log.actor_id is None  # 系统动作：无操作人
        assert log.target_type == "order"


def test_expire_skips_unexpired_and_is_idempotent(client: TestClient) -> None:
    _buyer, order_id, product_id = _make_order(client)

    with SessionLocal() as db:
        assert shop_service.expire_unpaid_orders(db) == 0  # 未到期：不动
    assert _order_of(order_id).status == OrderStatus.CREATED
    assert _stock_of(product_id) == 3

    _expire_now(order_id)
    with SessionLocal() as db:
        assert shop_service.expire_unpaid_orders(db) == 1
        assert shop_service.expire_unpaid_orders(db) == 0  # 幂等：重复执行不再处理
    assert _stock_of(product_id) == 5  # 只回补一次


def test_expire_race_with_buyer_cancel_restores_once(client: TestClient) -> None:
    """超时任务与买家手动取消并发：原子条件更新只有一个生效，库存只回补一次。"""
    buyer, order_id, product_id = _make_order(client)
    _expire_now(order_id)

    # 买家先取消成功
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/cancel",
        headers={"Authorization": f"Bearer {buyer['access_token']}"},
    )
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        assert shop_service.expire_unpaid_orders(db) == 0  # 已被取消，不再处理
    order = _order_of(order_id)
    assert order.cancel_reason == CancelReason.BUYER  # 保留买家取消的语义
    assert _stock_of(product_id) == 5


def test_expired_order_returns_stock_for_future_orders(client: TestClient) -> None:
    """超时回补后库存可继续售卖（原占库存问题消除）。"""
    buyer, order_id, product_id = _make_order(client)
    _expire_now(order_id)
    with SessionLocal() as db:
        shop_service.expire_unpaid_orders(db)

    resp = client.post(
        "/api/v1/shop/orders",
        json={
            "product_id": product_id,
            "quantity": 2,
            "idem_key": uuid.uuid4().hex[:16],
            **RECEIVER,
        },
        headers={"Authorization": f"Bearer {buyer['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    assert _stock_of(product_id) == 3


def test_cancel_repository_marks_buyer_reason(client: TestClient) -> None:
    _buyer, order_id, _product_id = _make_order(client)
    with SessionLocal() as db:
        assert shop_repository.cancel_order_if_created(db, order_id, user_id=999999) is False
        order = db.get(Order, order_id)
        assert order.status == OrderStatus.CREATED  # 非本人 / 不存在：不生效
    assert _order_of(order_id).expire_at is not None


def test_worker_task_is_registered() -> None:
    """Celery 任务注册检查（不启动 worker，仅确认接线正确）。"""
    from app.worker import celery_app

    assert "shop.expire_unpaid_orders" in celery_app.tasks

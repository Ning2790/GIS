"""站内通知：业务触发（支付 / 发货 / 售后申请 / 结单）+ 列表、未读数、已读语义与归属隔离。

触发链路走真实接口（下单 → 支付回调 → 发货 / 售后），读语义用 service 直写通知，
避免每个用例都依赖完整业务链路。
"""

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import ConflictError
from app.db.session import SessionLocal
from app.modules.notifications import service as notifications_service
from app.modules.notifications.models import Notification, NotificationType
from app.modules.shop.models import Order, OrderStatus
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus
from tests.conftest import RECEIVER


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[dict, int]:
    """注册并登录一个可用账号，返回 (鉴权头, 用户 id)。"""
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


def _admin_headers(client: TestClient) -> dict[str, str]:
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


def _product(client: TestClient, headers: dict) -> dict:
    return client.post(
        "/api/v1/shop/products",
        json={"name": "通知测试商品", "description": "测试用", "price": 20, "stock": 5},
        headers=headers,
    ).json()["data"]


def _order(client: TestClient, headers: dict, product_id: int) -> dict:
    return client.post(
        "/api/v1/shop/orders",
        json={
            "product_id": product_id,
            "quantity": 1,
            "idem_key": uuid.uuid4().hex[:16],
            **RECEIVER,
        },
        headers=headers,
    ).json()["data"]


def _pay(client: TestClient, uh: dict, order_id: int) -> int:
    return client.post(f"/api/v1/shop/orders/{order_id}/pay", headers=uh).json()["data"]["id"]


def _callback(client: TestClient, payment_id: int) -> None:
    resp = client.post(
        f"/api/v1/shop/payments/{payment_id}/callback",
        json={"success": True, "trade_no": f"MOCK-{uuid.uuid4().hex[:8]}"},
        headers=_admin_headers(client),
    )
    assert resp.status_code == 200, resp.text


def _paid_order(client: TestClient) -> tuple[dict, dict, int]:
    """商户 + 买家 + 已支付订单：返回 (商户头, 买家头, 订单 id)。"""
    mh, _mid = _register_active_user(client, "merchant")
    product = _product(client, mh)
    uh, _uid = _register_active_user(client)
    order = _order(client, uh, product["id"])
    _callback(client, _pay(client, uh, order["id"]))
    return mh, uh, order["id"]


def _items(client: TestClient, headers: dict, **params: int) -> list[dict]:
    resp = client.get("/api/v1/notifications", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["items"]


def _types(client: TestClient, headers: dict) -> list[str]:
    return [item["type"] for item in _items(client, headers)]


def _unread(client: TestClient, headers: dict) -> int:
    resp = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["unread"]


def test_payment_notifies_merchant(client: TestClient) -> None:
    """支付回调成功 → 商户收到 order.paid；买家不收到。"""
    mh, _mid = _register_active_user(client, "merchant")
    product = _product(client, mh)
    uh, _uid = _register_active_user(client)
    order = _order(client, uh, product["id"])
    payment_id = _pay(client, uh, order["id"])

    # 支付前没有通知（通知与状态变更同事务）
    assert _items(client, mh) == []

    _callback(client, payment_id)

    items = _items(client, mh)
    assert len(items) == 1
    notification = items[0]
    assert notification["type"] == NotificationType.ORDER_PAID
    assert notification["ref_type"] == "order"
    assert notification["ref_id"] == order["id"]
    assert notification["is_read"] is False
    assert f"#{order['id']}" in notification["content"]
    assert _items(client, uh) == []

    # 重复回调（网关重投 / 管理员双击）→ 409，且不重复通知
    resp = client.post(
        f"/api/v1/shop/payments/{payment_id}/callback",
        json={"success": True, "trade_no": f"MOCK-{uuid.uuid4().hex[:8]}"},
        headers=_admin_headers(client),
    )
    assert resp.status_code == 409
    assert len(_items(client, mh)) == 1


def test_ship_notifies_buyer_with_tracking(client: TestClient) -> None:
    """发货 → 买家收到 order.shipped，含承运商与运单号。"""
    mh, uh, order_id = _paid_order(client)
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF1234567890"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text

    items = _items(client, uh)
    assert [item["type"] for item in items] == [NotificationType.ORDER_SHIPPED]
    assert "顺丰" in items[0]["content"] and "SF1234567890" in items[0]["content"]
    assert items[0]["ref_type"] == "order" and items[0]["ref_id"] == order_id


def test_failed_business_action_writes_no_notification(client: TestClient) -> None:
    """业务操作失败（待支付订单不能发货）→ 不产生通知。"""
    mh, _mid = _register_active_user(client, "merchant")
    product = _product(client, mh)
    uh, _uid = _register_active_user(client)
    order = _order(client, uh, product["id"])

    resp = client.post(
        f"/api/v1/shop/orders/{order['id']}/ship",
        json={"carrier": "顺丰", "tracking_no": "SF1234567890"},
        headers=mh,
    )
    assert resp.status_code == 409
    assert _items(client, uh) == []
    assert _items(client, mh) == []


def test_after_sale_created_notifies_merchant_and_resolve_notifies_buyer(
    client: TestClient,
) -> None:
    """售后申请 → 商户；处理完成 → 买家。"""
    mh, uh, order_id = _paid_order(client)
    sale = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales",
        json={"reason": "quality", "description": "包装破损"},
        headers=uh,
    ).json()["data"]

    merchant_types = _types(client, mh)
    assert NotificationType.ORDER_PAID in merchant_types
    assert NotificationType.AFTER_SALE_CREATED in merchant_types
    created = next(
        item for item in _items(client, mh) if item["type"] == NotificationType.AFTER_SALE_CREATED
    )
    assert created["ref_type"] == "after_sale" and created["ref_id"] == sale["id"]
    assert created["title"] == "新的售后申请"
    # 商户看到的是中文原因，不是 quality 之类的枚举码
    assert "质量问题" in created["content"]
    assert "quality" not in created["content"]

    # 结单前买家没有结单通知
    assert NotificationType.AFTER_SALE_RESOLVED not in _types(client, uh)

    # 完成需先受理（PENDING → PROCESSING → RESOLVED）
    client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=mh)
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/resolve",
        json={"note": "已补发一箱"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text

    items = _items(client, uh)
    assert [item["type"] for item in items] == [NotificationType.AFTER_SALE_RESOLVED]
    assert items[0]["ref_type"] == "after_sale" and items[0]["ref_id"] == sale["id"]

    # 重复结单 → 409，不重复通知
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/resolve",
        json={"note": "再次结单"},
        headers=mh,
    )
    assert resp.status_code == 409
    assert len(_items(client, uh)) == 1


def test_after_sale_rejection_notifies_buyer(client: TestClient) -> None:
    mh, uh, order_id = _paid_order(client)
    sale = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales",
        json={"reason": "quality", "description": "包装破损"},
        headers=uh,
    ).json()["data"]

    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/reject",
        json={"reason": "商品已拆封且非质量问题"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text

    items = _items(client, uh)
    assert [item["type"] for item in items] == [NotificationType.AFTER_SALE_REJECTED]
    assert items[0]["title"] == "售后被拒绝"
    assert items[0]["ref_id"] == sale["id"]


def test_list_newest_first_and_pagination(client: TestClient) -> None:
    uh, user_id = _register_active_user(client)
    with SessionLocal() as db:
        for index in range(1, 4):
            notifications_service.notify(
                db,
                user_id,
                type=NotificationType.ORDER_SHIPPED,
                title=f"通知{index}",
                content="内容",
                ref_type="order",
                ref_id=index,
            )
        db.commit()

    items = _items(client, uh)
    assert [item["title"] for item in items] == ["通知3", "通知2", "通知1"]

    resp = client.get("/api/v1/notifications", headers=uh, params={"page": 2, "page_size": 2})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 3
    assert [item["title"] for item in data["items"]] == ["通知1"]


def test_unread_count_and_mark_read_semantics(client: TestClient) -> None:
    """未读数、单条已读（幂等）、全部已读、他人通知不可操作。"""
    uh, user_id = _register_active_user(client)
    other_headers, other_id = _register_active_user(client)
    with SessionLocal() as db:
        for index in range(3):
            notifications_service.notify(
                db,
                user_id,
                type=NotificationType.ORDER_SHIPPED,
                title=f"通知{index}",
                content="内容",
            )
        notifications_service.notify(
            db, other_id, type=NotificationType.ORDER_PAID, title="别人的通知", content="内容"
        )
        db.commit()
        other_notification = db.scalar(select(Notification).where(Notification.user_id == other_id))

    assert _unread(client, uh) == 3

    # 他人通知按不存在处理
    resp = client.post(f"/api/v1/notifications/{other_notification.id}/read", headers=uh)
    assert resp.status_code == 404
    # 不存在的 id 同样 404
    assert client.post("/api/v1/notifications/99999999/read", headers=uh).status_code == 404

    # 标一条已读：未读数 -1，重复标记幂等
    target = _items(client, uh)[-1]
    resp = client.post(f"/api/v1/notifications/{target['id']}/read", headers=uh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_read"] is True
    assert _unread(client, uh) == 2
    client.post(f"/api/v1/notifications/{target['id']}/read", headers=uh)
    assert _unread(client, uh) == 2

    # 全部已读
    resp = client.post("/api/v1/notifications/read-all", headers=uh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["updated"] == 2
    assert _unread(client, uh) == 0
    assert all(item["is_read"] for item in _items(client, uh))

    # 别人的通知不受影响
    assert _unread(client, other_headers) == 1


def test_requires_login(client: TestClient) -> None:
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401
    assert client.post("/api/v1/notifications/read-all").status_code == 401
    assert client.post("/api/v1/notifications/1/read").status_code == 401


def test_notification_rows_have_ref_and_timestamp(client: TestClient) -> None:
    """通知行带关联对象与创建时间（前端跳转与时间显示依赖）。"""
    mh, _uh, order_id = _paid_order(client)
    item = _items(client, mh)[0]
    assert item["ref_type"] == "order" and item["ref_id"] == order_id
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created.tzinfo is None:  # SQLite 不保存时区
        created = created.replace(tzinfo=UTC)
    assert abs((datetime.now(UTC) - created).total_seconds()) < 300


def test_order_status_untouched_by_notification_creation(client: TestClient) -> None:
    """通知写入不改变订单状态（同事务只追加一行通知）。"""
    _mh, _uh, order_id = _paid_order(client)
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        assert order.status == OrderStatus.PAID

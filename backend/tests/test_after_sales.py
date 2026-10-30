"""售后单（N4）：申请 / 受理 / 完成 / 拒绝 / 撤销 + 双方留言 + 时限与唯一性。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.shop.models import AfterSale, AfterSaleStatus, Order, OrderStatus
from tests.conftest import RECEIVER


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录一个可用账号（商户直接置 active，同其他用例的做法）。"""
    from app.modules.users.models import User, UserStatus

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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _order(client: TestClient, *, status: str = OrderStatus.PAID) -> tuple[dict, dict, int, int]:
    """建一个订单并直接置为目标状态；返回 (商户头, 买家头, 订单 id, 商品 id)。"""
    _mp, merchant_token, _mid = _register_active_user(client, "merchant")
    mh = _headers(merchant_token)
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "售后测试商品", "description": "测试用", "price": 30, "stock": 10},
        headers=mh,
    ).json()["data"]
    _up, user_token, _uid = _register_active_user(client)
    uh = _headers(user_token)
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
    with SessionLocal() as db:
        row = db.get(Order, order["id"])
        row.status = status
        row.paid_at = datetime.now(UTC)
        if status == OrderStatus.SHIPPED:
            row.shipped_at = datetime.now(UTC)
        if status == OrderStatus.COMPLETED:
            row.completed_at = datetime.now(UTC)
        db.commit()
    return mh, uh, order["id"], product["id"]


def _apply(client: TestClient, uh: dict, order_id: int, *, reason: str = "quality") -> dict:
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales",
        json={"reason": reason, "description": "收到时包装已破损"},
        headers=uh,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_full_after_sale_flow_with_messages(client: TestClient) -> None:
    """申请 → 受理 → 双方留言 → 完成：状态流转与留言流全通。"""
    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id, reason="damaged")
    assert sale["status"] == AfterSaleStatus.PENDING
    assert sale["reason"] == "damaged"
    assert sale["order_id"] == order_id

    # 买家补充说明
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/messages",
        json={"content": "外箱有明显挤压痕迹"},
        headers=uh,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["author_role"] == "buyer"

    # 商户受理
    resp = client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=mh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == AfterSaleStatus.PROCESSING

    # 商户留言 + 完成（附说明）
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/messages",
        json={"content": "已安排补发，请留意物流"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["author_role"] == "merchant"

    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/resolve",
        json={"note": "已补发一箱，单号 SF0001112223"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == AfterSaleStatus.RESOLVED
    assert resp.json()["data"]["closed_at"]

    # 详情：留言三条（买家 + 商户 + 完成说明），订单摘要带上
    detail = client.get(f"/api/v1/shop/after-sales/{sale['id']}", headers=uh).json()["data"]
    assert len(detail["messages"]) == 3
    assert detail["order_amount"] == 30.0
    assert detail["order_status"] == OrderStatus.PAID

    # 结单后不能继续留言
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/messages",
        json={"content": "还想再说一句"},
        headers=uh,
    )
    assert resp.status_code == 409


def test_reject_requires_reason_and_records_it(client: TestClient) -> None:
    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)

    # 缺理由 → 422（请求体校验）
    assert (
        client.post(
            f"/api/v1/shop/after-sales/{sale['id']}/reject", json={}, headers=mh
        ).status_code
        == 422
    )
    # 只有空白字符 → 400
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/reject", json={"reason": "   "}, headers=mh
    )
    assert resp.status_code == 400

    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/reject",
        json={"reason": "商品已拆封且非质量问题"},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == AfterSaleStatus.REJECTED

    detail = client.get(f"/api/v1/shop/after-sales/{sale['id']}", headers=uh).json()["data"]
    assert any("【拒绝】" in item["content"] for item in detail["messages"])


def test_withdraw_only_before_accept(client: TestClient) -> None:
    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)

    # 受理后不能撤销
    client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=mh)
    resp = client.post(f"/api/v1/shop/after-sales/{sale['id']}/withdraw", headers=uh)
    assert resp.status_code == 409

    # 另一单：受理前可撤销
    _mh2, uh2, order_id2, _pid2 = _order(client)
    sale2 = _apply(client, uh2, order_id2)
    resp = client.post(f"/api/v1/shop/after-sales/{sale2['id']}/withdraw", headers=uh2)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == AfterSaleStatus.WITHDRAWN


def test_only_one_open_after_sale_per_order(client: TestClient) -> None:
    _mh, uh, order_id, _pid = _order(client)
    _apply(client, uh, order_id)
    # 第二条未结单 → 409
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales",
        json={"reason": "other"},
        headers=uh,
    )
    assert resp.status_code == 409

    # 撤销后可再发起（结单后允许）
    sale = client.get("/api/v1/shop/after-sales", headers=uh).json()["data"]["items"][0]
    client.post(f"/api/v1/shop/after-sales/{sale['id']}/withdraw", headers=uh)
    second = _apply(client, uh, order_id, reason="other")
    assert second["status"] == AfterSaleStatus.PENDING


def test_apply_requires_paid_order_and_ownership(client: TestClient) -> None:
    # 待支付订单不能申请
    mh, uh, order_id, _pid = _order(client, status=OrderStatus.CREATED)
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales", json={"reason": "quality"}, headers=uh
    )
    assert resp.status_code == 409

    # 他人订单 404
    _up2, other_token, _ = _register_active_user(client)
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales",
        json={"reason": "quality"},
        headers=_headers(other_token),
    )
    assert resp.status_code == 404

    # 非法原因 400
    _mh2, uh3, order_id3, _pid3 = _order(client)
    resp = client.post(
        f"/api/v1/shop/orders/{order_id3}/after-sales",
        json={"reason": "not-a-reason"},
        headers=uh3,
    )
    assert resp.status_code == 400


def test_completed_order_window(client: TestClient) -> None:
    """已完成订单 15 天内可申请，超期拒绝。"""
    _mh, uh, order_id, _pid = _order(client, status=OrderStatus.COMPLETED)
    # 刚完成 → 可申请
    _apply(client, uh, order_id)

    # 拨到窗口之外
    _mh2, uh2, order_id2, _pid2 = _order(client, status=OrderStatus.COMPLETED)
    window = get_settings().after_sale_window_days
    with SessionLocal() as db:
        db.execute(
            text("update orders set completed_at = :t where id = :i"),
            {"t": datetime.now(UTC) - timedelta(days=window + 1), "i": order_id2},
        )
        db.commit()
    resp = client.post(
        f"/api/v1/shop/orders/{order_id2}/after-sales", json={"reason": "quality"}, headers=uh2
    )
    assert resp.status_code == 409
    assert "售后有效期" in resp.json()["msg"]


def test_visibility_and_merchant_actions_forbidden(client: TestClient) -> None:
    """可见范围：买家自己的、订单归属商户、管理员；他人一律 404。"""
    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)

    # 买家与商户都能看详情
    assert client.get(f"/api/v1/shop/after-sales/{sale['id']}", headers=uh).status_code == 200
    assert client.get(f"/api/v1/shop/after-sales/{sale['id']}", headers=mh).status_code == 200

    # 无关第三人：详情 404、列表为空、不能留言 / 受理
    _up3, other_token, _ = _register_active_user(client)
    oh = _headers(other_token)
    assert client.get(f"/api/v1/shop/after-sales/{sale['id']}", headers=oh).status_code == 404
    assert client.get("/api/v1/shop/after-sales", headers=oh).json()["data"]["total"] == 0
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/messages", json={"content": "无关留言"}, headers=oh
    )
    assert resp.status_code == 404
    assert (
        client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=oh).status_code == 403
    )

    # 其他商户不能受理我的订单售后（角色够但订单不是他的）
    _mp4, other_merchant_token, _ = _register_active_user(client, "merchant")
    assert (
        client.post(
            f"/api/v1/shop/after-sales/{sale['id']}/accept",
            headers=_headers(other_merchant_token),
        ).status_code
        == 404
    )


def test_list_filters_and_audit(client: TestClient) -> None:
    """列表按状态过滤；关键动作入审计（after_sale.create / accept）。"""
    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)

    listing = client.get(
        "/api/v1/shop/after-sales", params={"status": "pending"}, headers=uh
    ).json()["data"]
    assert listing["total"] >= 1
    assert all(item["status"] == "pending" for item in listing["items"])

    client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=mh)
    from app.modules.admin.models import AuditLog

    with SessionLocal() as db:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.target_type == "after_sale", AuditLog.target_id == sale["id"]
                )
            ).all()
        )
    assert {"after_sale.create", "after_sale.accept"} <= actions


def test_accept_and_resolve_state_guards(client: TestClient) -> None:
    """非法状态流转：未受理不能完成、重复受理 409。"""
    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)

    assert (
        client.post(
            f"/api/v1/shop/after-sales/{sale['id']}/resolve", json={}, headers=mh
        ).status_code
        == 409
    )
    client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=mh)
    assert (
        client.post(f"/api/v1/shop/after-sales/{sale['id']}/accept", headers=mh).status_code == 409
    )
    # 受理后不能撤销、可完成
    assert (
        client.post(f"/api/v1/shop/after-sales/{sale['id']}/withdraw", headers=uh).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/shop/after-sales/{sale['id']}/resolve", json={}, headers=mh
        ).status_code
        == 200
    )


def test_atomic_transition_only_one_wins(client: TestClient) -> None:
    """原子条件更新（并发语义）：受理与撤销互斥，先到者生效、后到者不做任何改动。"""
    from app.modules.shop import repository as shop_repository

    _mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        assert shop_repository.transition_after_sale(
            db,
            sale["id"],
            from_statuses=(AfterSaleStatus.PENDING,),
            to_status=AfterSaleStatus.PROCESSING,
            now=now,
        )
        # 模拟并发对手（买家撤销）：条件已不成立 → 返回 False 且状态不变
        assert not shop_repository.transition_after_sale(
            db,
            sale["id"],
            from_statuses=(AfterSaleStatus.PENDING,),
            to_status=AfterSaleStatus.WITHDRAWN,
            close=True,
            now=now,
        )
        db.rollback()
    final = client.get(f"/api/v1/shop/after-sales/{sale['id']}", headers=uh).json()["data"]
    assert final["status"] == AfterSaleStatus.PENDING  # 回滚未提交，仍为待处理


def test_db_guards_single_open_after_sale(client: TestClient) -> None:
    """数据库层兜底（部分唯一索引 uq_after_sales_open_order）：同一订单不可能有两条未结单。

    服务层「先查后插」在并发下是 TOCTOU，靠这条索引让后到者撞唯一冲突（服务层据此回 409）。
    """
    _mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.add(
                AfterSale(
                    order_id=order_id,
                    user_id=sale["user_id"],
                    merchant_id=sale["merchant_id"],
                    reason="other",
                )
            )
            db.flush()


def test_long_reason_note_within_column_limits(client: TestClient) -> None:
    """长文本边界：请求 schema 的口径必须为入库前缀留出空间（否则 PG 上会 varchar 溢出 500）。"""
    from app.modules.shop.models import AfterSaleMessage
    from app.modules.shop.schemas import AfterSaleRejectRequest

    content_width = AfterSaleMessage.__table__.c.content.type.length
    assert content_width is not None
    max_reason = next(
        item.max_length
        for item in AfterSaleRejectRequest.model_fields["reason"].metadata
        if hasattr(item, "max_length")
    )
    assert len("【拒绝】") + max_reason <= content_width  # 拒绝理由入留言流后不溢出
    assert len("【已解决】") + max_reason <= content_width  # 完成说明同一口径
    assert 120 + len("售后 #999999 被拒绝：") <= 255  # 审计 detail 截断后不溢出

    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)
    # 超限 → 422（schema 拦下）；上限内 → 正常拒绝
    assert (
        client.post(
            f"/api/v1/shop/after-sales/{sale['id']}/reject",
            json={"reason": "长" * (max_reason + 1)},
            headers=mh,
        ).status_code
        == 422
    )
    resp = client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/reject",
        json={"reason": "长" * max_reason},
        headers=mh,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == AfterSaleStatus.REJECTED


def test_completed_without_completed_at_is_bounded(client: TestClient) -> None:
    """completed_at 缺失（历史 / 手工数据）时按兜底时间算窗口，而不是当成「刚刚完成」。"""
    _mh, uh, order_id, _pid = _order(client, status=OrderStatus.COMPLETED)
    window = get_settings().after_sale_window_days
    with SessionLocal() as db:
        db.execute(
            text(
                "update orders set completed_at = NULL, paid_at = :t, created_at = :t where id = :i"
            ),
            {"t": datetime.now(UTC) - timedelta(days=window + 5), "i": order_id},
        )
        db.commit()
    resp = client.post(
        f"/api/v1/shop/orders/{order_id}/after-sales", json={"reason": "quality"}, headers=uh
    )
    assert resp.status_code == 409
    assert "售后有效期" in resp.json()["msg"]


def test_message_insert_is_atomic_against_closure(client: TestClient) -> None:
    """留言与结单交错：条件插入在结单后不落库（而不是先读后写的窗口）。"""
    from app.modules.shop import repository as shop_repository

    mh, uh, order_id, _pid = _order(client)
    sale = _apply(client, uh, order_id)
    client.post(
        f"/api/v1/shop/after-sales/{sale['id']}/reject", json={"reason": "不接受"}, headers=mh
    )
    with SessionLocal() as db:
        row = db.get(AfterSale, sale["id"])
        created = shop_repository.add_after_sale_message_if_open(
            db,
            after_sale_id=sale["id"],
            author_id=row.user_id,
            author_role="buyer",
            content="结单后落下的留言",
            now=datetime.now(UTC),
        )
        assert created is None  # 已结单：条件插入不成立
        db.rollback()
    # 未结单时同一函数可正常写入（供 service 复用）
    _mh2, uh2, order_id2, _pid2 = _order(client)
    sale2 = _apply(client, uh2, order_id2)
    with SessionLocal() as db:
        row2 = db.get(AfterSale, sale2["id"])
        created2 = shop_repository.add_after_sale_message_if_open(
            db,
            after_sale_id=sale2["id"],
            author_id=row2.user_id,
            author_role="buyer",
            content="未结单时的正常留言",
            now=datetime.now(UTC),
        )
        assert created2 is not None and created2.content == "未结单时的正常留言"
        db.rollback()

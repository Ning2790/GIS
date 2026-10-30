"""支付网关适配层（N13）测试：协议契约 + 占位实现 + 回调落地路径。

验收判据是「现有行为零变化」——原有支付用例（`tests/test_shop.py::test_payment_flow` 等）
继续全绿即是证据；这里补适配层自身的单测。
"""

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.modules.shop import payment_gateway, service


def test_mock_gateway_contract() -> None:
    """占位网关的契约：单号编码本地支付单 id、无支付链接、无签名可验。"""
    gateway = payment_gateway.get_gateway()
    assert gateway.name == "mock"

    created = gateway.create_payment(
        payment_id=42, order_id=7, amount=Decimal("88.00"), subject="平台订单 #7"
    )
    assert created.out_trade_no == "mock-42"
    assert created.pay_url is None
    assert payment_gateway.payment_id_from_out_trade_no(created.out_trade_no) == 42

    assert gateway.verify_notify(headers={}, body=b"{}") is True


def test_parse_notify_normalizes_fields() -> None:
    """回调解析把第三方字段归一成 (本地单号 / 流水号 / 成败)。"""
    gateway = payment_gateway.get_gateway()
    body = json.dumps(
        {"out_trade_no": "mock-9", "success": True, "trade_no": "SF-TRADE-1"}
    ).encode()
    notify = gateway.parse_notify(headers={"x-sign": "ignored"}, body=body)
    assert notify.out_trade_no == "mock-9"
    assert notify.success is True
    assert notify.trade_no == "SF-TRADE-1"


@pytest.mark.parametrize("body", [b"not-json", b'["list"]', b'{"success": true}'])
def test_parse_notify_rejects_bad_payload(body: bytes) -> None:
    """坏报文（非 JSON / 非对象 / 缺 out_trade_no）按 400 语义拒绝。"""
    from app.core.errors import BadRequestError

    gateway = payment_gateway.get_gateway()
    with pytest.raises(BadRequestError):
        gateway.parse_notify(headers={}, body=body)


def test_unknown_gateway_name_fails_loudly(monkeypatch) -> None:
    """未知网关名直接报错（不静默退回 mock，避免生产误用占位实现）。"""
    monkeypatch.setattr(get_settings(), "payment_gateway", "alipay", raising=False)
    with pytest.raises(RuntimeError, match="PAYMENT_GATEWAY"):
        payment_gateway.get_gateway()


def test_gateway_notify_settles_payment(client: TestClient) -> None:
    """网关回调落地：验签（mock 恒真）→ 解析 → 本地支付单置成功、订单置已支付。"""
    from app.core.errors import ConflictError
    from app.db.session import SessionLocal
    from tests.conftest import RECEIVER
    from tests.test_shop import _create_product, _register_active_user

    _mp, m_token, _mid = _register_active_user(client, "merchant")
    merchant_headers = {"Authorization": f"Bearer {m_token}"}
    product = _create_product(client, merchant_headers, "网关测试雪菊", 30.0, 5)

    _bp, b_token, _bid = _register_active_user(client)
    headers = {"Authorization": f"Bearer {b_token}"}
    order = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1, **RECEIVER},
        headers=headers,
    ).json()["data"]

    payment = client.post(f"/api/v1/shop/orders/{order['id']}/pay", headers=headers).json()["data"]
    assert payment["pay_url"] is None  # mock 网关没有支付链接

    body = json.dumps(
        {"out_trade_no": f"mock-{payment['id']}", "success": True, "trade_no": "TRADE-XYZ"}
    ).encode()
    with SessionLocal() as db:
        settled = service.handle_gateway_notify(db, headers={}, body=body)
        assert settled.status == "success" and settled.trade_no == "TRADE-XYZ"

    detail = client.get(f"/api/v1/shop/orders/{order['id']}", headers=headers).json()["data"]
    assert detail["status"] == "paid" and detail["payment_status"] == "success"

    # 重复回调：已处理的支付单按既有语义 409（幂等防线不变）
    with SessionLocal() as db:
        with pytest.raises(ConflictError):
            service.handle_gateway_notify(db, headers={}, body=body)


def test_notify_with_unknown_out_trade_no_is_rejected(client: TestClient) -> None:
    """回调单号定位不到本地支付单 → 404（而不是静默忽略）。"""
    from app.core.errors import NotFoundError
    from app.db.session import SessionLocal

    body = json.dumps({"out_trade_no": "alipay-unknown-1", "success": True}).encode()
    with SessionLocal() as db:
        with pytest.raises(NotFoundError):
            service.handle_gateway_notify(db, headers={}, body=body)

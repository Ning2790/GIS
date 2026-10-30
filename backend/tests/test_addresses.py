"""收货地址簿与订单收货信息快照（N2）：CRUD / 默认地址 / 越权 / 快照不可变。"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from tests.conftest import RECEIVER


def _phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _token(client: TestClient) -> tuple[str, str]:
    """注册并登录一个游客，返回 (手机号, token)。"""
    phone = _phone()
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return phone, resp.json()["data"]["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _addresses(client: TestClient, token: str) -> list[dict]:
    resp = client.get("/api/v1/users/addresses", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _add(client: TestClient, token: str, name: str, *, is_default: bool = False) -> dict:
    resp = client.post(
        "/api/v1/users/addresses",
        json={
            "receiver_name": name,
            "receiver_phone": "13800000001",
            "address": f"青海省西宁市城西区{name}路 1 号",
            "is_default": is_default,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_address_crud_and_default_switch(client: TestClient) -> None:
    _phone_a, token = _token(client)

    first = _add(client, token, "甲")
    assert first["is_default"] is True  # 首个地址自动为默认

    second = _add(client, token, "乙")
    assert second["is_default"] is False
    assert _addresses(client, token)[0]["id"] == first["id"]  # 默认排最前

    # 设为默认：默认标记唯一
    resp = client.post(f"/api/v1/users/addresses/{second['id']}/default", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    rows = _addresses(client, token)
    assert [r["is_default"] for r in rows] == [True, False]
    assert rows[0]["id"] == second["id"]

    # 更新
    resp = client.put(
        f"/api/v1/users/addresses/{second['id']}",
        json={
            "receiver_name": "乙（改）",
            "receiver_phone": "13900000002",
            "address": "青海省海东市乐都区测试路 9 号",
            "is_default": True,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["receiver_name"] == "乙（改）"

    # 删除默认地址：剩下的地址自动补为默认
    resp = client.delete(f"/api/v1/users/addresses/{second['id']}", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    rows = _addresses(client, token)
    assert len(rows) == 1 and rows[0]["is_default"] is True


def test_address_ownership_and_validation(client: TestClient) -> None:
    _phone_a, token_a = _token(client)
    _phone_b, token_b = _token(client)
    mine = _add(client, token_a, "甲")

    # 他人地址：读取 / 修改 / 删除均 404（不泄漏存在性）
    for method, url, body in (
        (
            "put",
            f"/api/v1/users/addresses/{mine['id']}",
            {
                "receiver_name": "x",
                "receiver_phone": "13800000001",
                "address": "青海省西宁市城西区路 1 号",
            },
        ),
        ("delete", f"/api/v1/users/addresses/{mine['id']}", None),
    ):
        if method == "put":
            resp = client.put(url, json=body, headers=_headers(token_b))
        else:
            resp = client.delete(url, headers=_headers(token_b))
        assert resp.status_code == 404, resp.text
    # 自己的默认地址未被他人改动
    assert _addresses(client, token_a)[0]["is_default"] is True

    # 校验：手机号格式 / 地址过短
    resp = client.post(
        "/api/v1/users/addresses",
        json={"receiver_name": "丙", "receiver_phone": "12345", "address": "青海省西宁市"},
        headers=_headers(token_a),
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/v1/users/addresses",
        json={"receiver_name": "丙", "receiver_phone": "13800000003", "address": "短"},
        headers=_headers(token_a),
    )
    assert resp.status_code == 422


def test_address_limit(client: TestClient) -> None:
    _phone_a, token = _token(client)
    for index in range(20):
        _add(client, token, f"地址{index}")
    resp = client.post(
        "/api/v1/users/addresses",
        json={
            "receiver_name": "超额",
            "receiver_phone": "13800000009",
            "address": "青海省西宁市城西区超额路 1 号",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 400
    assert "最多保存 20 个" in resp.json()["msg"]


def test_order_snapshots_receiver_and_ignores_later_address_change(client: TestClient) -> None:
    """下单把收货信息快照进订单；之后改地址不影响历史订单。"""
    phone, token = _token(client)
    # 商户 + 商品
    merchant_phone = _phone()
    client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": merchant_phone,
            "password": "secret123",
            "license_no": f"91{uuid.uuid4().int % 10**16:016d}",
            "role": "merchant",
        },
    )
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.modules.users.models import User, UserStatus

    with SessionLocal() as db:
        merchant = db.scalar(select(User).where(User.phone == merchant_phone))
        merchant.status = UserStatus.ACTIVE
        db.commit()
    merchant_token = client.post(
        "/api/v1/auth/login", json={"phone": merchant_phone, "password": "secret123"}
    ).json()["data"]["access_token"]
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "快照测试商品", "description": "测试", "price": 9.9, "stock": 3},
        headers=_headers(merchant_token),
    ).json()["data"]

    address = _add(client, token, "快照")
    resp = client.post(
        "/api/v1/shop/orders",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "idem_key": uuid.uuid4().hex[:16],
            "receiver_name": address["receiver_name"],
            "receiver_phone": address["receiver_phone"],
            "receiver_address": address["address"],
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()["data"]
    assert order["receiver_name"] == "快照"
    assert order["receiver_phone"] == "13800000001"
    assert order["receiver_address"] == address["address"]

    # 之后改地址：订单里的快照不动
    client.put(
        f"/api/v1/users/addresses/{address['id']}",
        json={
            "receiver_name": "改后",
            "receiver_phone": "13700000000",
            "address": "青海省海北州海晏县新路 5 号",
            "is_default": True,
        },
        headers=_headers(token),
    )
    detail = client.get(f"/api/v1/shop/orders/{order['id']}", headers=_headers(token)).json()[
        "data"
    ]
    assert detail["receiver_name"] == "快照"
    assert detail["receiver_address"] == address["address"]


def test_order_requires_receiver_info(client: TestClient) -> None:
    """新订单必填收货信息（缺字段 422）。"""
    _phone_a, token = _token(client)
    merchant_phone = _phone()
    client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": merchant_phone,
            "password": "secret123",
            "license_no": f"91{uuid.uuid4().int % 10**16:016d}",
            "role": "merchant",
        },
    )
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.modules.users.models import User, UserStatus

    with SessionLocal() as db:
        merchant = db.scalar(select(User).where(User.phone == merchant_phone))
        merchant.status = UserStatus.ACTIVE
        db.commit()
    merchant_token = client.post(
        "/api/v1/auth/login", json={"phone": merchant_phone, "password": "secret123"}
    ).json()["data"]["access_token"]
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "缺收货信息商品", "description": "测试", "price": 1, "stock": 3},
        headers=_headers(merchant_token),
    ).json()["data"]

    resp = client.post(
        "/api/v1/shop/orders",
        json={"product_id": product["id"], "quantity": 1},
        headers=_headers(token),
    )
    assert resp.status_code == 422

    # 手机号格式不合法同样拒绝
    resp = client.post(
        "/api/v1/shop/orders",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "receiver_name": "甲",
            "receiver_phone": "123",
            "receiver_address": "青海省西宁市城西区路 1 号",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_checkout_requires_receiver_info(client: TestClient) -> None:
    """购物车结算同样必填（缺少收货信息 422）；带齐则成功。"""
    _phone_a, token = _token(client)
    resp = client.post(
        "/api/v1/shop/cart/checkout",
        json={"idem_key": uuid.uuid4().hex[:16]},
        headers=_headers(token),
    )
    assert resp.status_code == 422

    merchant_phone = _phone()
    client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": merchant_phone,
            "password": "secret123",
            "license_no": f"91{uuid.uuid4().int % 10**16:016d}",
            "role": "merchant",
        },
    )
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.modules.users.models import User, UserStatus

    with SessionLocal() as db:
        merchant = db.scalar(select(User).where(User.phone == merchant_phone))
        merchant.status = UserStatus.ACTIVE
        db.commit()
    merchant_token = client.post(
        "/api/v1/auth/login", json={"phone": merchant_phone, "password": "secret123"}
    ).json()["data"]["access_token"]
    product = client.post(
        "/api/v1/shop/products",
        json={"name": "结算地址测试", "description": "测试", "price": 3, "stock": 5},
        headers=_headers(merchant_token),
    ).json()["data"]
    client.post(
        "/api/v1/shop/cart/items",
        json={"product_id": product["id"], "quantity": 1},
        headers=_headers(token),
    )
    resp = client.post(
        "/api/v1/shop/cart/checkout",
        json={"idem_key": uuid.uuid4().hex[:16], **RECEIVER},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["receiver_name"] == RECEIVER["receiver_name"]


def test_db_guards_single_default_address(client: TestClient) -> None:
    """数据库层兜底（偏唯一索引 uq_user_addresses_default）：一个用户不可能有两个默认地址。

    服务层的「清旧默认 → 置新默认」在并发下会出现写偏斜（两个事务各留一个默认），
    这条索引让后提交者撞唯一冲突，服务层据此回滚重试或返回 409。
    """
    _phone_a, token = _token(client)
    _add(client, token, "甲")  # 首个自动为默认
    second = _add(client, token, "乙")

    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE user_addresses SET is_default = true WHERE id = :i"),
                {"i": second["id"]},
            )

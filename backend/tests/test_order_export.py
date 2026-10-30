"""订单导出（CSV）与销量看板测试。

数据直接用 ORM 构造（聚合与导出只读行，不必走完整下单链路），断言重点：
导出内容与筛选（状态 / 时间区间 / 时区）、CSV 安全（公式注入 / BOM）、权限隔离、
截断标记，以及看板口径（仅已支付及之后、按支付时间落桶、补齐无成交日）。
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.modules.shop import service as shop_service
from app.modules.shop.models import Order, OrderItem, OrderStatus
from app.modules.users.models import User, UserRole, UserStatus

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _user(role: str, *, status: str = UserStatus.ACTIVE) -> int:
    with SessionLocal() as db:
        user = User(
            phone="136" + "".join("012345"[(ord(char) % 6)] for char in uuid.uuid4().hex[:8]),
            password_hash="x",
            role=role,
            status=status,
            nickname=f"{role}-报告用例",
        )
        db.add(user)
        db.commit()
        return user.id


def _auth(client: TestClient, user_id: int) -> dict[str, str]:
    """直接签一个访问令牌（测试不关心登录流程，只要鉴权头）。"""
    from app.core.security import create_access_token

    with SessionLocal() as db:
        user = db.get(User, user_id)
        token = create_access_token(str(user_id), user.role)
    return {"Authorization": f"Bearer {token}"}


def _order(
    *,
    user_id: int,
    merchant_id: int,
    amount: float,
    status: str,
    created_at: datetime | None = None,
    paid_at: datetime | None = None,
    item_name: str = "祁连山牦牛肉干",
    product_id: int = 1,
    quantity: int = 2,
    receiver_name: str = "测试收货人",
    receiver_address: str = "青海省西宁市城西区测试路 1 号",
) -> int:
    created = created_at or datetime.now(UTC)
    if paid_at is None and status in OrderStatus.PAID_STATUSES:
        paid_at = created
    with SessionLocal() as db:
        order = Order(
            user_id=user_id,
            merchant_id=merchant_id,
            amount=Decimal(str(amount)),
            status=status,
            receiver_name=receiver_name,
            receiver_phone="13800000000",
            receiver_address=receiver_address,
            idem_key=uuid.uuid4().hex,
            created_at=created,
            paid_at=paid_at,
        )
        db.add(order)
        db.flush()
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product_id,
                product_name=item_name,
                unit_price=Decimal(str(amount / quantity)),
                quantity=quantity,
                amount=Decimal(str(amount)),
            )
        )
        db.commit()
        return order.id


def _export(client: TestClient, headers: dict, query: str = "") -> tuple[bytes, object]:
    resp = client.get(f"/api/v1/shop/merchant/orders/export{query}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.content, resp


def _ids_in(body: str) -> set[int]:
    """CSV 第一列为订单号（表头除外）。"""
    lines = body.strip().splitlines()[1:]
    return {int(line.split(",")[0].strip("'")) for line in lines if line}


def test_export_csv_for_merchant(client: TestClient) -> None:
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    other_merchant = _user(UserRole.MERCHANT)
    created = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    paid_id = _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=200,
        status=OrderStatus.PAID,
        created_at=created,
    )
    created_id = _order(user_id=buyer, merchant_id=merchant, amount=50, status=OrderStatus.CREATED)
    other_id = _order(
        user_id=buyer, merchant_id=other_merchant, amount=999, status=OrderStatus.PAID
    )

    content, resp = _export(client, _auth(client, merchant))
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["x-export-rows"] == "2"
    assert resp.headers["x-export-truncated"] == "false"

    # UTF-8 BOM：Excel 双击打开不乱码；分块发送只能有一个 BOM
    assert content.startswith(b"\xef\xbb\xbf")
    assert content.count(b"\xef\xbb\xbf") == 1
    body = content.decode("utf-8-sig")
    lines = body.strip().splitlines()
    assert lines[0].startswith("订单号,状态,金额,买家ID,商户ID,商户名称")
    assert "创建时间（北京时间）" in lines[0]
    assert "merchant-报告用例" in body
    assert len(lines) == 3
    assert _ids_in(body) == {paid_id, created_id}
    assert other_id not in _ids_in(body)
    assert "待支付" in body and "已支付" in body
    assert "测试收货人" in body and "祁连山牦牛肉干×2" in body
    # 导出时间按北京时间输出（数据库存 UTC，12:00Z → 20:00 北京）
    assert "2026-01-10 20:00:00" in body


def test_export_csv_filters_and_timezone(client: TestClient) -> None:
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    noon_utc = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    inside = _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=100,
        status=OrderStatus.PAID,
        created_at=noon_utc,
    )
    _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=30,
        status=OrderStatus.CREATED,
        created_at=noon_utc + timedelta(days=2),
    )
    headers = _auth(client, merchant)

    # 状态筛选
    body = _export(client, headers, "?status=paid")[0].decode("utf-8-sig")
    assert _ids_in(body) == {inside}
    assert "待支付" not in body

    # 时间区间：带 +08:00 偏移（11:00Z–13:00Z 覆盖 12:00Z）
    body = _export(
        client,
        headers,
        "?start=2026-01-10T19:00:00%2B08:00&end=2026-01-10T21:00:00%2B08:00",
    )[0].decode("utf-8-sig")
    assert _ids_in(body) == {inside}
    # 区间外（14:00Z–15:00Z）不含
    body = _export(
        client,
        headers,
        "?start=2026-01-10T22:00:00%2B08:00&end=2026-01-10T23:00:00%2B08:00",
    )[0].decode("utf-8-sig")
    assert _ids_in(body) == set()
    # naive 入参按业务时区（Asia/Shanghai）解释：20:00 本地 == 12:00Z，含端点
    body = _export(client, headers, "?start=2026-01-10T20:00:00&end=2026-01-10T20:00:00")[0].decode(
        "utf-8-sig"
    )
    assert _ids_in(body) == {inside}
    # 纯日期 end 等价于上海当天 00:00（要覆盖全天需传 23:59:59）
    body = _export(client, headers, "?end=2026-01-10")[0].decode("utf-8-sig")
    assert _ids_in(body) == set()

    # 非法状态 / 起止倒置 → 400 级错误
    assert (
        client.get("/api/v1/shop/merchant/orders/export?status=oops", headers=headers).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/shop/merchant/orders/export?start=2026-01-11T00:00:00&end=2026-01-10T00:00:00",
            headers=headers,
        ).status_code
        == 400
    )
    # 极端年份跨时区换算会 OverflowError：必须是 400 而不是 500
    for query in (
        "?start=0001-01-01T00:00:00%2B08:00",
        "?end=9999-12-31T23:59:59-12:00",
        "?start=0001-01-01",
    ):
        assert (
            client.get(f"/api/v1/shop/merchant/orders/export{query}", headers=headers).status_code
            == 400
        )

    # 游客导出 → 403
    tourist = _user(UserRole.TOURIST)
    assert (
        client.get(
            "/api/v1/shop/merchant/orders/export", headers=_auth(client, tourist)
        ).status_code
        == 403
    )


def test_export_csv_scope_admin_and_other_merchant(client: TestClient) -> None:
    merchant_a = _user(UserRole.MERCHANT)
    merchant_b = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    admin = _user(UserRole.ADMIN)
    a_paid = _order(user_id=buyer, merchant_id=merchant_a, amount=11, status=OrderStatus.PAID)
    b_paid = _order(user_id=buyer, merchant_id=merchant_b, amount=22, status=OrderStatus.PAID)

    # 商户 A 只见自己
    assert _ids_in(_export(client, _auth(client, merchant_a))[0].decode("utf-8-sig")) == {a_paid}
    # 管理员看全平台（其它用例订单也会出现，用包含断言）；CSV 带商户 ID / 名称
    admin_body = _export(client, _auth(client, admin))[0].decode("utf-8-sig")
    assert {a_paid, b_paid} <= _ids_in(admin_body)
    assert str(merchant_a) in admin_body and str(merchant_b) in admin_body


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_export_csv_formula_injection_is_escaped(client: TestClient, prefix: str) -> None:
    """收货人 / 地址以公式前缀开头时前置单引号，Excel 不会当公式执行。"""
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=10,
        status=OrderStatus.PAID,
        receiver_name=f"{prefix}恶意公式",
        receiver_address="@SUM(1,1)",
    )
    body = _export(client, _auth(client, merchant))[0].decode("utf-8-sig")
    assert f"'{prefix}恶意公式" in body
    assert "'@SUM(1,1)" in body


def test_export_csv_multi_batch_streaming(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """跨多批游标导出：行数完整、BOM 只出现一次、中文跨块可解码。"""
    monkeypatch.setattr(shop_service, "_EXPORT_MAX_ROWS", 7)
    monkeypatch.setattr(shop_service, "_EXPORT_BATCH", 3)
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    ids = set()
    for index in range(7):
        ids.add(
            _order(
                user_id=buyer,
                merchant_id=merchant,
                amount=10 + index,
                status=OrderStatus.PAID,
                created_at=datetime(2026, 1, 10, 12, index, tzinfo=UTC),
            )
        )
    content, resp = _export(client, _auth(client, merchant))
    assert resp.headers["x-export-rows"] == "7"
    assert resp.headers["x-export-truncated"] == "false"
    assert content.count(b"\xef\xbb\xbf") == 1
    body = content.decode("utf-8-sig")
    assert len(body.strip().splitlines()) == 8  # 表头 + 7 单
    assert _ids_in(body) == ids


def test_export_csv_truncation_header(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shop_service, "_EXPORT_MAX_ROWS", 5)
    monkeypatch.setattr(shop_service, "_EXPORT_BATCH", 2)
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    ids = []
    for index in range(7):
        ids.append(
            _order(
                user_id=buyer,
                merchant_id=merchant,
                amount=10 + index,
                status=OrderStatus.PAID,
                created_at=datetime(2026, 1, 10, 12, index, tzinfo=UTC),
            )
        )
    content, resp = _export(client, _auth(client, merchant))
    assert resp.headers["x-export-rows"] == "5"
    assert resp.headers["x-export-truncated"] == "true"
    body = content.decode("utf-8-sig")
    assert len(body.strip().splitlines()) == 6  # 表头 + 5 单
    # 截断时优先导出最新订单（id 倒序）
    assert _ids_in(body) == set(ids[-5:])


def test_sales_overview_merchant_and_admin(client: TestClient) -> None:
    merchant_a = _user(UserRole.MERCHANT)
    merchant_b = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    admin = _user(UserRole.ADMIN)
    now = datetime.now(UTC)
    _order(
        user_id=buyer,
        merchant_id=merchant_a,
        amount=200,
        status=OrderStatus.PAID,
        created_at=now,
        item_name="祁连山牦牛肉干",
        quantity=2,
    )
    _order(
        user_id=buyer,
        merchant_id=merchant_a,
        amount=88,
        status=OrderStatus.SHIPPED,
        created_at=now - timedelta(days=1),
        item_name="青海雪菊",
        product_id=2,
        quantity=1,
    )
    # 待支付不计入成交口径；别的商户不算
    _order(user_id=buyer, merchant_id=merchant_a, amount=999, status=OrderStatus.CREATED)
    _order(user_id=buyer, merchant_id=merchant_b, amount=500, status=OrderStatus.PAID)

    data = client.get(
        "/api/v1/shop/merchant/sales-overview?days=14", headers=_auth(client, merchant_a)
    ).json()["data"]
    assert data["days"] == 14
    assert len(data["series"]) == 14  # 无成交日也补齐
    dates = [item["date"] for item in data["series"]]
    assert dates == sorted(dates)
    assert dates[-1] == datetime.now(SHANGHAI).date().isoformat()
    assert sum(item["orders"] for item in data["series"]) == 2
    assert abs(sum(item["revenue"] for item in data["series"]) - 288.0) < 0.01
    names = [item["name"] for item in data["top_products"]]
    assert "祁连山牦牛肉干" in names and "青海雪菊" in names
    assert "999" not in str(data)

    admin_data = client.get(
        "/api/v1/shop/merchant/sales-overview?days=14", headers=_auth(client, admin)
    ).json()["data"]
    assert sum(item["orders"] for item in admin_data["series"]) >= 3
    assert sum(item["revenue"] for item in admin_data["series"]) >= 788.0  # 288 + 500

    tourist = _user(UserRole.TOURIST)
    assert (
        client.get(
            "/api/v1/shop/merchant/sales-overview", headers=_auth(client, tourist)
        ).status_code
        == 403
    )


def test_sales_overview_uses_paid_at_and_business_tz(client: TestClient) -> None:
    """趋势按支付时间落桶：早下单晚支付计入支付日；按商品 ID 聚合不合并同名商品。"""
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    now = datetime.now(UTC)
    today_start = datetime.combine(datetime.now(SHANGHAI).date(), time.min, tzinfo=SHANGHAI)
    # 30 天前下单、今天支付 → 计入今天
    _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=120,
        status=OrderStatus.PAID,
        created_at=now - timedelta(days=30),
        paid_at=now,
        item_name="同名商品",
        product_id=101,
        quantity=1,
    )
    # 同一商品今天早些时候支付：按商品 ID 聚合成一行
    _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=80,
        status=OrderStatus.PAID,
        created_at=now,
        paid_at=today_start.astimezone(UTC) + timedelta(minutes=1),
        item_name="同名商品",
        product_id=101,
        quantity=1,
    )
    # 同名不同商品：两行（不按名称合并）
    _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=50,
        status=OrderStatus.PAID,
        created_at=now,
        paid_at=now,
        item_name="同名商品",
        product_id=102,
        quantity=1,
    )

    data = client.get(
        "/api/v1/shop/merchant/sales-overview?days=1", headers=_auth(client, merchant)
    ).json()["data"]
    assert len(data["series"]) == 1
    assert data["series"][0]["orders"] == 3  # 三单都在今天支付
    assert abs(data["series"][0]["revenue"] - 250.0) < 0.01
    assert len(data["top_products"]) == 2  # 同名的两个商品各一行
    assert [item["quantity"] for item in data["top_products"]] == [2, 1]


def test_sales_overview_counts_paid_orders_without_paid_at(client: TestClient) -> None:
    """历史 / 手工数据 paid_at 为空：回退到创建时间，不从成交口径消失。"""
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    order_id = _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=66,
        status=OrderStatus.PAID,
        created_at=datetime.now(UTC),
    )
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        order.paid_at = None
        db.commit()

    data = client.get(
        "/api/v1/shop/merchant/sales-overview?days=1", headers=_auth(client, merchant)
    ).json()["data"]
    assert data["series"][-1]["orders"] == 1
    assert abs(data["series"][-1]["revenue"] - 66.0) < 0.01
    assert data["top_products"][0]["name"] == "祁连山牦牛肉干"


def test_export_iso_uses_business_timezone() -> None:
    """导出时间统一北京时间：aware 先换算 UTC；naive 按 UTC 读回。"""
    aware = datetime(2026, 1, 10, 20, 0, tzinfo=SHANGHAI)
    assert shop_service._iso(aware) == "2026-01-10 20:00:00"
    assert shop_service._iso(datetime(2026, 1, 10, 12, 0)) == "2026-01-10 20:00:00"


def test_dashboard_today_revenue_matches_board(client: TestClient) -> None:
    """概览卡「今日成交额」与看板最后一根柱子口径一致（同一业务日界）。"""
    merchant = _user(UserRole.MERCHANT)
    buyer = _user(UserRole.TOURIST)
    _order(
        user_id=buyer,
        merchant_id=merchant,
        amount=77,
        status=OrderStatus.PAID,
        created_at=datetime.now(UTC),
    )
    headers = _auth(client, merchant)
    summary = client.get("/api/v1/dashboard/summary", headers=headers).json()["data"]
    board = client.get("/api/v1/shop/merchant/sales-overview?days=1", headers=headers).json()[
        "data"
    ]
    assert summary["today_revenue"] == 77.0
    assert board["series"][-1]["revenue"] == 77.0


def test_openapi_declares_csv_400_and_error_envelope() -> None:
    """契约与实现对齐：导出 400 已声明，422 使用统一 {code,msg,data} 信封。"""
    from app.main import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/shop/merchant/orders/export"]["get"]
    assert set(operation["responses"]) >= {"200", "400", "422"}
    assert "text/csv" in operation["responses"]["200"]["content"]
    ref = operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ErrorEnvelope")
    assert "ErrorEnvelope" in schema["components"]["schemas"]
    # 其它接口的 422 也统一成信封（抽查一个请求体接口）
    other = schema["paths"]["/api/v1/auth/login"]["post"]["responses"]["422"]
    assert other["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorEnvelope")

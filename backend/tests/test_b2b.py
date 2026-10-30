"""b2b 模块：供需发布、公开浏览与规则匹配测试。"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.b2b.models import B2bMatch
from app.modules.users.models import User, UserStatus


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录一个可用用户（商户 / 企业直接置为 active，同其它测试的做法）。"""
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


def _publish_supply(
    client: TestClient,
    headers: dict,
    *,
    title: str,
    category: str,
    region: str,
    quantity: float,
) -> dict:
    resp = client.post(
        "/api/v1/b2b/supplies",
        json={
            "title": title,
            "category": category,
            "region": region,
            "quantity": quantity,
            "unit": "吨",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_publish_requires_publisher_role(client: TestClient) -> None:
    payload = {"title": "x", "category": "c", "region": "r", "quantity": 1}
    assert client.post("/api/v1/b2b/supplies", json=payload).status_code == 401

    _p, token, _u = _register_active_user(client)
    resp = client.post(
        "/api/v1/b2b/supplies", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


def test_public_browse_filters_and_close(client: TestClient) -> None:
    _mp, token, _u = _register_active_user(client, "merchant")
    headers = {"Authorization": f"Bearer {token}"}
    supply_a = _publish_supply(
        client, headers, title="海北油菜籽", category="测试油菜籽", region="海北州", quantity=50
    )
    _publish_supply(
        client, headers, title="柴达木枸杞", category="测试枸杞", region="海西州", quantity=10
    )

    # 公开浏览（无 token）
    resp = client.get("/api/v1/b2b/supplies?page=1&page_size=10")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] >= 2

    resp = client.get("/api/v1/b2b/supplies", params={"category": "测试油菜籽"})
    assert all(item["category"] == "测试油菜籽" for item in resp.json()["data"]["items"])

    resp = client.get("/api/v1/b2b/supplies", params={"keyword": "柴达木"})
    assert resp.json()["data"]["total"] == 1

    assert client.get(f"/api/v1/b2b/supplies/{supply_a['id']}").status_code == 200

    # 非发布者不能关闭
    _op, other_token, _o = _register_active_user(client, "merchant")
    resp = client.post(
        f"/api/v1/b2b/supplies/{supply_a['id']}/close",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403

    # 发布者关闭 → 列表不再出现
    resp = client.post(f"/api/v1/b2b/supplies/{supply_a['id']}/close", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "closed"
    resp = client.get("/api/v1/b2b/supplies", params={"category": "测试油菜籽"})
    assert all(item["id"] != supply_a["id"] for item in resp.json()["data"]["items"])


def test_match_rules_and_persistence(client: TestClient) -> None:
    _sp, supplier_token, _su = _register_active_user(client, "merchant")
    supplier_headers = {"Authorization": f"Bearer {supplier_token}"}
    good = _publish_supply(
        client,
        supplier_headers,
        title="测试品类 20 吨",
        category="测试撮合品类",
        region="海北州",
        quantity=20,
    )
    partial = _publish_supply(
        client,
        supplier_headers,
        title="测试品类 5 吨",
        category="测试撮合品类",
        region="海西州",
        quantity=5,
    )
    other_category = _publish_supply(
        client,
        supplier_headers,
        title="其他品类",
        category="测试其他品类",
        region="海北州",
        quantity=100,
    )

    _dp, demand_token, _du = _register_active_user(client, "enterprise")
    demand_headers = {"Authorization": f"Bearer {demand_token}"}
    resp = client.post(
        "/api/v1/b2b/demands",
        json={
            "title": "求购测试品类",
            "category": "测试撮合品类",
            "region": "海北州",
            "quantity": 10,
        },
        headers=demand_headers,
    )
    assert resp.status_code == 200, resp.text
    demand = resp.json()["data"]

    # 非发布者不能匹配 / 查看匹配
    resp = client.post(f"/api/v1/b2b/demands/{demand['id']}/match", headers=supplier_headers)
    assert resp.status_code == 403

    # 规则匹配：品类一致才入选；地区一致 +20、数量满足 +20
    resp = client.post(f"/api/v1/b2b/demands/{demand['id']}/match", headers=demand_headers)
    assert resp.status_code == 200, resp.text
    matches = resp.json()["data"]["matches"]
    assert [item["supply"]["id"] for item in matches] == [good["id"], partial["id"]]
    assert [item["score"] for item in matches] == [100, 60]
    assert all(item["supply"]["id"] != other_category["id"] for item in matches)

    # 重复匹配为替换而非追加
    resp = client.post(f"/api/v1/b2b/demands/{demand['id']}/match", headers=demand_headers)
    assert len(resp.json()["data"]["matches"]) == 2
    with SessionLocal() as db:
        rows = db.scalars(select(B2bMatch).where(B2bMatch.demand_id == demand["id"])).all()
        assert len(rows) == 2

    resp = client.get(f"/api/v1/b2b/demands/{demand['id']}/matches", headers=demand_headers)
    assert [item["score"] for item in resp.json()["data"]["matches"]] == [100, 60]

    # 关闭一条供给后重新匹配 → 只剩另一条
    client.post(f"/api/v1/b2b/supplies/{good['id']}/close", headers=supplier_headers)
    resp = client.post(f"/api/v1/b2b/demands/{demand['id']}/match", headers=demand_headers)
    assert [item["supply"]["id"] for item in resp.json()["data"]["matches"]] == [partial["id"]]

    # 需求关闭后不能再发起匹配（此前仍返回 200 并生成记录）
    assert (
        client.post(f"/api/v1/b2b/demands/{demand['id']}/close", headers=demand_headers).status_code
        == 200
    )
    resp = client.post(f"/api/v1/b2b/demands/{demand['id']}/match", headers=demand_headers)
    assert resp.status_code == 409

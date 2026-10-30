"""admin 模块：资质审核流程测试。"""

from fastapi.testclient import TestClient

from app.core.errors import ConflictError
from app.db.session import SessionLocal
from app.modules.users import service as users_service

ADMIN_PHONE = "13700000000"
ADMIN_PASSWORD = "admin123456"


def _ensure_admin() -> None:
    with SessionLocal() as db:
        try:
            users_service.create_admin(
                db, phone=ADMIN_PHONE, password=ADMIN_PASSWORD, nickname="测试管理员"
            )
        except ConflictError:
            pass


def _login(client: TestClient, phone: str, password: str) -> str | None:
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    if resp.status_code != 200:
        return None
    return resp.json()["data"]["access_token"]


def _admin_headers(client: TestClient) -> dict[str, str]:
    _ensure_admin()
    token = _login(client, ADMIN_PHONE, ADMIN_PASSWORD)
    assert token
    return {"Authorization": f"Bearer {token}"}


def _register_enterprise(client: TestClient, phone: str, role: str = "merchant") -> None:
    resp = client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": phone,
            "password": "pass123456",
            "license_no": f"91370000{phone[-4:]}0000",
            "role": role,
        },
    )
    assert resp.status_code == 200, resp.text


def _find_review(headers: dict[str, str], client: TestClient, phone: str) -> dict:
    resp = client.get("/api/v1/admin/reviews?page=1&page_size=50", headers=headers)
    assert resp.status_code == 200, resp.text
    return next(item for item in resp.json()["data"]["items"] if item["phone"] == phone)


def test_reviews_requires_admin(client: TestClient) -> None:
    assert client.get("/api/v1/admin/reviews").status_code == 401

    client.post(
        "/api/v1/auth/register/tourist",
        json={"phone": "13711000001", "password": "pass123456"},
    )
    token = _login(client, "13711000001", "pass123456")
    resp = client.get("/api/v1/admin/reviews", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300


def test_approve_flow_merchant_can_login(client: TestClient) -> None:
    headers = _admin_headers(client)
    _register_enterprise(client, "13721000001")

    item = _find_review(headers, client, "13721000001")
    assert item["status"] == "pending_review"
    assert item["license_no"]  # 审核列表带资质信息

    # 审核前不能登录
    assert _login(client, "13721000001", "pass123456") is None

    # 通过 → 状态变为正常
    resp = client.post(f"/api/v1/admin/reviews/{item['id']}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "active"

    # 通过后可登录
    assert _login(client, "13721000001", "pass123456")

    # 已不在待审核列表；重复审核报 409
    resp = client.get("/api/v1/admin/reviews?page=1&page_size=50", headers=headers)
    assert all(i["phone"] != "13721000001" for i in resp.json()["data"]["items"])
    resp = client.post(f"/api/v1/admin/reviews/{item['id']}/approve", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == 40900


def test_reject_flow_blocks_login(client: TestClient) -> None:
    headers = _admin_headers(client)
    _register_enterprise(client, "13721000002", role="enterprise")

    item = _find_review(headers, client, "13721000002")

    resp = client.post(f"/api/v1/admin/reviews/{item['id']}/reject", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "rejected"

    # 驳回后登录被拒
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13721000002", "password": "pass123456"}
    )
    assert resp.status_code == 401
    assert "审核未通过" in resp.json()["msg"]

    # 驳回后不可再通过
    resp = client.post(f"/api/v1/admin/reviews/{item['id']}/approve", headers=headers)
    assert resp.status_code == 409


def test_approve_missing_user_returns_404(client: TestClient) -> None:
    headers = _admin_headers(client)
    resp = client.post("/api/v1/admin/reviews/999999/approve", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == 40400


def test_create_admin_rejects_duplicate_phone() -> None:
    """seed 路径：重复创建管理员报冲突（脚本据此实现幂等）。"""
    with SessionLocal() as db:
        users_service.create_admin(db, phone="13790000001", password="pass123456")
        created = users_service.create_admin(db, phone="13790000002", password="pass123456")
        assert created.role == "admin"
        assert created.status == "active"
        try:
            users_service.create_admin(db, phone="13790000001", password="pass123456")
        except ConflictError:
            pass
        else:
            raise AssertionError("重复创建应抛 ConflictError")


def test_disable_and_enable_flow(client: TestClient) -> None:
    headers = _admin_headers(client)
    client.post(
        "/api/v1/auth/register/tourist",
        json={"phone": "13732000001", "password": "pass123456"},
    )
    assert _login(client, "13732000001", "pass123456")

    resp = client.get("/api/v1/users?keyword=13732000001", headers=headers)
    uid = resp.json()["data"]["items"][0]["id"]

    # 禁用 → 登录被拒；重复禁用 409
    resp = client.post(f"/api/v1/admin/users/{uid}/disable", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "disabled"
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13732000001", "password": "pass123456"}
    )
    assert resp.status_code == 401
    assert "禁用" in resp.json()["msg"]
    assert client.post(f"/api/v1/admin/users/{uid}/disable", headers=headers).status_code == 409

    # 启用 → 恢复可登录；未禁用者再启用 409
    resp = client.post(f"/api/v1/admin/users/{uid}/enable", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "active"
    assert _login(client, "13732000001", "pass123456")
    assert client.post(f"/api/v1/admin/users/{uid}/enable", headers=headers).status_code == 409


def test_disable_guards(client: TestClient) -> None:
    headers = _admin_headers(client)

    # 管理员账号不可被禁用（含"禁用自己"的场景）
    resp = client.get("/api/v1/users?keyword=13700000000", headers=headers)
    admin_id = resp.json()["data"]["items"][0]["id"]
    resp = client.post(f"/api/v1/admin/users/{admin_id}/disable", headers=headers)
    assert resp.status_code == 409

    # 待审核用户不可直接禁用（应先驳回）
    _register_enterprise(client, "13732000002")
    item = _find_review(headers, client, "13732000002")
    resp = client.post(f"/api/v1/admin/users/{item['id']}/disable", headers=headers)
    assert resp.status_code == 409

    # 目标不存在 404
    assert client.post("/api/v1/admin/users/999999/disable", headers=headers).status_code == 404


def test_audit_logs_recorded_and_filterable(client: TestClient) -> None:
    headers = _admin_headers(client)
    resp = client.get("/api/v1/users?keyword=13700000000", headers=headers)
    admin_id = resp.json()["data"]["items"][0]["id"]

    _register_enterprise(client, "13732000003")
    item = _find_review(headers, client, "13732000003")
    client.post(f"/api/v1/admin/reviews/{item['id']}/approve", headers=headers)

    # 该目标的审核动作已落日志：动作 / 操作人 / 目标齐全
    resp = client.get(f"/api/v1/admin/audit-logs?target_id={item['id']}", headers=headers)
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total"] == 1
    log = data["items"][0]
    assert log["action"] == "review.approve"
    assert log["actor_id"] == admin_id
    assert log["target_type"] == "user"
    assert log["target_id"] == item["id"]
    assert log["detail"]
    assert log["created_at"]

    # 按动作过滤 + 分页形状
    resp = client.get(
        "/api/v1/admin/audit-logs?action=review.approve&page=1&page_size=5", headers=headers
    )
    data = resp.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["items"]
    assert all(i["action"] == "review.approve" for i in data["items"])

    # 权限：未登录 401
    assert client.get("/api/v1/admin/audit-logs").status_code == 401

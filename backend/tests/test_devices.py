"""设备绑定（需求 4.2）：登录登记设备、刷新校验设备、设备管理列表与移除。"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.admin.models import AuditLog
from app.modules.auth.models import DeviceBinding


def _device_id() -> str:
    return uuid.uuid4().hex[:32]


def _register(client: TestClient, phone: str) -> None:
    resp = client.post(
        "/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text


def _login(
    client: TestClient,
    phone: str,
    *,
    device_id: str | None = None,
    device_label: str | None = None,
    remember: bool = True,
) -> dict:
    payload: dict = {"phone": phone, "password": "secret123", "remember": remember}
    if device_id is not None:
        payload["device_id"] = device_id
    if device_label is not None:
        payload["device_label"] = device_label
    resp = client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _auth_headers(token: str, device_id: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if device_id:
        headers["X-Device-Id"] = device_id
    return headers


def _devices(client: TestClient, token: str, device_id: str | None = None) -> list[dict]:
    resp = client.get("/api/v1/auth/devices", headers=_auth_headers(token, device_id))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _new_phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def test_login_binds_device_and_lists(client: TestClient) -> None:
    phone = _new_phone()
    _register(client, phone)
    device_id = _device_id()
    data = _login(client, phone, device_id=device_id, device_label="Chrome · Windows")

    devices = _devices(client, data["access_token"], device_id)
    assert len(devices) == 1
    assert devices[0]["device_label"] == "Chrome · Windows"
    assert devices[0]["is_current"] is True
    assert devices[0]["last_ip"]


def test_devices_require_login(client: TestClient) -> None:
    assert client.get("/api/v1/auth/devices").status_code == 401


def test_refresh_requires_matching_device(client: TestClient) -> None:
    phone = _new_phone()
    _register(client, phone)
    device_id = _device_id()
    data = _login(client, phone, device_id=device_id)

    # 同一设备刷新：通过（令牌轮换）
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": data["refresh_token"], "device_id": device_id},
    )
    assert resp.status_code == 200, resp.text
    rotated = resp.json()["data"]["refresh_token"]

    # 不带设备标识：拒绝
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100

    # 换一台设备：拒绝
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated, "device_id": _device_id()}
    )
    assert resp.status_code == 401


def test_session_without_device_refreshes_compatibly(client: TestClient) -> None:
    """未上报设备的旧客户端会话不受设备校验影响（向后兼容）。"""
    phone = _new_phone()
    _register(client, phone)
    data = _login(client, phone)

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200, resp.text


def test_revoke_device_kills_only_that_device(client: TestClient) -> None:
    phone = _new_phone()
    _register(client, phone)
    device_a, device_b = _device_id(), _device_id()
    login_a = _login(client, phone, device_id=device_a)
    login_b = _login(client, phone, device_id=device_b)

    devices = _devices(client, login_a["access_token"], device_a)
    assert len(devices) == 2
    current = next(item for item in devices if item["is_current"])
    other = next(item for item in devices if not item["is_current"])

    resp = client.post(
        f"/api/v1/auth/devices/{current['id']}/revoke",
        headers=_auth_headers(login_a["access_token"], device_a),
    )
    assert resp.status_code == 200, resp.text

    # 被移除设备：刷新立即失效（其名下会话已随设备撤销）
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_a["refresh_token"], "device_id": device_a},
    )
    assert resp.status_code == 401

    # 另一台设备不受影响
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_b["refresh_token"], "device_id": device_b},
    )
    assert resp.status_code == 200, resp.text

    # 列表只剩另一台设备
    devices = _devices(client, login_b["access_token"], device_b)
    assert [item["id"] for item in devices] == [other["id"]]
    assert devices[0]["is_current"] is True


def test_relogin_reactivates_revoked_device(client: TestClient) -> None:
    """移除设备后在同一设备重新登录：绑定重新激活，不产生重复记录。"""
    phone = _new_phone()
    _register(client, phone)
    device_id = _device_id()
    data = _login(client, phone, device_id=device_id)
    binding_id = _devices(client, data["access_token"], device_id)[0]["id"]
    client.post(
        f"/api/v1/auth/devices/{binding_id}/revoke",
        headers=_auth_headers(data["access_token"], device_id),
    )

    relogin = _login(client, phone, device_id=device_id)
    devices = _devices(client, relogin["access_token"], device_id)
    assert [item["id"] for item in devices] == [binding_id]
    with SessionLocal() as db:
        total = db.scalar(
            select(func.count())
            .select_from(DeviceBinding)
            .where(DeviceBinding.device_id == device_id)
        )
    assert total == 1


def test_remember_false_shortens_session(client: TestClient) -> None:
    phone = _new_phone()
    _register(client, phone)
    long_session = _login(client, phone, remember=True)
    short_session = _login(client, phone, remember=False)

    assert long_session["refresh_expires_in"] == 30 * 24 * 3600
    assert (
        short_session["refresh_expires_in"]
        == get_settings().refresh_token_short_expire_hours * 3600
    )


def test_revoke_other_users_device_returns_404(client: TestClient) -> None:
    phone_a, phone_b = _new_phone(), _new_phone()
    _register(client, phone_a)
    _register(client, phone_b)
    device_a, device_b = _device_id(), _device_id()
    login_a = _login(client, phone_a, device_id=device_a)
    login_b = _login(client, phone_b, device_id=device_b)

    victim_binding = _devices(client, login_b["access_token"], device_b)[0]
    resp = client.post(
        f"/api/v1/auth/devices/{victim_binding['id']}/revoke",
        headers=_auth_headers(login_a["access_token"], device_a),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == 40400


def test_invalid_device_id_rejected(client: TestClient) -> None:
    phone = _new_phone()
    _register(client, phone)
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": "secret123", "device_id": "短"},
    )
    assert resp.status_code == 422


def test_revoke_device_writes_audit(client: TestClient) -> None:
    phone = _new_phone()
    _register(client, phone)
    device_id = _device_id()
    data = _login(client, phone, device_id=device_id, device_label="Safari · iOS")
    binding_id = _devices(client, data["access_token"], device_id)[0]["id"]

    client.post(
        f"/api/v1/auth/devices/{binding_id}/revoke",
        headers=_auth_headers(data["access_token"], device_id),
    )
    with SessionLocal() as db:
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "device.revoke", AuditLog.target_id == binding_id)
            .order_by(AuditLog.id.desc())
        )
    assert log is not None
    assert log.target_type == "device"
    assert log.target_id == binding_id
    assert log.detail and "Safari · iOS" in log.detail


def test_change_password_validates_device_header(client: TestClient) -> None:
    """X-Device-Id 头与请求体同一校验口径：非法值 400，且密码不会被改掉。"""
    phone = _new_phone()
    _register(client, phone)
    data = _login(client, phone, device_id=_device_id())
    headers = _auth_headers(data["access_token"])
    headers["X-Device-Id"] = "a" * 200  # 超出 String(64)：此前会落库时炸成 500（且密码已改）

    resp = client.post(
        "/api/v1/auth/password",
        json={"old_password": "secret123", "new_password": "newsecret123"},
        headers=headers,
    )
    assert resp.status_code == 400
    # 旧密码仍可登录，说明密码未被修改（修复前：旧密码 401、新密码可登录）
    assert (
        client.post(
            "/api/v1/auth/login", json={"phone": phone, "password": "secret123"}
        ).status_code
        == 200
    )


def test_change_password_keeps_remember(client: TestClient) -> None:
    """改密码为当前端续期时沿用「记住我」：未勾选仍是短期会话（不被悄悄拉长）。"""
    phone = _new_phone()
    _register(client, phone)
    short = _login(client, phone, device_id=_device_id(), remember=False)

    resp = client.post(
        "/api/v1/auth/password",
        json={"old_password": "secret123", "new_password": "newsecret123", "remember": False},
        headers=_auth_headers(short["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    assert (
        resp.json()["data"]["refresh_expires_in"]
        == get_settings().refresh_token_short_expire_hours * 3600
    )

    # 勾选「记住我」的会话改密码后仍是 30 天
    phone2 = _new_phone()
    _register(client, phone2)
    long_session = _login(client, phone2, device_id=_device_id(), remember=True)
    resp = client.post(
        "/api/v1/auth/password",
        json={"old_password": "secret123", "new_password": "newsecret123", "remember": True},
        headers=_auth_headers(long_session["access_token"]),
    )
    assert resp.json()["data"]["refresh_expires_in"] == 30 * 24 * 3600

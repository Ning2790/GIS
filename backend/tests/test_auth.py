"""认证闭环测试：注册 → 登录 → 携带令牌访问受保护接口 → 刷新 / 退出会话。"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.auth.models import LoginSession
from app.modules.users.models import User, UserStatus


def _unique_phone() -> str:
    """生成不重复的 11 位手机号，避免多个用例之间互相污染。"""
    return "13" + str(uuid.uuid4().int)[:9]


def test_tourist_register_login_and_me(client):
    phone = _unique_phone()

    resp = client.post(
        "/api/v1/auth/register/tourist",
        json={"phone": phone, "password": "secret123", "nickname": "游客甲"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "tourist"
    assert resp.json()["data"]["status"] == "active"

    resp = client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    assert resp.json()["data"]["user"]["phone"] == phone

    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["phone"] == phone


def test_duplicate_phone_rejected(client):
    phone = _unique_phone()
    payload = {"phone": phone, "password": "secret123"}

    assert client.post("/api/v1/auth/register/tourist", json=payload).status_code == 200

    resp = client.post("/api/v1/auth/register/tourist", json=payload)
    assert resp.status_code == 409
    assert resp.json()["code"] == 40900


def test_enterprise_register_requires_license(client):
    resp = client.post(
        "/api/v1/auth/register/enterprise",
        json={"phone": _unique_phone(), "password": "secret123"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 40000


def test_enterprise_pending_review_cannot_login(client):
    phone = _unique_phone()
    resp = client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": phone,
            "password": "secret123",
            "license_no": "91630100MA0000000X",
            "nickname": "某某农牧合作社",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "pending_review"

    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 401
    assert "审核" in resp.json()["msg"]


def test_login_with_wrong_password(client):
    phone = _unique_phone()
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})

    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "wrong-pass"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100


def _sign(payload: dict) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_token_must_carry_exp_and_sub(client):
    """令牌必须带有效的 exp 与数字 sub，否则一律 401（此前缺 sub 会 500、缺 exp 可永久有效）。"""
    exp = datetime.now(UTC) + timedelta(minutes=5)

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {_sign({'exp': exp})}"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {_sign({'sub': '1'})}"}
    )
    assert resp.status_code == 401

    resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {_sign({'sub': 'abc', 'exp': exp})}"},
    )
    assert resp.status_code == 401


def test_disabled_user_access_token_rejected(client):
    """被禁用的账号，禁用前签发的 access token 也应立即失效。"""
    phone = _unique_phone()
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    token = resp.json()["data"]["access_token"]

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone))
        user.status = UserStatus.DISABLED
        db.commit()

    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100


def test_register_rejects_password_over_bcrypt_limit(client):
    """超过 72 字节的密码应在参数校验阶段返回 422（此前是 500）。"""
    resp = client.post(
        "/api/v1/auth/register/tourist",
        json={"phone": _unique_phone(), "password": "密" * 25},  # 75 字节
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 40000


def _register_and_login(client) -> tuple[str, dict]:
    """注册并登录一个游客，返回 (手机号, 登录响应 data)。"""
    phone = _unique_phone()
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return phone, resp.json()["data"]


def test_login_returns_refresh_token_and_stores_hash(client):
    _phone, data = _register_and_login(client)
    assert data["refresh_token"]
    assert data["refresh_expires_in"] == 30 * 24 * 3600

    # 数据库只存哈希，不存明文
    expected_hash = hashlib.sha256(data["refresh_token"].encode("utf-8")).hexdigest()
    with SessionLocal() as db:
        session = db.scalar(select(LoginSession).where(LoginSession.token_hash == expected_hash))
        assert session is not None
        assert session.revoked_at is None


def test_refresh_rotates_and_revokes_old_token(client):
    phone, data = _register_and_login(client)
    old_refresh = data["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200, resp.text
    new = resp.json()["data"]
    assert new["access_token"]
    assert new["refresh_token"] != old_refresh

    # 新访问令牌可用
    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {new['access_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["phone"] == phone

    # 旧刷新令牌已作废（轮换）
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100

    # 新刷新令牌可继续轮换
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]})
    assert resp.status_code == 200


def test_logout_revokes_refresh_token(client):
    _phone, data = _register_and_login(client)
    refresh_token = data["refresh_token"]

    resp = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0

    # 退出后不能再刷新
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401

    # 重复退出幂等
    resp = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 200


def test_refresh_with_invalid_or_expired_token_rejected(client):
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 40})
    assert resp.status_code == 401

    _phone, data = _register_and_login(client)
    expired_token = "expired-token-for-test"
    with SessionLocal() as db:
        db.add(
            LoginSession(
                user_id=data["user"]["id"],
                family_id="expired-test-family",
                token_hash=hashlib.sha256(expired_token.encode("utf-8")).hexdigest(),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db.commit()

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": expired_token})
    assert resp.status_code == 401
    assert "过期" in resp.json()["msg"]


def test_disabled_user_refresh_rejected_and_session_revoked(client):
    phone, data = _register_and_login(client)
    refresh_token = data["refresh_token"]

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone))
        user.status = UserStatus.DISABLED
        db.commit()

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401
    assert "状态异常" in resp.json()["msg"]

    # 会话已被撤销：恢复启用后旧刷新令牌也不能再用
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone))
        user.status = UserStatus.ACTIVE
        db.commit()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


def test_update_profile_nickname(client: TestClient) -> None:
    """个人资料：改昵称生效；未登录 401；超长 422。"""
    phone = "13" + str(uuid.uuid4().int)[:9]
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    token = client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": "secret123"}
    ).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert (
        client.put("/api/v1/users/me", json={"nickname": "新昵称"}, headers=headers).status_code
        == 200
    )
    me = client.get("/api/v1/users/me", headers=headers).json()["data"]
    assert me["nickname"] == "新昵称"

    assert client.put("/api/v1/users/me", json={"nickname": "x"}).status_code == 401
    too_long = client.put("/api/v1/users/me", json={"nickname": "x" * 65}, headers=headers)
    assert too_long.status_code == 422


def test_change_password_flow(client: TestClient) -> None:
    """改密码：原密码校验 → 旧刷新令牌失效 → 新密码可登录、旧密码不可。"""
    phone = "13" + str(uuid.uuid4().int)[:9]
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    login = client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": "secret123"}
    ).json()["data"]
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    old_refresh = login["refresh_token"]

    # 原密码错误 → 401
    resp = client.post(
        "/api/v1/auth/password",
        json={"old_password": "wrong-pass", "new_password": "newsecret456"},
        headers=headers,
    )
    assert resp.status_code == 401
    assert "原密码" in resp.json()["msg"]

    # 新旧相同 → 400
    resp = client.post(
        "/api/v1/auth/password",
        json={"old_password": "secret123", "new_password": "secret123"},
        headers=headers,
    )
    assert resp.status_code == 400

    # 正常修改：返回新令牌对
    resp = client.post(
        "/api/v1/auth/password",
        json={"old_password": "secret123", "new_password": "newsecret456"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    new_tokens = resp.json()["data"]
    assert new_tokens["access_token"] and new_tokens["refresh_token"]

    # 其他会话（旧刷新令牌）已失效
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401

    # 新令牌可刷新（当前端续期正常）
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert resp.status_code == 200

    # 新密码可登录、旧密码不可
    assert (
        client.post(
            "/api/v1/auth/login", json={"phone": phone, "password": "secret123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"phone": phone, "password": "newsecret456"}
        ).status_code
        == 200
    )

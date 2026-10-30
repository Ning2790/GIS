"""刷新令牌重放检测 / 家族撤销 / 会话清理（S8 安全债）测试。

重放检测语义（见 auth.service.refresh）：
- 已轮换令牌在宽限窗口内二次出现 → 视为并发刷新竞态，仅 401；
- 超出宽限 → 判定重放，撤销整个轮换家族（含最新令牌），强制重新登录。
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.modules.auth import service as auth_service
from app.modules.auth.models import LoginSession


def _register_and_login(client: TestClient) -> tuple[str, str]:
    phone = "139" + uuid.uuid4().hex[:8]
    password = "Test123456"
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": password})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert resp.status_code == 200, resp.text
    return phone, resp.json()["data"]["refresh_token"]


def _refresh(client: TestClient, token: str) -> tuple[int, dict]:
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    return resp.status_code, resp.json()


def _set_revoked_age(token: str, seconds: int) -> None:
    """把某刷新令牌对应会话的 revoked_at 改成 N 秒前（模拟时间流逝）。"""
    with SessionLocal() as db:
        db.execute(
            update(LoginSession)
            .where(LoginSession.token_hash == auth_service._hash_token(token))
            .values(revoked_at=datetime.now(UTC) - timedelta(seconds=seconds))
        )
        db.commit()


def _session_of(token: str) -> LoginSession:
    with SessionLocal() as db:
        return db.scalar(
            select(LoginSession).where(LoginSession.token_hash == auth_service._hash_token(token))
        )


def test_replay_beyond_grace_revokes_family(client: TestClient) -> None:
    _phone, t1 = _register_and_login(client)
    status, body = _refresh(client, t1)
    assert status == 200
    t2 = body["data"]["refresh_token"]

    # 模拟：T1 已被轮换 60 秒（超出宽限），此时它再次出现 → 判定重放
    _set_revoked_age(t1, 60)
    assert _refresh(client, t1)[0] == 401

    # 家族被撤销：合法用户手里的 T2 一并失效（需重新登录）
    assert _refresh(client, t2)[0] == 401


def test_replay_within_grace_keeps_family(client: TestClient) -> None:
    _phone, t1 = _register_and_login(client)
    status, body = _refresh(client, t1)
    assert status == 200
    t2 = body["data"]["refresh_token"]

    # 宽限期内二次使用 T1（并发刷新的正常竞态）：仅 401，不撤销家族
    assert _refresh(client, t1)[0] == 401
    # 新令牌仍可用
    assert _refresh(client, t2)[0] == 200


def test_refresh_rotation_keeps_family_chain(client: TestClient) -> None:
    phone, t1 = _register_and_login(client)
    status, body = _refresh(client, t1)
    assert status == 200
    t2 = body["data"]["refresh_token"]

    assert _session_of(t1).family_id == _session_of(t2).family_id  # 轮换同族

    # 重新登录 = 新家族
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "Test123456"})
    t3 = resp.json()["data"]["refresh_token"]
    assert _session_of(t3).family_id != _session_of(t1).family_id


def test_cleanup_expired_sessions(client: TestClient) -> None:
    tag = uuid.uuid4().hex[:8]
    now = datetime.now(UTC)

    def _key() -> str:
        return uuid.uuid4().hex * 2  # 64 位唯一 token_hash

    with SessionLocal() as db:
        db.add(  # 过期活跃：应删
            LoginSession(
                user_id=1,
                family_id=f"cl-{tag}-a",
                token_hash=_key(),
                expires_at=now - timedelta(hours=1),
            )
        )
        db.add(  # 久撤销（超保留期）：应删
            LoginSession(
                user_id=1,
                family_id=f"cl-{tag}-b",
                token_hash=_key(),
                expires_at=now + timedelta(days=1),
                revoked_at=now - timedelta(days=2),
            )
        )
        db.add(  # 新撤销（保留期内）：应留——重放检测的依据
            LoginSession(
                user_id=1,
                family_id=f"cl-{tag}-c",
                token_hash=_key(),
                expires_at=now + timedelta(days=1),
                revoked_at=now - timedelta(minutes=5),
            )
        )
        db.add(  # 正常活跃：应留
            LoginSession(
                user_id=1,
                family_id=f"cl-{tag}-d",
                token_hash=_key(),
                expires_at=now + timedelta(days=1),
            )
        )
        db.commit()
        removed = auth_service.cleanup_expired_sessions(db)

    # 不写死总数：同库可能还有别的用例留下的过期会话（如 test_auth 的手工过期行）
    assert removed >= 2
    with SessionLocal() as db:
        remaining = {
            session.family_id
            for session in db.scalars(
                select(LoginSession).where(LoginSession.family_id.like(f"cl-{tag}-%"))
            )
        }
    assert remaining == {f"cl-{tag}-c", f"cl-{tag}-d"}

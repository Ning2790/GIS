"""cs 模块：AI 接待 → 转人工 → 客服队列 → 人工回复流程测试。"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import llm
from app.core.errors import ConflictError
from app.db.session import SessionLocal
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus


def _unique_phone() -> str:
    return "13" + str(uuid.uuid4().int)[:9]


def _register_active_user(client: TestClient, role: str = "tourist") -> tuple[str, str, int]:
    """注册并登录一个可用的用户，返回 (phone, token, user_id)。

    商户 / 企业正常流程需 admin 审核；测试夹具直接改状态，避免依赖 admin 用例。
    """
    phone = _unique_phone()
    if role == "tourist":
        client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    else:
        client.post(
            "/api/v1/auth/register/enterprise",
            json={
                "phone": phone,
                "password": "secret123",
                "license_no": f"91{str(uuid.uuid4().int)[:16]}",
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


def test_cs_requires_login(client: TestClient) -> None:
    assert client.post("/api/v1/cs/sessions").status_code == 401
    assert client.get("/api/v1/cs/queue").status_code == 401


def test_ai_service_and_human_transfer_flow(client: TestClient) -> None:
    _phone, token, _uid = _register_active_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 发起会话：AI 接待 + 开场问候
    resp = client.post("/api/v1/cs/sessions", headers=headers)
    assert resp.status_code == 200, resp.text
    session = resp.json()["data"]
    sid = session["id"]
    assert session["status"] == "ai"

    # 用户发消息 → AI 自动应答（mock 提供方）
    resp = client.post(
        f"/api/v1/cs/sessions/{sid}/messages",
        json={"content": "带老人去青海湖要注意什么？"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["message"]["sender_type"] == "user"
    assert data["reply"] is not None
    assert data["reply"]["sender_type"] == "ai"
    assert "mock" in data["reply"]["content"]

    # 消息序列：问候 → 用户 → AI 应答
    resp = client.get(f"/api/v1/cs/sessions/{sid}/messages", headers=headers)
    items = resp.json()["data"]["items"]
    assert [m["sender_type"] for m in items] == ["ai", "user", "ai"]

    # 转人工 → 排队；重复转人工 409
    resp = client.post(f"/api/v1/cs/sessions/{sid}/transfer", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "queued"
    assert client.post(f"/api/v1/cs/sessions/{sid}/transfer", headers=headers).status_code == 409

    # 游客不可看队列（403）；商户可见
    assert client.get("/api/v1/cs/queue", headers=headers).status_code == 403
    _m_phone, m_token, m_id = _register_active_user(client, "merchant")
    mh = {"Authorization": f"Bearer {m_token}"}
    resp = client.get("/api/v1/cs/queue?page=1&page_size=50", headers=mh)
    assert sid in [s["id"] for s in resp.json()["data"]["items"]]

    # 接入 → human；重复接入 409
    resp = client.post(f"/api/v1/cs/sessions/{sid}/claim", headers=mh)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "human"
    assert resp.json()["data"]["agent_id"] == m_id
    assert client.post(f"/api/v1/cs/sessions/{sid}/claim", headers=mh).status_code == 409

    # 客服人工回复（agent，无 AI 应答）；人工服务中用户消息也不触发 AI
    resp = client.post(
        f"/api/v1/cs/sessions/{sid}/messages",
        json={"content": "建议携带氧气瓶，避免剧烈运动。"},
        headers=mh,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"]["sender_type"] == "agent"
    assert resp.json()["data"]["reply"] is None
    resp = client.post(
        f"/api/v1/cs/sessions/{sid}/messages", json={"content": "好的，谢谢"}, headers=headers
    )
    assert resp.json()["data"]["reply"] is None

    # 结束会话；结束后发消息 409
    resp = client.post(f"/api/v1/cs/sessions/{sid}/close", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "closed"
    resp = client.post(
        f"/api/v1/cs/sessions/{sid}/messages", json={"content": "还在吗"}, headers=headers
    )
    assert resp.status_code == 409


def test_cs_session_visibility_enforced(client: TestClient) -> None:
    _p1, t1, _u1 = _register_active_user(client)
    _p2, t2, _u2 = _register_active_user(client)
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}

    sid = client.post("/api/v1/cs/sessions", headers=h1).json()["data"]["id"]
    # 他人不可见（按不存在处理，不泄漏）
    assert client.get(f"/api/v1/cs/sessions/{sid}", headers=h2).status_code == 404
    assert client.get(f"/api/v1/cs/sessions/{sid}/messages", headers=h2).status_code == 404
    resp = client.post(f"/api/v1/cs/sessions/{sid}/messages", json={"content": "hi"}, headers=h2)
    assert resp.status_code == 404
    assert client.post(f"/api/v1/cs/sessions/{sid}/transfer", headers=h2).status_code == 404


def test_cs_ai_failure_auto_transfers_to_human(client: TestClient, monkeypatch) -> None:
    _p, token, _u = _register_active_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/api/v1/cs/sessions", headers=headers).json()["data"]["id"]

    def _boom(messages, **kwargs):
        raise RuntimeError("AI 不可用")

    monkeypatch.setattr(llm, "chat", _boom)

    resp = client.post(
        f"/api/v1/cs/sessions/{sid}/messages", json={"content": "你好"}, headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reply"] is not None
    assert data["reply"]["sender_type"] == "system"
    assert "人工" in data["reply"]["content"]

    # 会话已自动转人工
    resp = client.get(f"/api/v1/cs/sessions/{sid}", headers=headers)
    assert resp.json()["data"]["status"] == "queued"


def _admin_headers(client: TestClient) -> dict[str, str]:
    """创建（幂等）并登录测试管理员，返回请求头。"""
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


def test_claim_guards_and_release_flow(client: TestClient) -> None:
    # 商户同时是普通用户：不能接入自己发起的会话
    _mp, m_token, _mid = _register_active_user(client, "merchant")
    m_headers = {"Authorization": f"Bearer {m_token}"}
    own_sid = client.post("/api/v1/cs/sessions", headers=m_headers).json()["data"]["id"]
    client.post(f"/api/v1/cs/sessions/{own_sid}/transfer", headers=m_headers)
    resp = client.post(f"/api/v1/cs/sessions/{own_sid}/claim", headers=m_headers)
    assert resp.status_code == 409

    # 正常流程：转人工 → 接入 → 释放 → 其他客服可再次接入
    _up, u_token, _uid = _register_active_user(client)
    u_headers = {"Authorization": f"Bearer {u_token}"}
    sid = client.post("/api/v1/cs/sessions", headers=u_headers).json()["data"]["id"]
    client.post(f"/api/v1/cs/sessions/{sid}/transfer", headers=u_headers)

    _mp2, m2_token, m2_id = _register_active_user(client, "merchant")
    m2_headers = {"Authorization": f"Bearer {m2_token}"}
    resp = client.post(f"/api/v1/cs/sessions/{sid}/claim", headers=m2_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["agent_id"] == m2_id

    resp = client.post(f"/api/v1/cs/sessions/{sid}/release", headers=m2_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "queued"
    assert resp.json()["data"]["agent_id"] is None

    # 未接入的客服对排队中的会话不可见（按 404 处理），更不能替别人释放
    _mp3, m3_token, _m3 = _register_active_user(client, "merchant")
    m3_headers = {"Authorization": f"Bearer {m3_token}"}
    resp = client.post(f"/api/v1/cs/sessions/{sid}/release", headers=m3_headers)
    assert resp.status_code == 404

    # 释放后其他客服可正常接入
    resp = client.post(f"/api/v1/cs/sessions/{sid}/claim", headers=m3_headers)
    assert resp.status_code == 200


def test_queue_order_stable_against_messages(client: TestClient) -> None:
    """排队期间继续发消息不应把排队者刷到队尾（队列按进入队列时间排序）。"""
    _up, u1_token, _u1 = _register_active_user(client)
    h1 = {"Authorization": f"Bearer {u1_token}"}
    _up2, u2_token, _u2 = _register_active_user(client)
    h2 = {"Authorization": f"Bearer {u2_token}"}

    sid_a = client.post("/api/v1/cs/sessions", headers=h1).json()["data"]["id"]
    client.post(f"/api/v1/cs/sessions/{sid_a}/transfer", headers=h1)
    sid_b = client.post("/api/v1/cs/sessions", headers=h2).json()["data"]["id"]
    client.post(f"/api/v1/cs/sessions/{sid_b}/transfer", headers=h2)

    client.post(f"/api/v1/cs/sessions/{sid_a}/messages", json={"content": "还在吗"}, headers=h1)

    _mp, m_token, _mid = _register_active_user(client, "merchant")
    m_headers = {"Authorization": f"Bearer {m_token}"}
    resp = client.get("/api/v1/cs/queue?page=1&page_size=50", headers=m_headers)
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert ids.index(sid_a) < ids.index(sid_b)


def test_admin_cannot_send_message_in_others_session(client: TestClient) -> None:
    """管理员可查看会话，但不能以"用户"身份在他人会话里发言。"""
    _up, u_token, _uid = _register_active_user(client)
    u_headers = {"Authorization": f"Bearer {u_token}"}
    sid = client.post("/api/v1/cs/sessions", headers=u_headers).json()["data"]["id"]

    admin_headers = _admin_headers(client)
    assert client.get(f"/api/v1/cs/sessions/{sid}", headers=admin_headers).status_code == 200
    resp = client.post(
        f"/api/v1/cs/sessions/{sid}/messages",
        json={"content": "管理员插话"},
        headers=admin_headers,
    )
    assert resp.status_code == 403


def test_cs_lifecycle_is_audited(client: TestClient) -> None:
    """客服流转（转人工 / 接入 / 释放 / 结束）写入审计日志，可按目标类型过滤查询。"""
    from app.modules.admin.models import AuditLog

    _up, u_token, u_id = _register_active_user(client)
    u_headers = {"Authorization": f"Bearer {u_token}"}
    sid = client.post("/api/v1/cs/sessions", headers=u_headers).json()["data"]["id"]
    client.post(f"/api/v1/cs/sessions/{sid}/transfer", headers=u_headers)

    _mp, m_token, m_id = _register_active_user(client, "merchant")
    m_headers = {"Authorization": f"Bearer {m_token}"}
    client.post(f"/api/v1/cs/sessions/{sid}/claim", headers=m_headers)
    client.post(f"/api/v1/cs/sessions/{sid}/release", headers=m_headers)
    client.post(f"/api/v1/cs/sessions/{sid}/claim", headers=m_headers)
    client.post(f"/api/v1/cs/sessions/{sid}/close", headers=m_headers)

    with SessionLocal() as db:
        logs = db.scalars(
            select(AuditLog)
            .where(AuditLog.target_type == "cs_session", AuditLog.target_id == sid)
            .order_by(AuditLog.id.asc())
        ).all()
    assert [log.action for log in logs] == [
        "cs.transfer",
        "cs.claim",
        "cs.release",
        "cs.claim",
        "cs.close",
    ]
    assert logs[0].actor_id == u_id  # 转人工由会话发起人触发
    assert logs[1].actor_id == m_id  # 接入由客服触发
    assert all(log.detail for log in logs)

    # 管理员可按 target_type 过滤查到这些记录
    admin_headers = _admin_headers(client)
    resp = client.get(
        "/api/v1/admin/audit-logs?target_type=cs_session&page_size=50", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert all(item["target_type"] == "cs_session" for item in items)
    assert sid in [item["target_id"] for item in items]

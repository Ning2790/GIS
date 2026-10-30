"""ai 模块：问答、RAG / 联网适配与流式测试。"""

import json
import uuid

from fastapi.testclient import TestClient

from app.core import llm


def _login_tourist(client: TestClient) -> str:
    """注册并登录一个游客，返回访问令牌。"""
    phone = "13" + str(uuid.uuid4().int)[:9]
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def test_ask_creates_and_continues_conversation(client: TestClient) -> None:
    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/v1/ai/ask", json={"question": "你好"}).status_code == 401

    resp = client.post("/api/v1/ai/ask", json={"question": "青海湖好玩吗？"}, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    conversation_id = data["conversation_id"]
    assert conversation_id and "mock" in data["answer"]

    resp = client.post(
        "/api/v1/ai/ask",
        json={"question": "要带什么？", "conversation_id": conversation_id},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/v1/ai/conversations/{conversation_id}", headers=headers)
    assert resp.status_code == 200
    messages = resp.json()["data"]["messages"]
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    resp = client.get("/api/v1/ai/conversations?page=1&page_size=5", headers=headers)
    assert any(item["id"] == conversation_id for item in resp.json()["data"]["items"])


def test_rag_and_search_context_in_prompt(client: TestClient, monkeypatch) -> None:
    """验证 prompt 组装：知识库命中（RAG）与联网适配器按需触发。"""
    captured: dict = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        return "（AI 助手 · mock）测试回答"

    monkeypatch.setattr(llm, "chat", fake_chat)
    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/v1/ai/ask", json={"question": "高反怎么办？"}, headers=headers)
    joined = json.dumps(captured["messages"], ensure_ascii=False)
    assert "红景天" in joined  # 命中「高原反应」知识

    client.post("/api/v1/ai/ask", json={"question": "现在青海湖的天气怎么样？"}, headers=headers)
    joined = json.dumps(captured["messages"], ensure_ascii=False)
    assert "模拟搜索结果" in joined  # 含「现在 / 天气」触发联网适配器


def test_conversation_ownership(client: TestClient) -> None:
    token_a = _login_tourist(client)
    token_b = _login_tourist(client)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    conversation_id = client.post(
        "/api/v1/ai/ask", json={"question": "测试归属"}, headers=headers_a
    ).json()["data"]["conversation_id"]

    assert (
        client.get(f"/api/v1/ai/conversations/{conversation_id}", headers=headers_b).status_code
        == 404
    )
    resp = client.post(
        "/api/v1/ai/ask",
        json={"question": "跟进", "conversation_id": conversation_id},
        headers=headers_b,
    )
    assert resp.status_code == 404


def test_stream_returns_sse_and_persists(client: TestClient) -> None:
    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/v1/ai/ask/stream", json={"question": "流式测试"}, headers=headers)
    assert resp.status_code == 200, resp.text
    text = resp.text
    assert "conversation_id" in text
    assert "[DONE]" in text

    events = [
        json.loads(line[len("data: ") :])
        for line in text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    conversation_id = events[0]["conversation_id"]
    assert any("delta" in event for event in events)

    resp = client.get(f"/api/v1/ai/conversations/{conversation_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["messages"]) == 2


def test_conversation_rename_and_delete(client: TestClient) -> None:
    """会话重命名与删除（仅本人）：改名持久、删除连同消息、他人不可见。"""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.modules.ai.models import AiMessage

    token_a = _login_tourist(client)
    token_b = _login_tourist(client)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    conversation_id = client.post(
        "/api/v1/ai/ask", json={"question": "重命名用"}, headers=headers_a
    ).json()["data"]["conversation_id"]

    # 未登录 401；他人 404；非法标题 422
    assert (
        client.patch(
            f"/api/v1/ai/conversations/{conversation_id}", json={"title": "新标题"}
        ).status_code
        == 401
    )
    assert (
        client.patch(
            f"/api/v1/ai/conversations/{conversation_id}", json={"title": "偷改"}, headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/ai/conversations/{conversation_id}", json={"title": ""}, headers=headers_a
        ).status_code
        == 422
    )

    # 重命名：返回新标题，列表里也是新标题
    renamed = client.patch(
        f"/api/v1/ai/conversations/{conversation_id}",
        json={"title": "  青海湖行程咨询  "},
        headers=headers_a,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["title"] == "青海湖行程咨询"  # 首尾空白已去除
    listing = client.get("/api/v1/ai/conversations", headers=headers_a).json()["data"]["items"]
    assert any(
        item["id"] == conversation_id and item["title"] == "青海湖行程咨询" for item in listing
    )

    # 删除：连同消息一起删；再取详情 404
    with SessionLocal() as db:
        before = len(
            db.scalars(select(AiMessage).where(AiMessage.conversation_id == conversation_id)).all()
        )
    assert before > 0

    deleted = client.delete(f"/api/v1/ai/conversations/{conversation_id}", headers=headers_a)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted_messages"] == before
    assert (
        client.get(f"/api/v1/ai/conversations/{conversation_id}", headers=headers_a).status_code
        == 404
    )
    with SessionLocal() as db:
        assert (
            db.scalars(select(AiMessage).where(AiMessage.conversation_id == conversation_id)).all()
            == []
        )
    # 幂等语义：再删一次 404（会话已不存在）
    assert (
        client.delete(f"/api/v1/ai/conversations/{conversation_id}", headers=headers_a).status_code
        == 404
    )


def test_rename_rejects_blank_and_control_titles(client: TestClient) -> None:
    """空白标题与控制字符在请求模型层就被拦下（复审发现：纯空格会落库为空标题、NUL 会 500）。"""
    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}
    conversation_id = client.post(
        "/api/v1/ai/ask", json={"question": "标题校验"}, headers=headers
    ).json()["data"]["conversation_id"]

    for bad in ("   ", "", chr(9) + chr(10), "a" + chr(0) + "b", "字" * 129):
        resp = client.patch(
            f"/api/v1/ai/conversations/{conversation_id}", json={"title": bad}, headers=headers
        )
        assert resp.status_code == 422, (bad, resp.status_code, resp.text)

    # 边界：129 个字符但首尾带空白 → strip 后 127，应当通过
    ok = client.patch(
        f"/api/v1/ai/conversations/{conversation_id}",
        json={"title": " " + "字" * 127 + " "},
        headers=headers,
    )
    assert ok.status_code == 200
    assert len(ok.json()["data"]["title"]) == 127


def test_delete_during_ask_returns_404_not_500(client: TestClient, monkeypatch) -> None:
    """模型回答期间删除会话：按「会话不存在」返回 404，不能漏成 500（复审实测的竞态）。"""
    from app.core import llm
    from app.modules.ai import service as ai_service

    token = _login_tourist(client)
    headers = {"Authorization": f"Bearer {token}"}
    conversation_id = client.post(
        "/api/v1/ai/ask", json={"question": "先建会话"}, headers=headers
    ).json()["data"]["conversation_id"]

    def delete_then_answer(messages):  # noqa: ANN001
        # 模拟「模型思考期间用户删掉了会话」
        client.delete(f"/api/v1/ai/conversations/{conversation_id}", headers=headers)
        return "迟到的回答"

    monkeypatch.setattr(llm, "chat", delete_then_answer)
    monkeypatch.setattr(ai_service.llm, "chat", delete_then_answer)
    resp = client.post(
        "/api/v1/ai/ask",
        json={"question": "并发删除", "conversation_id": conversation_id},
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
    assert "会话不存在" in resp.json()["msg"]

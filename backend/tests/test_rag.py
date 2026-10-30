"""N12 向量检索：嵌入确定性、语义命中、关键词回退、AI/客服两处接入。

载体是 JSON 列 + 应用层余弦（用户拍板），嵌入默认 mock 确定性实现——
所以这些测试全部离线可复现，不需要外网与嵌入服务。
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import rag
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.ai import knowledge
from app.modules.ai.models import KnowledgeChunk


def _auth_headers(client: TestClient) -> dict[str, str]:
    """注册并登录一个游客（与其他 ai 测试同一写法），返回鉴权头。"""
    phone = "13" + str(uuid.uuid4().int)[:9]
    client.post("/api/v1/auth/register/tourist", json={"phone": phone, "password": "secret123"})
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _seed_chunks() -> None:
    """把内置知识写进表（幂等，与 seed 脚本共用同一实现，避免逻辑漂移）。"""
    with SessionLocal() as db:
        knowledge.upsert_entries(db)


def test_mock_embedding_is_deterministic_and_normalized() -> None:
    """同文本恒等、向量已归一化（余弦 = 点积的前提）。"""
    first = rag.mock_embed("青海湖什么时候去最好")
    assert first == rag.mock_embed("青海湖什么时候去最好")
    assert abs(sum(v * v for v in first) - 1.0) < 1e-9


def test_semantic_hit_when_keyword_misses() -> None:
    """「小孩」不在关键词里，但同义词归一后应语义命中「亲子出行」。"""
    _seed_chunks()
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "带小孩去青海要注意什么")
    assert hits, "语义检索应有命中"
    assert hits[0].topic == "亲子出行"
    assert hits[0].matched_by == "vector"
    assert hits[0].score >= get_settings().rag_min_score

    # 对照：纯关键词路径（内置条目的 keywords 刻意没写「小孩」）命中为空
    assert not knowledge._keyword_hits("带小孩去青海要注意什么", 3)


def test_keyword_fallback_when_table_empty() -> None:
    """表为空（种子没跑）时不报错，回退关键词检索；用例结束恢复数据，避免污染其它用例。"""
    try:
        with SessionLocal() as db:
            for chunk in db.scalars(select(KnowledgeChunk)):
                db.delete(chunk)
            db.commit()
            hits = knowledge.retrieve(db, "高反怎么办")
        assert hits and hits[0].topic == "高原反应"
        assert hits[0].matched_by == "keyword"
    finally:
        _seed_chunks()


def test_embedding_failure_falls_back_to_keyword(monkeypatch) -> None:
    """嵌入实现不可用（如真实服务连不上）时回退关键词，不抛异常。"""
    _seed_chunks()
    monkeypatch.setattr(
        rag, "embed_texts", lambda _texts: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "高反怎么办")
    assert hits and hits[0].topic == "高原反应"


def test_ask_returns_knowledge_sources(client: TestClient) -> None:
    """AI 问答响应带知识命中（topic/score/matched_by/excerpt），供前端来源卡片。"""
    _seed_chunks()
    headers = _auth_headers(client)
    resp = client.post(
        "/api/v1/ai/ask", json={"question": "带小孩去青海要注意什么"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    sources = data["knowledge_sources"]
    assert sources, data
    top = sources[0]
    assert top["topic"] == "亲子出行"
    assert top["matched_by"] == "vector"
    assert top["score"] > 0
    assert top["excerpt"] and len(top["excerpt"]) <= 81
    # 联网来源（sources）仍是 URL 列表，两者互不干扰
    assert data["sources"] == []


def test_stream_emits_knowledge_sources_event(client: TestClient) -> None:
    """SSE 流里也要带 knowledge_sources 事件（前端流式渲染用）。"""
    _seed_chunks()
    headers = _auth_headers(client)
    with client.stream(
        "POST", "/api/v1/ai/ask/stream", json={"question": "特产能寄回家吗"}, headers=headers
    ) as resp:
        body = "".join(chunk for chunk in resp.iter_text())
    assert "knowledge_sources" in body
    assert "特产" in body


def test_cs_auto_reply_uses_knowledge(client: TestClient) -> None:
    """客服自动应答共用检索：命中时回复末尾附「参考：…」。"""
    _seed_chunks()
    headers = _auth_headers(client)
    created = client.post("/api/v1/cs/sessions", headers=headers)
    session_id = created.json()["data"]["id"]
    resp = client.post(
        f"/api/v1/cs/sessions/{session_id}/messages",
        json={"content": "带小孩上高原要注意什么"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["data"]["reply"]
    assert reply["sender_type"] == "ai"
    assert "参考：" in reply["content"]
    assert "亲子出行" in reply["content"]


def test_keyword_hit_survives_vector_miss() -> None:
    """复审回归：向量误命中不能挤掉关键词的正确结果。

    「需要带什么衣服」此前命中「特产」（同义词桶归错）而丢掉本该命中的「装备」；
    现在两路结果合并，且「带什么」归装备组，装备必须排在最前。
    """
    _seed_chunks()
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "去青海需要带什么衣服")
    topics = [hit.topic for hit in hits]
    assert topics[0] == "装备", topics
    assert "特产" not in topics, topics


def test_weather_question_hits_weather_entry() -> None:
    """复审回归：天气类问题应命中「天气与保暖」，而不是被防晒/保暖词磁吸到装备/亲子。"""
    _seed_chunks()
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "今天天气怎么样")
    assert hits, "天气问题应有命中"
    assert hits[0].topic == "天气与保暖", [hit.topic for hit in hits]


def test_retrieve_never_raises_on_db_error(monkeypatch) -> None:
    """复审回归：读取分块表失败（DB 抖动）时降级为关键词，不把异常抛给调用方。"""
    _seed_chunks()
    monkeypatch.setattr(
        knowledge, "_load_chunks", lambda _db: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "高反怎么办")
    assert hits and hits[0].topic == "高原反应"
    assert hits[0].matched_by == "keyword"


def test_dimension_mismatch_skips_vector_with_warning(caplog) -> None:
    """复审回归：库内向量维度与当前配置不一致时跳过向量路径（并告警），不静默返回空。"""
    import logging

    _seed_chunks()
    with SessionLocal() as db:
        chunk = db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.topic == "高原反应"))
        chunk.embedding = [0.1] * 32  # 模拟旧维度向量
        chunk.embedding_dim = 32
        db.commit()
        with caplog.at_level(logging.WARNING, logger="app.modules.ai.knowledge"):
            hits = knowledge.retrieve(db, "带小孩去青海要注意什么")
        # 该条目被跳过，但其它条目仍可向量命中；「高原反应」不再贡献向量结果
        assert all(hit.topic != "高原反应" or hit.matched_by == "keyword" for hit in hits)
        assert any("不一致" in record.getMessage() for record in caplog.records), "应有不一致告警"
        chunk.embedding_dim = 1024
        db.commit()


def test_secondary_hits_filtered_from_cards() -> None:
    """复审延续项：弱命中（非首位且低于二级门槛）只进 prompt，不进「参考平台知识」卡片。"""
    _seed_chunks()
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "今天天气怎么样")
    strong = knowledge.strong_hits(hits)
    assert strong and strong[0].topic == "天气与保暖"
    # 装备/亲子（防晒保暖词相关但弱）不应出现在卡片里
    assert all(hit.topic not in {"装备", "亲子出行"} for hit in strong), [
        (hit.topic, hit.score) for hit in strong
    ]
    # 但 prompt 上下文仍可用全部命中（检索结果本身不裁剪）
    assert len(hits) >= len(strong)


def test_history_keeps_knowledge_sources(client: TestClient) -> None:
    """复审观察项：来源随助手消息持久化——重开会话详情仍带 knowledge_sources。"""
    _seed_chunks()
    headers = _auth_headers(client)
    asked = client.post(
        "/api/v1/ai/ask", json={"question": "带小孩去青海要注意什么"}, headers=headers
    ).json()["data"]
    conversation_id = asked["conversation_id"]
    assert asked["knowledge_sources"], "首答应带来源"

    detail = client.get(f"/api/v1/ai/conversations/{conversation_id}", headers=headers).json()[
        "data"
    ]
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
    assert assistant["knowledge_sources"], "历史消息应带来源"
    assert assistant["knowledge_sources"][0]["topic"] == "亲子出行"
    assert assistant["knowledge_sources"][0]["excerpt"]


def test_strong_hits_accepts_specific_single_keyword() -> None:
    """展示门禁：命中的关键词本身够具体（≥3 字）时，单词命中即算强信号。

    扩充知识库后单词命中很常见（「无人机」→「环保与无人机」），此前只按「≥2 词」
    过滤会把最贴切的条目挡在来源卡片外（扩充演示数据时实测踩到）。
    """
    from app.modules.ai.knowledge import KnowledgeHit, strong_hits

    top = KnowledgeHit(
        topic="青海湖", content="x", score=1.0, matched_by="keyword", matched=("青海湖",)
    )
    specific = KnowledgeHit(
        topic="环保与无人机", content="y", score=1.0, matched_by="keyword", matched=("无人机",)
    )
    short = KnowledgeHit(
        topic="装备", content="z", score=1.0, matched_by="keyword", matched=("装备",)
    )

    assert [hit.topic for hit in strong_hits([top, specific])] == ["青海湖", "环保与无人机"]
    assert [hit.topic for hit in strong_hits([top, short])] == ["青海湖"]  # 2 字短词仍不算强


def test_menyuan_entry_does_not_hijack_qinghai_lake_question() -> None:
    """回归（复审 P2）：问「青海湖油菜花」不该把答案推到「门源油菜花」（跨地点误导）。

    此前 门源油菜花 条目的关键词含裸「油菜花」，任何提到油菜花的问题都会被它命中。
    """
    _seed_chunks()
    question = "青海湖油菜花什么时候开"
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, question, limit=3)
    # 检索（prompt 上下文）仍可带上相似条目，但**来源卡片**不该跨地点误导
    cards = [hit.topic for hit in knowledge.strong_hits(hits, question=question)]
    assert "门源油菜花" not in cards
    assert "青海湖" in cards  # 该问的正主仍在卡片里


def test_cycling_keywords_cover_both_spacing_variants() -> None:
    """回归（复审 P2）：「360公里」不带空格的写法也要能命中环湖骑行条目。"""
    _seed_chunks()
    with SessionLocal() as db:
        hits = knowledge.retrieve(db, "环湖骑行360公里要几天", limit=3)
    assert "环湖骑行" in [hit.topic for hit in hits]


def test_zhuoershan_altitude_matches_public_sources() -> None:
    """回归（复审 P1）：卓尔山海拔此前写成 2650 米（低于山脚祁连县城），公开口径约 2930 米。"""
    from app.modules.ai.knowledge_data import KNOWLEDGE_ENTRIES

    entry = next(item for item in KNOWLEDGE_ENTRIES if item["topic"] == "祁连卓尔山")
    assert "2930" in entry["content"]
    assert "2650" not in entry["content"]

"""ai 业务逻辑层。

需求 2.1 / 客服的 AI 能力升级：会话记录 + RAG（N12：向量检索优先、关键词兜底，
见 app/modules/ai/knowledge.py；命中随响应回传，前端展示「参考来源」卡片）+
联网搜索适配器（当前 mock 实现，接真实搜索服务只改 web_search）+
SSE 流式输出（当前 mock 一次性生成后分块吐出）。模型统一走 app/core/llm.py。
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.core import llm, pagination, retention
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.pagination import PageQuery
from app.modules.ai import knowledge, repository
from app.modules.ai.models import AiConversation, AiMessage, AiMessageRole
from app.modules.users.models import User

_SYSTEM_PROMPT = (
    "你是「青海旅游 + 农产品平台」的智能助手，熟悉青海的景点、气候、交通与高原"
    "注意事项，回答要简洁、准确；不确定的信息不要编造。"
)
_FALLBACK_ANSWER = "抱歉，AI 助手暂时不可用，请稍后再试或联系在线客服。"
HISTORY_LIMIT = 6

# 含这些词的提问会额外触发联网搜索适配器（当前为 mock）
_SEARCH_TRIGGERS = ("最新", "实时", "现在", "今天", "天气", "路况", "预约")


def web_search(query: str) -> list[dict[str, str]]:
    """联网搜索适配器（当前为 mock 实现）。

    返回 [{title, url, snippet}]。接入真实搜索服务时只改本函数；
    调用失败由调用方兜底（见 _build_messages）。
    """
    return [
        {
            "title": f"（模拟搜索结果）{query}",
            "url": "https://example.com/mock-search",
            "snippet": f"这是关于「{query}」的模拟实时结果；接入真实搜索服务后替换。",
        }
    ]


def retrieve_knowledge(
    db: Session, question: str, *, limit: int | None = None
) -> list[knowledge.KnowledgeHit]:
    """知识库检索（跨模块入口）——cs 等其它模块**只经本函数**使用向量检索（跨模块只调 service）。"""
    return knowledge.retrieve(db, question, limit=limit)


def _needs_search(question: str) -> bool:
    return any(trigger in question for trigger in _SEARCH_TRIGGERS)


def _build_messages(
    db: Session, conversation: AiConversation, question: str
) -> tuple[list[dict[str, str]], list[str], list[knowledge.KnowledgeHit]]:
    """组装 prompt：系统提示 + RAG 知识 + 联网结果（按需）+ 最近历史 + 当前问题。

    返回 (messages, 联网来源 URL, 知识库命中) —— 命中一并交给调用方，
    以便在响应里回传「参考来源」卡片（N12）。
    """
    context_parts: list[str] = []
    sources: list[str] = []

    hits = knowledge.retrieve(db, question)
    if hits:
        lines = knowledge.build_context(hits)
        context_parts.append(f"【平台知识】\n{lines}")

    if _needs_search(question):
        try:
            results = web_search(question)
        except Exception:  # 搜索不可用不影响主流程
            results = []
        if results:
            lines = "\n".join(f"- {item['title']}：{item['snippet']}" for item in results)
            context_parts.append(f"【联网搜索（参考）】\n{lines}")
            sources = [item["url"] for item in results]

    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if context_parts:
        messages.append({"role": "system", "content": "\n\n".join(context_parts)})
    history = repository.list_recent_messages(db, conversation.id, HISTORY_LIMIT)
    messages += [{"role": message.role, "content": message.content} for message in history]
    messages.append({"role": "user", "content": question})
    return messages, sources, hits


def _get_owned_conversation(db: Session, conversation_id: int, user: User) -> AiConversation:
    conversation = repository.get_conversation(db, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise NotFoundError("会话不存在")
    return conversation


def ask(
    db: Session,
    user: User,
    *,
    question: str,
    conversation_id: int | None = None,
) -> tuple[AiConversation, str, list[str], list[knowledge.KnowledgeHit]]:
    """提问：新建或续聊一个会话，返回 (会话, 回答, 联网来源, 知识库命中)。

    分两个事务提交：会话（如新建）+ 用户提问先落库，避免跨模型调用持有
    未提交事务；模型回答到达后再落库。模型不可用时写入兜底文案（行为不变）。

    模型调用期间用户可能**删掉这个会话**（前端会禁用删除，但 API 不能假设）：
    第二个事务前重新确认会话仍在，否则按「会话不存在」返回 404——不能把
    ObjectDeletedError 漏成 500（复审实测过这条竞态）。
    """
    if conversation_id is None:
        conversation = repository.create_conversation(
            db, AiConversation(user_id=user.id, title=question[:30])
        )
    else:
        conversation = _get_owned_conversation(db, conversation_id, user)

    # 先取值：调用方/并发删除会让 ORM 实例过期，之后不能再读 conversation.id
    conversation_pk = conversation.id
    messages, sources, hits = _build_messages(db, conversation, question)
    repository.add_message(
        db,
        AiMessage(conversation_id=conversation_pk, role=AiMessageRole.USER, content=question),
    )
    db.commit()

    try:
        answer = llm.chat(messages)
    except Exception:  # 模型不可用：兜底文案，仍记录消息
        answer = _FALLBACK_ANSWER

    conversation = repository.get_conversation(db, conversation_pk)
    if conversation is None:  # 回答期间会话被删除：不再落回答
        raise NotFoundError("会话不存在")
    repository.add_message(
        db,
        AiMessage(
            conversation_id=conversation_pk,
            role=AiMessageRole.ASSISTANT,
            content=answer,
            # 只持久化「强命中」（与前端卡片一致；弱命中仅用于本次 prompt 上下文）
            knowledge_sources=[
                {
                    "topic": hit.topic,
                    "score": hit.score,
                    "matched_by": hit.matched_by,
                    "excerpt": hit.excerpt,
                }
                for hit in knowledge.strong_hits(hits, question=question)
            ],
        ),
    )
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    return conversation, answer, sources, hits


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_events(
    conversation_id: int,
    answer: str,
    sources: list[str],
    knowledge_sources: list[dict] | None = None,
) -> Iterator[str]:
    """把答复切成 SSE 事件流。

    当前 mock 模型一次性生成后按块吐出；接入真实流式模型时改为逐 token 转发。
    """
    yield _sse({"conversation_id": conversation_id})
    step = 24
    for index in range(0, len(answer), step):
        yield _sse({"delta": answer[index : index + step]})
    if sources:
        yield _sse({"sources": sources})
    if knowledge_sources:
        yield _sse({"knowledge_sources": knowledge_sources})
    yield "data: [DONE]\n\n"


def list_conversations(
    db: Session, user: User, page: PageQuery
) -> tuple[list[AiConversation], int]:
    return pagination.paginate(db, repository.conversation_list_query(user.id), page)


def get_conversation_detail(
    db: Session, user: User, conversation_id: int
) -> tuple[AiConversation, list[AiMessage]]:
    conversation = _get_owned_conversation(db, conversation_id, user)
    return conversation, repository.list_messages(db, conversation.id)


def rename_conversation(
    db: Session, user: User, conversation_id: int, title: str
) -> AiConversation:
    """重命名会话（仅本人；标题长度由请求模型约束）。"""
    conversation = _get_owned_conversation(db, conversation_id, user)
    repository.rename_conversation(db, conversation, title)  # 标题已由请求模型 strip + 校验
    db.commit()
    return conversation


def delete_conversation(db: Session, user: User, conversation_id: int) -> int:
    """删除会话（仅本人），连同其消息一起删，返回删除的消息条数。"""
    conversation = _get_owned_conversation(db, conversation_id, user)
    messages = repository.delete_conversation(db, conversation)
    db.commit()
    return messages


def purge_expired(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的 AI 消息与空会话（数据保留期清理；跨模块由 maintenance 编排）。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days)
    message_condition = AiMessage.created_at < cutoff
    # 空会话：超过保留期**且已无消息**（消息先删，再收会话）
    no_messages = ~exists().where(AiMessage.conversation_id == AiConversation.id)
    conversation_condition = (AiConversation.updated_at < cutoff) & no_messages

    if dry_run:
        return retention.count_expired(
            db, AiMessage, condition=message_condition, limit=settings.retention_max_per_run
        ) + retention.count_expired(
            db,
            AiConversation,
            condition=conversation_condition,
            limit=settings.retention_max_per_run,
        )

    deleted = retention.batch_delete(
        db,
        AiMessage,
        condition=message_condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )
    deleted += retention.batch_delete(
        db,
        AiConversation,
        condition=conversation_condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )
    return deleted

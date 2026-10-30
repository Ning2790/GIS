"""ai 模块路由：AI 问答与会话（登录用户）。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.pagination import PageParams, page_data
from app.core.rate_limit import rate_limit
from app.core.response import ok
from app.modules.ai import knowledge, service
from app.modules.ai.schemas import (
    AiAskRequest,
    AiAskResponse,
    AiConversationDetail,
    AiConversationPublic,
    AiConversationRenameRequest,
    AiMessagePublic,
    KnowledgeSourceOut,
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/ask",
    summary="提问（不传会话 id 则新建会话）",
    dependencies=[Depends(rate_limit("ai", by="user"))],
)
def ask(payload: AiAskRequest, db: DbSession, current_user: CurrentUser) -> dict:
    conversation, answer, sources, hits = service.ask(
        db, current_user, question=payload.question, conversation_id=payload.conversation_id
    )
    data = AiAskResponse(
        conversation_id=conversation.id,
        answer=answer,
        sources=sources,
        knowledge_sources=[
            KnowledgeSourceOut(
                topic=hit.topic, score=hit.score, matched_by=hit.matched_by, excerpt=hit.excerpt
            )
            for hit in knowledge.strong_hits(hits, question=payload.question)
        ],
    )
    return ok(data.model_dump(mode="json"), msg="回答完成")


@router.post(
    "/ask/stream",
    summary="提问（SSE 流式，前端用 fetch 读取）",
    dependencies=[Depends(rate_limit("ai", by="user"))],
)
def ask_stream(
    payload: AiAskRequest, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    conversation, answer, sources, hits = service.ask(
        db, current_user, question=payload.question, conversation_id=payload.conversation_id
    )
    return StreamingResponse(
        service.sse_events(
            conversation.id,
            answer,
            sources,
            knowledge_sources=[
                {
                    "topic": hit.topic,
                    "score": hit.score,
                    "matched_by": hit.matched_by,
                    "excerpt": hit.excerpt,
                }
                for hit in knowledge.strong_hits(hits, question=payload.question)
            ],
        ),
        media_type="text/event-stream",
    )


@router.get("/conversations", summary="我的会话列表")
def list_conversations(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_conversations(db, current_user, page)
    items = [AiConversationPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.patch("/conversations/{conversation_id}", summary="重命名会话（仅本人）")
def rename_conversation(
    conversation_id: int,
    payload: AiConversationRenameRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    conversation = service.rename_conversation(db, current_user, conversation_id, payload.title)
    return ok(
        AiConversationPublic.model_validate(conversation).model_dump(mode="json"), msg="已重命名"
    )


@router.delete("/conversations/{conversation_id}", summary="删除会话（仅本人，连同消息）")
def delete_conversation(conversation_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    messages = service.delete_conversation(db, current_user, conversation_id)
    return ok({"deleted_messages": messages}, msg="已删除会话")


@router.get("/conversations/{conversation_id}", summary="会话详情（含消息）")
def get_conversation(conversation_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    conversation, messages = service.get_conversation_detail(db, current_user, conversation_id)
    data = AiConversationDetail(
        **AiConversationPublic.model_validate(conversation).model_dump(),
        messages=[AiMessagePublic.model_validate(message) for message in messages],
    )
    return ok(data.model_dump(mode="json"))

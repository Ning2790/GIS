"""cs 模块路由：平台 AI 客服与商家人工客服（需求 4.4）。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.cs import service
from app.modules.cs.schemas import (
    CsMessagePublic,
    CsSessionPublic,
    SendMessageRequest,
    SendMessageResponse,
)
from app.modules.users.models import User

router = APIRouter(prefix="/cs", tags=["cs"])

# 人工客服（商户 / 企业）专用依赖（写法见 app/api/deps.py 的 require_roles）。
AgentUser = Annotated[User, Depends(require_roles(*service.AGENT_ROLES))]


@router.post("/sessions", summary="发起会话（AI 客服接待）")
def create_session(db: DbSession, current_user: CurrentUser) -> dict:
    session = service.create_session(db, current_user)
    return ok(CsSessionPublic.model_validate(session).model_dump(mode="json"), msg="已接入智能客服")


@router.get("/sessions", summary="我的会话列表")
def list_my_sessions(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_my_sessions(db, current_user, page)
    items = [CsSessionPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/queue", summary="人工客服队列（商户 / 企业）")
def list_queue(db: DbSession, page: PageParams, agent: AgentUser) -> dict:
    rows, total = service.list_queue(db, page)
    items = [CsSessionPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/sessions/{session_id}", summary="会话详情")
def get_session(session_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    session = service.get_session_detail(db, session_id, current_user)
    return ok(CsSessionPublic.model_validate(session).model_dump(mode="json"))


@router.get("/sessions/{session_id}/messages", summary="会话消息")
def list_messages(
    session_id: int, db: DbSession, page: PageParams, current_user: CurrentUser
) -> dict:
    rows, total = service.list_messages(db, session_id, current_user, page)
    items = [CsMessagePublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.post("/sessions/{session_id}/messages", summary="发送消息（AI 接待时自动应答）")
def send_message(
    session_id: int, payload: SendMessageRequest, db: DbSession, current_user: CurrentUser
) -> dict:
    message, reply = service.send_message(db, session_id, current_user, payload.content)
    data = SendMessageResponse(
        message=CsMessagePublic.model_validate(message),
        reply=CsMessagePublic.model_validate(reply) if reply is not None else None,
    ).model_dump(mode="json")
    return ok(data, msg="已发送")


@router.post("/sessions/{session_id}/transfer", summary="转人工客服")
def transfer(session_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    session = service.transfer_to_human(db, session_id, current_user)
    return ok(CsSessionPublic.model_validate(session).model_dump(mode="json"), msg="已转接人工客服")


@router.post("/sessions/{session_id}/claim", summary="人工客服接入会话")
def claim(session_id: int, db: DbSession, agent: AgentUser) -> dict:
    session = service.claim(db, session_id, agent)
    return ok(CsSessionPublic.model_validate(session).model_dump(mode="json"), msg="已接入会话")


@router.post("/sessions/{session_id}/release", summary="客服释放会话（回到人工队列）")
def release(session_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    session = service.release_session(db, session_id, current_user)
    return ok(CsSessionPublic.model_validate(session).model_dump(mode="json"), msg="已释放会话")


@router.post("/sessions/{session_id}/close", summary="结束会话")
def close(session_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    session = service.close_session(db, session_id, current_user)
    return ok(CsSessionPublic.model_validate(session).model_dump(mode="json"), msg="会话已结束")

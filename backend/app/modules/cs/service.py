"""cs 业务逻辑层。

需求 4.4：平台 AI 客服 + 商家人工客服。
用户消息在 AI 接待状态下由 app/core/llm.py 统一入口生成应答；转人工后进入队列，
商家（商户 / 企业）从队列接入并人工回复。

客服参与行为（接入 / 释放 / 转人工 / 结束）经 admin 模块的公共审计入口
`admin_service.record_action` 记入 audit_logs，供运营追溯（跨模块只走 service）。
"""

from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core import llm, pagination, retention
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageQuery
from app.modules.admin import service as admin_service
from app.modules.ai import service as ai_service
from app.modules.cs import repository
from app.modules.cs.models import CsMessage, CsSenderType, CsSession, CsSessionStatus
from app.modules.users.models import User, UserRole

# 人工客服角色：商户 / 企业；游客仅可使用 AI 客服。
AGENT_ROLES = (UserRole.MERCHANT, UserRole.ENTERPRISE)

_GREETING = "您好，这里是平台智能客服，请问有什么可以帮您？"
_SYSTEM_PROMPT = "你是青海旅游与农产品平台的智能客服，请简洁、友好地回答用户问题。"
_AI_FALLBACK = "抱歉，AI 助手暂时不可用，已为您转接人工客服，请稍候。"


def _now() -> datetime:
    return datetime.now(UTC)


def _store(
    db: Session,
    session: CsSession,
    sender_type: str,
    sender_id: int | None,
    content: str,
) -> CsMessage:
    """落一条消息并刷新会话活跃时间。"""
    message = repository.add_message(
        db,
        CsMessage(
            session_id=session.id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
        ),
    )
    session.updated_at = _now()
    repository.save_session(db, session)
    return message


def _get_visible_session(db: Session, session_id: int, user: User) -> CsSession:
    """可见性：会话归属用户 / 接入的客服 / 管理员；其余按不存在处理，不泄漏。"""
    session = repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    if user.role == UserRole.ADMIN or session.user_id == user.id or session.agent_id == user.id:
        return session
    raise NotFoundError("会话不存在")


def create_session(db: Session, user: User) -> CsSession:
    """用户发起会话：AI 接待，并落一条开场问候（同一事务）。"""
    session = repository.create_session(db, CsSession(user_id=user.id, status=CsSessionStatus.AI))
    _store(db, session, CsSenderType.AI, None, _GREETING)
    db.commit()
    return session


def list_my_sessions(db: Session, user: User, page: PageQuery) -> tuple[list[CsSession], int]:
    return pagination.paginate(db, repository.my_sessions_query(user.id), page)


def get_session_detail(db: Session, session_id: int, user: User) -> CsSession:
    return _get_visible_session(db, session_id, user)


def list_messages(
    db: Session, session_id: int, user: User, page: PageQuery
) -> tuple[list[CsMessage], int]:
    session = _get_visible_session(db, session_id, user)
    return pagination.paginate(db, repository.messages_query(session.id), page)


def queue_count(db: Session) -> int:
    """等待接入人工客服的会话数（控制台首页概览用）。"""
    return repository.queue_count(db)


def list_queue(db: Session, page: PageQuery) -> tuple[list[CsSession], int]:
    """转人工队列（商家侧，路由层已限定 merchant / enterprise 角色）。"""
    return pagination.paginate(db, repository.queue_query(), page)


def send_message(
    db: Session,
    session_id: int,
    user: User,
    content: str,
) -> tuple[CsMessage, CsMessage | None]:
    """发消息，返回 (本条消息, 即时应答或 None)。

    归属用户在 AI 接待状态下发消息会触发自动应答（入口 app/core/llm.py），
    应答失败时自动转人工并提示；接入的客服以 agent 身份回复，不触发 AI。
    """
    session = _get_visible_session(db, session_id, user)
    if session.status == CsSessionStatus.CLOSED:
        raise ConflictError("会话已结束")
    if session.user_id != user.id and session.agent_id != user.id:
        raise ForbiddenError("只有会话参与方可以发送消息")

    is_agent = session.agent_id == user.id
    if is_agent and session.status != CsSessionStatus.HUMAN:
        raise ConflictError("会话尚未接入人工客服")
    sender = CsSenderType.AGENT if is_agent else CsSenderType.USER
    message = _store(db, session, sender, user.id, content)
    if is_agent or session.status != CsSessionStatus.AI:
        db.commit()  # 人工客服回复：落消息即提交
        return message, None

    # 平台知识库检索（N12，与 AI 问答同一实现）：命中则并入 system 提示，
    # 并在回复末尾附一行「参考」，让用户在客服里也能看到答案依据。
    hits = ai_service.retrieve_knowledge(db, content, limit=2)
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if hits:
        lines = "\n".join(f"- {hit.topic}：{hit.content}" for hit in hits)
        messages.append({"role": "system", "content": "【平台知识】" + "\n" + lines})
    messages.append({"role": "user", "content": content})
    try:
        reply_text = llm.chat(messages)
    except Exception:  # 模型不可用等故障：转人工兜底，不阻断用户使用
        session.status = CsSessionStatus.QUEUED
        session.queued_at = _now()
        reply = _store(db, session, CsSenderType.SYSTEM, None, _AI_FALLBACK)
        db.commit()
        return message, reply
    if hits:
        topics = "、".join(hit.topic for hit in hits)
        reply_text = f"{reply_text}{chr(10)}{chr(10)}参考：{topics}"
    reply = _store(db, session, CsSenderType.AI, None, reply_text)
    db.commit()
    return message, reply


def transfer_to_human(db: Session, session_id: int, user: User) -> CsSession:
    """用户转人工：进入客服队列（仅 AI 接待中的会话可转，条件更新防竞态）。"""
    session = _get_visible_session(db, session_id, user)
    if session.user_id != user.id:
        raise ForbiddenError("只有会话发起人可以转人工")
    if not repository.transfer_to_queue(db, session.id, _now()):
        raise ConflictError("当前状态不可转人工")
    db.refresh(session)
    _store(db, session, CsSenderType.SYSTEM, None, "已为您转接人工客服，请稍候。")
    admin_service.record_action(
        db,
        actor_id=user.id,
        action=admin_service.ACTION_CS_TRANSFER,
        target_type="cs_session",
        target_id=session.id,
        detail=f"用户 {user.phone} 转人工（会话 #{session.id}）",
        commit=False,  # 与状态变更同一事务
    )
    db.commit()
    return session


def claim(db: Session, session_id: int, agent: User) -> CsSession:
    """人工客服接入队列中的会话（原子抢占，先到先得；不能接入自己发起的会话）。"""
    session = repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    if session.user_id == agent.id:
        raise ConflictError("不能接入自己发起的会话")
    if session.status != CsSessionStatus.QUEUED:
        raise ConflictError("该会话不在等待接入状态")
    if not repository.claim_queued(db, session.id, agent.id, _now()):
        raise ConflictError("该会话已被其他客服接入")
    db.refresh(session)
    _store(db, session, CsSenderType.SYSTEM, None, "人工客服已接入，很高兴为您服务。")
    admin_service.record_action(
        db,
        actor_id=agent.id,
        action=admin_service.ACTION_CS_CLAIM,
        target_type="cs_session",
        target_id=session.id,
        detail=f"客服 {agent.phone} 接入会话 #{session.id}",
        commit=False,
    )
    db.commit()
    return session


def release_session(db: Session, session_id: int, user: User) -> CsSession:
    """客服释放会话：回到人工队列等待其他客服接入（管理员可代为操作）。"""
    session = _get_visible_session(db, session_id, user)
    if user.role != UserRole.ADMIN and session.agent_id != user.id:
        raise ForbiddenError("只有接入的客服可以释放会话")
    if not repository.requeue_from_human(db, session.id, _now()):
        raise ConflictError("当前状态不可释放")
    db.refresh(session)
    _store(db, session, CsSenderType.SYSTEM, None, "客服已释放会话，正在重新为您转接。")
    admin_service.record_action(
        db,
        actor_id=user.id,
        action=admin_service.ACTION_CS_RELEASE,
        target_type="cs_session",
        target_id=session.id,
        detail=f"{user.phone} 释放会话 #{session.id} 回队列",
        commit=False,
    )
    db.commit()
    return session


def close_session(db: Session, session_id: int, user: User) -> CsSession:
    """结束会话：发起人 / 接入客服 / 管理员可操作（原子关闭，避免与接入竞态）。"""
    session = _get_visible_session(db, session_id, user)
    if not repository.close_if_open(db, session.id, _now()):
        raise ConflictError("会话已结束")
    db.refresh(session)
    _store(db, session, CsSenderType.SYSTEM, None, "会话已结束，感谢您的咨询。")
    admin_service.record_action(
        db,
        actor_id=user.id,
        action=admin_service.ACTION_CS_CLOSE,
        target_type="cs_session",
        target_id=session.id,
        detail=f"{user.phone}（{user.role}）结束会话 #{session.id}",
        commit=False,
    )
    db.commit()
    return session


def purge_expired(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的客服消息（仅已结单会话）与无消息的已结单会话。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days)
    closed_sessions = select(CsSession.id).where(
        CsSession.status == CsSessionStatus.CLOSED, CsSession.updated_at < cutoff
    )
    message_condition = (CsMessage.created_at < cutoff) & CsMessage.session_id.in_(closed_sessions)
    no_messages = ~exists().where(CsMessage.session_id == CsSession.id)
    session_condition = (
        (CsSession.status == CsSessionStatus.CLOSED) & (CsSession.updated_at < cutoff) & no_messages
    )

    if dry_run:
        return retention.count_expired(
            db, CsMessage, condition=message_condition, limit=settings.retention_max_per_run
        ) + retention.count_expired(
            db, CsSession, condition=session_condition, limit=settings.retention_max_per_run
        )

    deleted = retention.batch_delete(
        db,
        CsMessage,
        condition=message_condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )
    deleted += retention.batch_delete(
        db,
        CsSession,
        condition=session_condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )
    return deleted

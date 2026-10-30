"""ai 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
本层只 flush 不 commit：事务边界由 service 统一控制（与 shop repository 一致）。
"""

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.modules.ai.models import AiConversation, AiMessage


def create_conversation(db: Session, conversation: AiConversation) -> AiConversation:
    db.add(conversation)
    db.flush()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: int) -> AiConversation | None:
    return db.get(AiConversation, conversation_id)


def conversation_list_query(user_id: int) -> Select[tuple[AiConversation]]:
    stmt = select(AiConversation).where(AiConversation.user_id == user_id)
    return stmt.order_by(AiConversation.id.desc())


def add_message(db: Session, message: AiMessage) -> AiMessage:
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def list_messages(db: Session, conversation_id: int) -> list[AiMessage]:
    stmt = (
        select(AiMessage)
        .where(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.id.asc())
    )
    return list(db.scalars(stmt).all())


def list_recent_messages(db: Session, conversation_id: int, limit: int) -> list[AiMessage]:
    """最近 N 条消息（按时间正序返回，用于拼 prompt 的对话历史）。"""
    stmt = (
        select(AiMessage)
        .where(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(list(db.scalars(stmt).all())))


def delete_conversation(db: Session, conversation: AiConversation) -> int:
    """删除会话及其消息，返回删除的消息条数（消息先删，避免悬挂）。"""
    result = db.execute(delete(AiMessage).where(AiMessage.conversation_id == conversation.id))
    messages = int(result.rowcount or 0)
    db.delete(conversation)
    db.flush()
    return messages


def rename_conversation(db: Session, conversation: AiConversation, title: str) -> AiConversation:
    conversation.title = title
    db.flush()
    db.refresh(conversation)
    return conversation

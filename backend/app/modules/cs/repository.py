"""cs 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
本层只 flush 不 commit：事务边界由 service 统一控制（状态变更与审计日志同一事务）。
"""

from datetime import datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.modules.cs.models import CsMessage, CsSession, CsSessionStatus


def create_session(db: Session, session: CsSession) -> CsSession:
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: int) -> CsSession | None:
    return db.get(CsSession, session_id)


def save_session(db: Session, session: CsSession) -> CsSession:
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def add_message(db: Session, message: CsMessage) -> CsMessage:
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def my_sessions_query(user_id: int) -> Select[tuple[CsSession]]:
    return select(CsSession).where(CsSession.user_id == user_id).order_by(CsSession.id.desc())


def queue_count(db: Session) -> int:
    """等待接入人工客服的会话数（控制台首页概览用）。"""
    return (
        db.scalar(
            select(func.count())
            .select_from(CsSession)
            .where(CsSession.status == CsSessionStatus.QUEUED)
        )
        or 0
    )


def queue_query() -> Select[tuple[CsSession]]:
    """转人工队列：按进入队列的时间先到先服务（消息往来不影响排队顺序）。"""
    return (
        select(CsSession)
        .where(CsSession.status == CsSessionStatus.QUEUED)
        .order_by(CsSession.queued_at.asc().nulls_last(), CsSession.id.asc())
    )


def transfer_to_queue(db: Session, session_id: int, now: datetime) -> bool:
    """原子转人工：仅 AI 接待中的会话可进入队列，返回是否成功。"""
    result = db.execute(
        update(CsSession)
        .where(CsSession.id == session_id, CsSession.status == CsSessionStatus.AI)
        .values(status=CsSessionStatus.QUEUED, queued_at=now, updated_at=now)
    )
    db.flush()
    return result.rowcount == 1


def claim_queued(db: Session, session_id: int, agent_id: int, now: datetime) -> bool:
    """原子接入：仅排队中的会话可被接入，返回是否成功（并发下只有一个能抢到）。"""
    result = db.execute(
        update(CsSession)
        .where(CsSession.id == session_id, CsSession.status == CsSessionStatus.QUEUED)
        .values(status=CsSessionStatus.HUMAN, agent_id=agent_id, updated_at=now)
    )
    db.flush()
    return result.rowcount == 1


def requeue_from_human(db: Session, session_id: int, now: datetime) -> bool:
    """原子释放：仅人工服务中的会话可回到队列，返回是否成功。"""
    result = db.execute(
        update(CsSession)
        .where(CsSession.id == session_id, CsSession.status == CsSessionStatus.HUMAN)
        .values(
            status=CsSessionStatus.QUEUED,
            agent_id=None,
            queued_at=now,
            updated_at=now,
        )
    )
    db.flush()
    return result.rowcount == 1


def close_if_open(db: Session, session_id: int, now: datetime) -> bool:
    """原子结束：仅未结束的会话可关闭，返回是否成功（避免与接入操作竞态）。"""
    result = db.execute(
        update(CsSession)
        .where(CsSession.id == session_id, CsSession.status != CsSessionStatus.CLOSED)
        .values(status=CsSessionStatus.CLOSED, closed_at=now, updated_at=now)
    )
    db.flush()
    return result.rowcount == 1


def messages_query(session_id: int) -> Select[tuple[CsMessage]]:
    return select(CsMessage).where(CsMessage.session_id == session_id).order_by(CsMessage.id.asc())

"""cs ORM 模型。

新增或修改表后，需生成 Alembic 迁移：
    uv run alembic revision --autogenerate -m "描述"
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CsSessionStatus:
    """客服会话状态：AI 接待 →（转人工）排队 → 人工服务 → 结束。"""

    AI = "ai"
    QUEUED = "queued"
    HUMAN = "human"
    CLOSED = "closed"


class CsSenderType:
    """消息发送方类型。"""

    USER = "user"
    AI = "ai"
    AGENT = "agent"
    SYSTEM = "system"


class CsSession(Base):
    """客服会话。用户发起后由平台 AI 接待，可转人工；人工客服从队列接入。"""

    __tablename__ = "cs_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default=CsSessionStatus.AI, index=True)
    agent_id: Mapped[int | None] = mapped_column(default=None)  # 接入的人工客服用户 id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    # 进入人工队列的时间；队列按它排序，避免排队期间发消息被刷到队尾。
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class CsMessage(Base):
    """会话消息。sender_id：user / agent 为对应用户 id，ai / system 为空。"""

    __tablename__ = "cs_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(index=True)
    sender_type: Mapped[str] = mapped_column(String(20))
    sender_id: Mapped[int | None] = mapped_column(default=None)
    content: Mapped[str] = mapped_column(Text)
    # 保留期清理按 created_at 删（数据增长方案）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

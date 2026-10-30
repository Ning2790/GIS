"""ai ORM 模型。

新增或修改表后，需生成 Alembic 迁移：
    uv run alembic revision --autogenerate -m "描述"
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiMessageRole:
    """消息角色（与 OpenAI 协议一致）。"""

    USER = "user"
    ASSISTANT = "assistant"


class AiConversation(Base):
    """AI 会话。"""

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiMessage(Base):
    """会话消息（user / assistant）。"""

    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    # 助手消息的知识命中来源（N12 后续）：随消息持久化，重开会话后来源卡片仍可见
    knowledge_sources: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    # 保留期清理按 created_at 删（数据增长方案）：必须有索引，否则删除退化为全表扫描
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class KnowledgeChunk(Base):
    """知识分块（N12 向量检索）。

    向量以 JSON 数组存储（PostgreSQL 落 JSONB、SQLite 落 TEXT），检索在应用层算余弦——
    当前知识库规模（十几条）下足够，且零新依赖；将来换 pgvector 只需替换检索实现
    （见 `app/core/rag.py` 的设计说明与 docs/部署.md）。
    """

    __tablename__ = "ai_knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 一主题一条（种子脚本按 topic 幂等 upsert；同一主题要拆多块时再放开唯一约束）
    topic: Mapped[str] = mapped_column(String(64), unique=True)
    content: Mapped[str] = mapped_column(Text)
    # PG 落 JSONB（用户拍板的载体；将来可加 GIN 索引），SQLite 落 TEXT
    _json_type = JSON().with_variant(JSONB(), "postgresql")
    keywords: Mapped[list] = mapped_column(_json_type, default=list)
    embedding: Mapped[list] = mapped_column(_json_type, default=list)
    # 嵌入元数据：用于检测「配置变了但没重算向量」（维度不一致会静默失效，复审发现）
    embedding_provider: Mapped[str] = mapped_column(String(32), default="")
    embedding_model: Mapped[str] = mapped_column(String(64), default="")
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

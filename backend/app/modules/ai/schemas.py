"""ai 请求 / 响应模型（Pydantic）。"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class AiAskRequest(BaseModel):
    """提问。"""

    question: str = Field(min_length=1, max_length=500, description="问题")
    conversation_id: int | None = Field(default=None, description="续聊的会话 id，不传则新建")


class KnowledgeSourceOut(BaseModel):
    """知识库命中来源（N12 向量检索；前端「参考来源」卡片用）。"""

    topic: str
    score: float = Field(description="余弦相似度（关键词回退时为命中词数）")
    matched_by: str = Field(description="vector = 语义命中 / keyword = 关键词回退")
    excerpt: str


class AiAskResponse(BaseModel):
    """回答。"""

    conversation_id: int
    answer: str
    sources: list[str] = []  # 联网搜索结果链接（mock 搜索适配器）
    knowledge_sources: list[KnowledgeSourceOut] = []  # 平台知识库命中（N12）


#: 会话标题：去首尾空白后 1–128 字，且不含控制字符
#: （控制字符会被数据库拒收成 500，NUL 在 PG 里直接报错；这里前置为 422）
ConversationTitle = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[^\x00-\x1f\x7f]*$",
    ),
]


class AiConversationRenameRequest(BaseModel):
    """重命名会话。空白标题与含控制字符的标题在这里就被拦下（422）。"""

    title: ConversationTitle = Field(description="新标题（去首尾空白后 1–128 字）")


class AiConversationPublic(BaseModel):
    """会话。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class AiMessagePublic(BaseModel):
    """会话消息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    knowledge_sources: list[KnowledgeSourceOut] = []
    created_at: datetime


class AiConversationDetail(AiConversationPublic):
    """会话详情（含消息）。"""

    messages: list[AiMessagePublic] = []

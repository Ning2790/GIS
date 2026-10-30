"""cs 请求 / 响应模型（Pydantic）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    """发送消息。"""

    content: str = Field(min_length=1, max_length=2000, description="消息内容")


class CsSessionPublic(BaseModel):
    """客服会话。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    agent_id: int | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class CsMessagePublic(BaseModel):
    """会话消息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    sender_type: str
    sender_id: int | None = None
    content: str
    created_at: datetime


class SendMessageResponse(BaseModel):
    """发送结果：本条消息 + 可选的即时应答（AI 接待时）。"""

    message: CsMessagePublic
    reply: CsMessagePublic | None = None

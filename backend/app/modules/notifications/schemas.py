"""notifications 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationPublic(BaseModel):
    """站内通知。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    content: str
    ref_type: str | None = None
    ref_id: int | None = None
    is_read: bool
    created_at: datetime

"""admin 请求 / 响应模型（Pydantic）。

审核与用户管理接口的用户信息复用 app.modules.users.schemas 的模型
（跨模块复用 schemas 是允许的，那只是接口契约的形状）。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogPublic(BaseModel):
    """审计日志条目。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None = None  # 系统动作（如超时取消）无操作人
    action: str
    target_type: str
    target_id: int
    detail: str | None = None
    created_at: datetime

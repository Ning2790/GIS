"""admin ORM 模型。

新增或修改表后，需生成 Alembic 迁移：
    uv run alembic revision --autogenerate -m "描述"
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """审核与操作日志：管理员对用户的关键操作，只追加不修改。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(
        index=True, default=None
    )  # 操作人 id；系统动作（如超时取消）为空
    action: Mapped[str] = mapped_column(String(32), index=True)  # 如 review.approve / user.disable
    target_type: Mapped[str] = mapped_column(String(32), default="user")
    target_id: Mapped[int] = mapped_column(index=True)
    detail: Mapped[str | None] = mapped_column(String(255), default=None)  # 可读描述，便于人工排查
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

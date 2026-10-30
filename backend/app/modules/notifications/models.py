"""通知 ORM 模型：站内通知（增强池）。

触发点（由 shop service 在状态变化时调用 `notifications.service.notify`）：
订单支付成功 → 商户；订单发货 → 买家；售后申请 → 商户；售后完成 / 拒绝 → 买家。
通知与业务状态在同一事务里写入（notify 只 flush，commit 由调用方负责）。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationType:
    """通知类型（前端按类型显示图标 / 文案时可用）。"""

    ORDER_PAID = "order.paid"
    ORDER_SHIPPED = "order.shipped"
    AFTER_SALE_CREATED = "after_sale.created"
    AFTER_SALE_RESOLVED = "after_sale.resolved"
    AFTER_SALE_REJECTED = "after_sale.rejected"
    PAYMENT_EXCEPTION = "payment.exception"
    PAYMENT_REFUNDED = "payment.refunded"


class Notification(Base):
    """一条站内通知：谁、什么类型、标题与正文、关联对象（订单 / 售后单）、是否已读。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column()
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(String(255))
    ref_type: Mapped[str | None] = mapped_column(String(32), default=None)  # order / after_sale
    ref_id: Mapped[int | None] = mapped_column(default=None)
    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (
        # 列表：WHERE user_id = ? ORDER BY id DESC
        Index("ix_notifications_user_id_id", "user_id", "id"),
        # 未读计数 / 全部已读：WHERE user_id = ? AND is_read = false
        Index("ix_notifications_user_unread", "user_id", "is_read"),
    )

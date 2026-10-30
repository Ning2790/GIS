"""notifications 业务逻辑层。

`notify()` 供其它模块在业务状态变化时调用（跨模块只走 service）：只 add+flush，
**不 commit**——与调用方的状态变更在同一事务里落库，避免「通知已发、订单没变」。
"""

from sqlalchemy.orm import Session

from app.core import retention
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.pagination import PageQuery, paginate
from app.modules.notifications import repository
from app.modules.notifications.models import Notification
from app.modules.users.models import User


def notify(
    db: Session,
    user_id: int,
    *,
    type: str,
    title: str,
    content: str,
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> Notification:
    """写一条站内通知（不提交，随调用方事务一起落库）。

    标题 / 正文按列宽截断：notify 是跨模块公共入口，超长文案不应把调用方的
    业务事务（支付 / 发货 / 售后）一起打挂。
    """
    return repository.create(
        db,
        Notification(
            user_id=user_id,
            type=type,
            title=title[:64],
            content=content[:255],
            ref_type=ref_type,
            ref_id=ref_id,
            is_read=False,
        ),
    )


def list_notifications(db: Session, user: User, page: PageQuery) -> tuple[list[Notification], int]:
    """我的通知（最新在前）。"""
    return paginate(db, repository.list_query(user.id), page)


def unread_count(db: Session, user: User) -> int:
    return repository.unread_count(db, user.id)


def mark_read(db: Session, user: User, notification_id: int) -> Notification:
    """标记单条已读（仅本人；他人的按不存在处理）。"""
    notification = repository.get(db, notification_id)
    if notification is None or notification.user_id != user.id:
        raise NotFoundError("通知不存在")
    if not notification.is_read:
        repository.mark_read(db, notification)
        db.commit()
    return notification


def mark_all_read(db: Session, user: User) -> int:
    """全部标记已读，返回本次更新条数。"""
    updated = repository.mark_all_read(db, user.id)
    db.commit()
    return updated


def purge_expired(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的通知（数据保留期清理，见 docs/数据增长与归档方案.md）。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days)
    condition = Notification.created_at < cutoff
    if dry_run:
        return retention.count_expired(
            db, Notification, condition=condition, limit=settings.retention_max_per_run
        )
    return retention.batch_delete(
        db,
        Notification,
        condition=condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )

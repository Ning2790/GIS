"""notifications 数据访问层：只 flush 不 commit（事务边界由 service 控制）。"""

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification


def create(db: Session, notification: Notification) -> Notification:
    db.add(notification)
    db.flush()
    return notification


def get(db: Session, notification_id: int) -> Notification | None:
    return db.get(Notification, notification_id)


def list_query(user_id: int) -> Select[tuple[Notification]]:
    return (
        select(Notification).where(Notification.user_id == user_id).order_by(Notification.id.desc())
    )


def unread_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        or 0
    )


def mark_read(db: Session, notification: Notification) -> None:
    notification.is_read = True
    db.flush()


def mark_all_read(db: Session, user_id: int) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.flush()
    # rowcount 为 -1 表示驱动不提供行数（哨兵值），不能当成负数返回给前端
    return max(0, int(result.rowcount or 0))

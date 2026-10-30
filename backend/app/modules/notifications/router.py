"""站内通知路由（登录用户只能看 / 操作自己的通知）。"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationPublic

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", summary="我的通知（最新在前）")
def list_notifications(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_notifications(db, current_user, page)
    items = [NotificationPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/unread-count", summary="未读通知数（顶栏铃铛角标）")
def unread_count(db: DbSession, current_user: CurrentUser) -> dict:
    return ok({"unread": service.unread_count(db, current_user)})


@router.post("/{notification_id}/read", summary="标记单条已读（仅本人）")
def mark_read(notification_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    row = service.mark_read(db, current_user, notification_id)
    return ok(NotificationPublic.model_validate(row).model_dump(mode="json"), msg="已读")


@router.post("/read-all", summary="全部标记已读")
def mark_all_read(db: DbSession, current_user: CurrentUser) -> dict:
    updated = service.mark_all_read(db, current_user)
    return ok({"updated": updated}, msg="已全部标为已读")

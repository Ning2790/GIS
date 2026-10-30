"""admin 模块路由：商户 / 企业资质审核与运营操作。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_roles
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.admin import service
from app.modules.admin.schemas import AuditLogPublic
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserAdminPublic

router = APIRouter(prefix="/admin", tags=["admin"])

# 仅管理员可用（写法见 app/api/deps.py 的 require_roles）。
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("/reviews", summary="待审核商户 / 企业列表")
def list_reviews(db: DbSession, page: PageParams, admin: AdminUser) -> dict:
    rows, total = service.list_pending_reviews(db, page)
    items = [UserAdminPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.post("/reviews/{user_id}/approve", summary="审核通过（通过后即可登录）")
def approve_review(user_id: int, db: DbSession, admin: AdminUser) -> dict:
    user = service.approve(db, user_id, actor_id=admin.id)
    return ok(UserAdminPublic.model_validate(user).model_dump(mode="json"), msg="审核通过")


@router.post("/reviews/{user_id}/reject", summary="审核驳回（驳回后不可登录）")
def reject_review(user_id: int, db: DbSession, admin: AdminUser) -> dict:
    user = service.reject(db, user_id, actor_id=admin.id)
    return ok(UserAdminPublic.model_validate(user).model_dump(mode="json"), msg="已驳回")


@router.post("/users/{user_id}/disable", summary="禁用账号（禁用后不可登录）")
def disable_user(user_id: int, db: DbSession, admin: AdminUser) -> dict:
    user = service.disable_user(db, user_id, actor_id=admin.id)
    return ok(UserAdminPublic.model_validate(user).model_dump(mode="json"), msg="已禁用")


@router.post("/users/{user_id}/enable", summary="解除禁用（恢复为正常状态）")
def enable_user(user_id: int, db: DbSession, admin: AdminUser) -> dict:
    user = service.enable_user(db, user_id, actor_id=admin.id)
    return ok(UserAdminPublic.model_validate(user).model_dump(mode="json"), msg="已启用")


@router.get("/audit-logs", summary="审计日志（审核 / 运营 / 客服流转记录）")
def list_audit_logs(
    db: DbSession,
    page: PageParams,
    admin: AdminUser,
    action: Annotated[str | None, Query(description="按动作过滤，如 review.approve")] = None,
    target_type: Annotated[
        str | None, Query(max_length=32, description="按目标类型过滤：user / cs_session")
    ] = None,
    target_id: Annotated[int | None, Query(description="按目标 id 过滤")] = None,
) -> dict:
    rows, total = service.list_audit_logs(
        db, page, action=action, target_type=target_type, target_id=target_id
    )
    items = [AuditLogPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))

"""用户模块路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import PageParams, page_data
from app.core.response import ok
from app.modules.users import service
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import (
    AddressCreateRequest,
    AddressPublic,
    AddressUpdateRequest,
    ProfileUpdateRequest,
    UserAdminPublic,
    UserPublic,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", summary="获取当前登录用户")
def read_me(current_user: CurrentUser) -> dict:
    return ok(UserPublic.model_validate(current_user).model_dump(mode="json"))


# ---------- 收货地址（个人中心；下单选它时快照进订单） ----------


@router.get("/addresses", summary="我的收货地址（默认在前）")
def list_addresses(db: DbSession, current_user: CurrentUser) -> dict:
    rows = service.list_addresses(db, current_user)
    items = [AddressPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(items, msg=f"共 {len(items)} 个地址")


@router.post("/addresses", summary="新增收货地址（首个自动为默认）")
def create_address(payload: AddressCreateRequest, db: DbSession, current_user: CurrentUser) -> dict:
    created = service.create_address(
        db,
        current_user,
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        address=payload.address,
        is_default=payload.is_default,
    )
    return ok(AddressPublic.model_validate(created).model_dump(mode="json"), msg="地址已保存")


@router.put("/addresses/{address_id}", summary="更新收货地址")
def update_address(
    address_id: int,
    payload: AddressUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    updated = service.update_address(
        db,
        current_user,
        address_id,
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        address=payload.address,
        is_default=payload.is_default,
    )
    return ok(AddressPublic.model_validate(updated).model_dump(mode="json"), msg="地址已更新")


@router.post("/addresses/{address_id}/default", summary="设为默认地址")
def set_default_address(address_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    updated = service.set_default_address(db, current_user, address_id)
    return ok(AddressPublic.model_validate(updated).model_dump(mode="json"), msg="已设为默认")


@router.delete("/addresses/{address_id}", summary="删除收货地址")
def delete_address(address_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    service.delete_address(db, current_user, address_id)
    return ok(None, msg="地址已删除")


@router.put("/me", summary="更新个人资料（昵称）")
def update_me(payload: ProfileUpdateRequest, db: DbSession, current_user: CurrentUser) -> dict:
    user = service.update_profile(db, current_user, nickname=payload.nickname)
    return ok(UserPublic.model_validate(user).model_dump(mode="json"), msg="已保存")


@router.get("", summary="用户列表（管理员）")
def list_users(
    db: DbSession,
    page: PageParams,
    admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    role: Annotated[str | None, Query(description="按角色过滤")] = None,
    status: Annotated[str | None, Query(description="按状态过滤")] = None,
    keyword: Annotated[
        str | None, Query(max_length=64, description="按手机号 / 昵称模糊搜索")
    ] = None,
) -> dict:
    rows, total = service.list_users(db, page, role=role, status=status, keyword=keyword)
    items = [UserAdminPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))

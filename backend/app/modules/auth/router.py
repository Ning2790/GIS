"""认证模块路由：注册、登录、会话（刷新 / 退出）与已登录设备管理。"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import CurrentUser, DbSession
from app.core.errors import BadRequestError
from app.core.rate_limit import client_ip, rate_limit
from app.core.response import ok
from app.modules.auth import service
from app.modules.auth.models import DeviceBinding
from app.modules.auth.schemas import (
    _DEVICE_ID_PATTERN,
    ChangePasswordRequest,
    DevicePublic,
    EnterpriseRegisterRequest,
    LoginRequest,
    RefreshResponse,
    RefreshTokenRequest,
    TokenResponse,
    TouristRegisterRequest,
)
from app.modules.users.schemas import UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


def device_id_header(
    device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None,
) -> str | None:
    """X-Device-Id 头（与请求体 device_id 同一校验口径）。

    头部绕过 Pydantic 校验：超长 / 非法字符会在落库时才炸成 500（且此时密码已改），
    这里提前挡住；空值与未提供等价。
    """
    if not device_id:
        return None
    if not re.fullmatch(_DEVICE_ID_PATTERN, device_id):
        raise BadRequestError("X-Device-Id 格式不合法")
    return device_id


DeviceIdHeader = Annotated[str | None, Depends(device_id_header)]


def _device_payload(binding: DeviceBinding, *, is_current: bool) -> dict:
    return DevicePublic(
        id=binding.id,
        device_label=binding.device_label,
        last_ip=binding.last_ip,
        last_user_agent=binding.last_user_agent,
        first_seen_at=binding.first_seen_at,
        last_seen_at=binding.last_seen_at,
        is_current=is_current,
    ).model_dump(mode="json")


@router.post(
    "/register/tourist",
    summary="游客注册",
    dependencies=[Depends(rate_limit("register"))],
)
def register_tourist(payload: TouristRegisterRequest, db: DbSession) -> dict:
    user = service.register_tourist(db, payload.phone, payload.password, payload.nickname)
    return ok(UserPublic.model_validate(user).model_dump(mode="json"), msg="注册成功")


@router.post(
    "/register/enterprise",
    summary="商户 / 企业注册（需资质，注册后待审核）",
    dependencies=[Depends(rate_limit("register"))],
)
def register_enterprise(payload: EnterpriseRegisterRequest, db: DbSession) -> dict:
    user = service.register_enterprise(
        db,
        phone=payload.phone,
        password=payload.password,
        license_no=payload.license_no,
        license_file=payload.license_file,
        nickname=payload.nickname,
        role=payload.role,
    )
    return ok(UserPublic.model_validate(user).model_dump(mode="json"), msg="注册成功，资质审核中")


@router.post(
    "/login",
    summary="登录（游客 / 商户 / 企业通用）",
    dependencies=[Depends(rate_limit("login"))],
)
def login(
    payload: LoginRequest,
    db: DbSession,
    request: Request,
    user_agent: Annotated[str | None, Header()] = None,
) -> dict:
    token, refresh_token, refresh_expires_in, user = service.login(
        db,
        payload.phone,
        payload.password,
        user_agent=user_agent,
        device_id=payload.device_id,
        device_label=payload.device_label,
        ip=client_ip(request),
        remember=payload.remember,
    )
    data = TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        refresh_expires_in=refresh_expires_in,
        user=UserPublic.model_validate(user),
    ).model_dump(mode="json")
    return ok(data, msg="登录成功")


@router.post("/password", summary="修改密码（撤销其他设备登录，当前端自动续期）")
def change_password(
    payload: ChangePasswordRequest,
    db: DbSession,
    current_user: CurrentUser,
    user_agent: Annotated[str | None, Header()] = None,
    device_id: DeviceIdHeader = None,
) -> dict:
    token, refresh_token, refresh_expires_in = service.change_password(
        db,
        current_user,
        old_password=payload.old_password,
        new_password=payload.new_password,
        user_agent=user_agent,
        device_id=device_id,
        remember=payload.remember,
    )
    data = RefreshResponse(
        access_token=token,
        refresh_token=refresh_token,
        refresh_expires_in=refresh_expires_in,
    ).model_dump(mode="json")
    return ok(data, msg="密码已修改，其他设备已退出登录")


@router.post("/refresh", summary="刷新令牌（旧刷新令牌随之作废；需与登录设备一致）")
def refresh(payload: RefreshTokenRequest, db: DbSession, request: Request) -> dict:
    token, refresh_token, expires_in = service.refresh(
        db,
        payload.refresh_token,
        device_id=payload.device_id,
        ip=client_ip(request),
    )
    data = RefreshResponse(
        access_token=token,
        refresh_token=refresh_token,
        refresh_expires_in=expires_in,
    ).model_dump(mode="json")
    return ok(data, msg="刷新成功")


@router.get("/devices", summary="已登录设备列表（标注当前设备）")
def list_devices(
    db: DbSession,
    current_user: CurrentUser,
    device_id: DeviceIdHeader = None,
) -> dict:
    rows = service.list_devices(db, current_user, current_device_id=device_id)
    data = [_device_payload(binding, is_current=is_current) for binding, is_current in rows]
    return ok(data, msg=f"共 {len(data)} 台设备")


@router.post("/devices/{binding_id}/revoke", summary="移除设备（撤销其名下全部会话）")
def revoke_device(binding_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    binding = service.revoke_device(db, current_user, binding_id=binding_id)
    return ok(_device_payload(binding, is_current=False), msg="设备已移除，该设备需重新登录")


@router.post("/logout", summary="退出登录（撤销刷新令牌）")
def logout(payload: RefreshTokenRequest, db: DbSession) -> dict:
    service.logout(db, payload.refresh_token)
    return ok(None, msg="已退出登录")

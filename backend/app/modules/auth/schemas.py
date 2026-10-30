"""认证模块请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.users.schemas import UserPublic

# 设备标识：客户端生成的随机串（UUID / 随机 hex 等），只允许安全字符集
_DEVICE_ID_PATTERN = r"^[A-Za-z0-9._-]{8,64}$"


def _check_password_bytes(value: str) -> str:
    """bcrypt 上限 72 字节：在这里挡住，返回 422，而不是等落库时变成 500。"""
    if len(value.encode("utf-8")) > 72:
        raise ValueError("密码过长（最多 72 字节，约 24 个汉字）")
    return value


class TouristRegisterRequest(BaseModel):
    """游客注册：手机号 + 密码，注册后即可使用。"""

    phone: str = Field(min_length=11, max_length=20, description="手机号")
    password: str = Field(min_length=6, max_length=64, description="密码")
    nickname: str | None = Field(default=None, max_length=64, description="昵称")

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        return _check_password_bytes(value)


class EnterpriseRegisterRequest(BaseModel):
    """商户 / 企业注册：需提供资质，注册后进入待审核状态。"""

    phone: str = Field(min_length=11, max_length=20, description="手机号")
    password: str = Field(min_length=6, max_length=64, description="密码")
    nickname: str | None = Field(default=None, max_length=64, description="企业 / 商户名称")
    license_no: str = Field(min_length=6, max_length=64, description="营业执照号")
    license_file: str | None = Field(default=None, max_length=255, description="资质文件地址")
    role: str = Field(default="enterprise", description="enterprise 或 merchant")

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        return _check_password_bytes(value)


class LoginRequest(BaseModel):
    """登录：三种角色通用。

    可带上客户端设备标识（需求量 4.2 的「二次访问自动登录」）：
    登录即登记设备绑定，刷新时会话与设备必须匹配；remember 控制「记住我」的有效期。
    """

    phone: str = Field(min_length=11, max_length=20)
    password: str = Field(min_length=1, max_length=64)
    device_id: str | None = Field(
        default=None, pattern=_DEVICE_ID_PATTERN, description="客户端生成并持久化的随机设备标识"
    )
    device_label: str | None = Field(
        default=None, max_length=64, description="可读的设备名（如 Chrome · Windows）"
    )
    remember: bool = Field(default=True, description="记住我：勾选为 30 天免密续期，否则为短期会话")

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        return _check_password_bytes(value)


class TokenResponse(BaseModel):
    """登录成功返回的令牌对与用户信息。"""

    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    refresh_expires_in: int = Field(description="刷新令牌有效期（秒）")
    user: UserPublic


class ChangePasswordRequest(BaseModel):
    """修改密码：需提供原密码与新密码。

    remember 与登录时的「记住我」一致：改密码后当前端会新开会话，
    短期会话（未勾选记住我）不应被悄悄拉长成 30 天。
    """

    old_password: str = Field(min_length=1, max_length=64, description="原密码")
    new_password: str = Field(min_length=6, max_length=64, description="新密码（6–64 位）")
    remember: bool = Field(default=True, description="与登录时的「记住我」一致")

    @field_validator("new_password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        return _check_password_bytes(value)


class RefreshTokenRequest(BaseModel):
    """刷新 / 退出登录请求：携带登录时下发的刷新令牌（与登录时的设备标识）。"""

    refresh_token: str = Field(min_length=16, description="登录时返回的刷新令牌")
    device_id: str | None = Field(
        default=None, pattern=_DEVICE_ID_PATTERN, description="登录时上报过的同一设备标识"
    )


class RefreshResponse(BaseModel):
    """刷新成功返回的新令牌对；旧刷新令牌已随之作废。"""

    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    refresh_expires_in: int = Field(description="刷新令牌有效期（秒）")


class DevicePublic(BaseModel):
    """已登录设备（device_bindings 的对外视图）。"""

    id: int
    device_label: str | None = None
    last_ip: str | None = None
    last_user_agent: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    is_current: bool = False

"""用户模块请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserPublic(BaseModel):
    """对外暴露的用户信息，绝不含密码哈希。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    role: str
    status: str
    nickname: str | None = None
    license_no: str | None = None
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    """更新个人资料（当前仅昵称）。"""

    nickname: str = Field(min_length=1, max_length=64, description="昵称 / 商户名称")


class UserAdminPublic(UserPublic):
    """管理视图：在 UserPublic 基础上补充资质文件地址（仅管理员接口使用）。"""

    license_file: str | None = None


class AddressCreateRequest(BaseModel):
    """新增收货地址（个人中心维护，下单选它时快照进订单）。"""

    receiver_name: str = Field(min_length=1, max_length=32, description="收货人")
    receiver_phone: str = Field(pattern=r"^1[3-9]\d{9}$", description="收货手机号（11 位）")
    address: str = Field(
        min_length=5, max_length=255, description="收货地址（省 / 市 / 区 + 详细地址）"
    )
    is_default: bool = Field(default=False, description="设为默认（首个地址自动为默认）")


class AddressUpdateRequest(AddressCreateRequest):
    """更新收货地址（全量字段）。"""


class AddressPublic(BaseModel):
    """收货地址（个人中心视图）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    receiver_name: str
    receiver_phone: str
    address: str
    is_default: bool
    created_at: datetime

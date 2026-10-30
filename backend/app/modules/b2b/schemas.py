"""b2b 请求 / 响应模型（Pydantic）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SupplyCreateRequest(BaseModel):
    """发布供给信息（商户 / 企业）。"""

    title: str = Field(min_length=1, max_length=128, description="标题")
    category: str = Field(min_length=1, max_length=64, description="品类，如 油菜籽 / 牦牛肉")
    region: str = Field(min_length=1, max_length=64, description="地区 / 州")
    quantity: float = Field(gt=0, le=99_999_999.99, description="数量（与单位配套）")
    unit: str = Field(default="吨", max_length=16, description="单位")
    price_expect: float | None = Field(
        default=None, gt=0, le=99_999_999.99, description="期望价（参考信息，可空）"
    )
    description: str = Field(default="", max_length=2000, description="补充说明")


class DemandCreateRequest(BaseModel):
    """发布需求信息（商户 / 企业）。"""

    title: str = Field(min_length=1, max_length=128, description="标题")
    category: str = Field(min_length=1, max_length=64, description="品类")
    region: str = Field(min_length=1, max_length=64, description="地区 / 州")
    quantity: float = Field(gt=0, le=99_999_999.99, description="需求量（与单位配套）")
    unit: str = Field(default="吨", max_length=16, description="单位")
    price_expect: float | None = Field(
        default=None, gt=0, le=99_999_999.99, description="期望价（参考信息，可空）"
    )
    description: str = Field(default="", max_length=2000, description="补充说明")


class B2bSupplyPublic(BaseModel):
    """供给信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    category: str
    region: str
    quantity: float
    unit: str
    price_expect: float | None = None
    description: str
    status: str
    created_at: datetime


class B2bDemandPublic(BaseModel):
    """需求信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    category: str
    region: str
    quantity: float
    unit: str
    price_expect: float | None = None
    description: str
    status: str
    created_at: datetime


class B2bMatchItem(BaseModel):
    """匹配结果条目。"""

    score: int
    supply: B2bSupplyPublic


class B2bMatchResult(BaseModel):
    """匹配结果（某需求）。"""

    demand: B2bDemandPublic
    matches: list[B2bMatchItem] = []

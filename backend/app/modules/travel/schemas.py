"""travel 请求 / 响应模型（Pydantic）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketPublic(BaseModel):
    """门票。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: float
    description: str | None = None


class AttractionPublic(BaseModel):
    """景点（列表项）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str
    description: str
    latitude: float | None = None
    longitude: float | None = None
    cover_image: str | None = None
    distance_km: float | None = None  # 传 near 排序时返回（计算核心给出）
    created_at: datetime


class AttractionDetail(AttractionPublic):
    """景点详情（含票种）。"""

    tickets: list[TicketPublic] = []


class ItineraryGenerateRequest(BaseModel):
    """生成个性化行程的输入。"""

    days: int = Field(default=3, ge=1, le=15, description="行程天数")
    budget: float | None = Field(
        default=None, gt=0, le=99_999_999.99, description="预算（元，可空）"
    )
    preferences: str = Field(default="", max_length=500, description="偏好（自由文本）")
    fitness: str | None = Field(default=None, max_length=64, description="身体条件 / 体力说明")


class ItineraryStopItem(BaseModel):
    """停靠点（全量替换用；顺序按数组顺序解析）。"""

    attraction_id: int
    day: int = Field(default=1, ge=1, le=15, description="第几天")
    note: str | None = Field(default=None, max_length=255)


class ItineraryStopsReplaceRequest(BaseModel):
    """全量替换行程停靠点（增 / 删 / 排序一次完成）。"""

    stops: list[ItineraryStopItem] = Field(default_factory=list, max_length=40)


class ItineraryStopPublic(BaseModel):
    """停靠点（含景点名，前端可直接展示）。"""

    id: int
    attraction_id: int
    attraction_name: str | None = None
    day: int
    position: int
    note: str | None = None


class ItineraryPublic(BaseModel):
    """行程。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    days: int
    budget: float | None = None
    preferences: str
    fitness: str | None = None
    risk_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ItineraryDetail(ItineraryPublic):
    """行程详情（含停靠点与全程里程）。"""

    stops: list[ItineraryStopPublic] = []
    total_distance_km: float | None = None  # 停靠点齐全且都有坐标时给出（计算核心累加）


class RouteStopPublic(BaseModel):
    """预设路线停靠点（含景点名与坐标，前端可直接展示 / 上图）。"""

    id: int
    attraction_id: int
    attraction_name: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    day: int
    position: int
    note: str | None = None


class RoutePublic(BaseModel):
    """预设路线（列表项）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    theme: str
    days: int
    budget: float | None = None
    description: str
    cover_image: str | None = None
    stop_count: int = 0
    created_at: datetime


class RouteDetail(RoutePublic):
    """预设路线详情（含停靠点与全程里程）。"""

    stops: list[RouteStopPublic] = []
    total_distance_km: float | None = None  # 停靠点齐全且都有坐标时给出（计算核心累加）


class RouteStopItem(BaseModel):
    """运营提交的路线停靠点：数组顺序决定同日内的先后（position 由服务端推导）。"""

    attraction_id: int = Field(gt=0, description="景点 id")
    day: int = Field(default=1, ge=1, le=15, description="第几天")
    note: str | None = Field(default=None, max_length=255, description="当日玩法 / 提示")


class RouteSaveRequest(BaseModel):
    """新建 / 全量更新预设路线（运营后台，管理员）。"""

    name: str = Field(min_length=1, max_length=128, description="路线名称")
    theme: str = Field(default="", max_length=32, description="主题（环湖 / 人文 / 摄影…）")
    days: int = Field(ge=1, le=15, description="天数")
    budget: float | None = Field(
        default=None, ge=0, le=99_999_999.99, description="人均预估（元，可空）"
    )
    description: str = Field(default="", max_length=2000, description="路线介绍")
    stops: list[RouteStopItem] = Field(default_factory=list, max_length=40, description="停靠点")

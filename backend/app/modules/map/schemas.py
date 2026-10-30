"""map 请求 / 响应模型（Pydantic）。"""

from pydantic import BaseModel, ConfigDict


class MapLayerPublic(BaseModel):
    """底图图层。"""

    key: str
    name: str
    url_template: str
    attribution: str


class MapPointPublic(BaseModel):
    """点位（景点坐标）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str
    latitude: float
    longitude: float

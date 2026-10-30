"""gear 请求 / 响应模型（Pydantic）。"""

from datetime import date

from pydantic import BaseModel, ConfigDict


class WeatherSnapshotPublic(BaseModel):
    """环境快照。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str
    snapshot_date: date
    temperature_c: float
    soil_moisture_pct: float
    altitude_m: int
    pressure_hpa: float
    source: str


class GearAdvicePublic(BaseModel):
    """装备建议。"""

    city: str
    date: date
    snapshot: WeatherSnapshotPublic
    items: list[str] = []
    notes: str | None = None

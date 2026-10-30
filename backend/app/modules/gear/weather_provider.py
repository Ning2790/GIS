"""气象数据源适配层（gear 需求 2.2）。

- **真实源**：Open-Meteo（免密钥免费，https://open-meteo.com）。一次请求取回一城数日数据：
  日最高 / 最低气温取均值为当日气温；小时级土壤湿度按本地日期聚合为日均百分比。
- **模拟源**：原确定性实现，作为断网回退（快照 `source=mock` 与真实源区分）。

约定：真实源任何失败（超时 / 非 200 / 响应报错 / 字段缺失 / 未知城市）统一抛
`WeatherProviderError`，由 service 决定跳过该城或整批回退模拟源。
"""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings

# 中国标准时间：快照日期与 Open-Meteo 返回的逐日时间均按此口径（青海无夏令时）
CN_TZ = ZoneInfo("Asia/Shanghai")

MOCK_SOURCE = "mock"
OPENMETEO_SOURCE = "openmeteo"

# 青海各州市（州府驻地）坐标：Open-Meteo 逐城请求用；海拔仍以 service.CITY_ALTITUDE 为准
CITY_COORDS: dict[str, tuple[float, float]] = {
    "西宁市": (36.62554, 101.75739),
    "海东市": (36.48, 102.41639),  # 乐都区
    "海南州": (36.28139, 100.61306),  # 共和县恰卜恰镇
    "海西州": (37.376, 97.37457),  # 德令哈市
    "海北州": (36.87509, 100.96092),  # 海晏县西海镇
    "黄南州": (35.51483, 102.016),  # 同仁市
    "果洛州": (34.47442, 100.24496),  # 玛沁县大武镇
    "玉树州": (33.00118, 97.00893),  # 玉树市
}


class WeatherProviderError(RuntimeError):
    """数据源不可用（网络 / 响应异常 / 未知城市 / 字段缺失）。"""


@dataclass(frozen=True)
class DailyWeather:
    """某城市某日的一条环境数据（provider 对 service 的输出契约）。"""

    day: date
    temperature_c: Decimal
    soil_moisture_pct: Decimal


class WeatherProvider(Protocol):
    """数据源协议：实现方只需给出 source 标识与逐城逐日拉取。"""

    source: str

    def fetch_daily(self, city: str, days: int) -> list[DailyWeather]: ...


class OpenMeteoProvider:
    """Open-Meteo 真实气象源。

    请求天数 = days + 1（含今天）；`base_url` / `timeout` 可覆盖（自建代理或测试打桩）。
    """

    source = OPENMETEO_SOURCE

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.weather_base_url
        self._timeout = timeout or settings.weather_timeout_seconds
        self._transport = transport

    def fetch_daily(self, city: str, days: int) -> list[DailyWeather]:
        coords = CITY_COORDS.get(city)
        if coords is None:
            raise WeatherProviderError(f"未配置 {city} 的坐标，无法走真实气象源")
        params = {
            "latitude": coords[0],
            "longitude": coords[1],
            "daily": "temperature_2m_max,temperature_2m_min",
            "hourly": "soil_moisture_0_to_7cm",
            "forecast_days": days + 1,
            "timezone": "Asia/Shanghai",
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(self._base_url, params=params)
        except httpx.HTTPError as exc:
            raise WeatherProviderError(f"{city} 气象请求失败：{exc}") from exc
        if response.status_code != 200:
            raise WeatherProviderError(
                f"{city} 气象接口返回 HTTP {response.status_code}{_error_reason(response)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherProviderError(f"{city} 气象接口返回非 JSON 内容") from exc
        if payload.get("error"):
            raise WeatherProviderError(f"{city} 气象接口报错：{payload.get('reason', '未知原因')}")
        return _parse_openmeteo(city, payload)


def _error_reason(response: httpx.Response) -> str:
    """尽力从错误响应体取出原因（Open-Meteo 错误形状为 {"error": true, "reason": ...}）。"""
    try:
        reason = (response.json() or {}).get("reason")
    except ValueError:
        return ""
    return f"：{reason}" if reason else ""


def _parse_openmeteo(city: str, payload: dict) -> list[DailyWeather]:
    """解析 Open-Meteo 响应：日均温 = (最高 + 最低) / 2；土壤湿度 m³/m³ → 百分比日均。"""
    daily = payload.get("daily") or {}
    times: list[str] = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    if not times or len(times) != len(highs) or len(times) != len(lows):
        raise WeatherProviderError(f"{city} 气象接口缺少逐日气温字段")

    soil_by_day: dict[str, list[float]] = {}
    hourly = payload.get("hourly") or {}
    for stamp, value in zip(
        hourly.get("time") or [], hourly.get("soil_moisture_0_to_7cm") or [], strict=False
    ):
        if value is None or not stamp:
            continue
        soil_by_day.setdefault(stamp[:10], []).append(float(value))

    rows: list[DailyWeather] = []
    for stamp, high, low in zip(times, highs, lows, strict=False):
        if high is None or low is None or not stamp:
            continue
        samples = soil_by_day.get(stamp[:10]) or []
        if not samples:
            raise WeatherProviderError(f"{city} 气象接口缺少 {stamp} 的土壤湿度")
        mean_soil = sum(samples) / len(samples)
        rows.append(
            DailyWeather(
                day=date.fromisoformat(stamp[:10]),
                temperature_c=((Decimal(str(high)) + Decimal(str(low))) / 2).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                ),
                soil_moisture_pct=(Decimal(str(mean_soil)) * 100).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                ),
            )
        )
    if not rows:
        raise WeatherProviderError(f"{city} 气象接口未返回可用数据")
    return rows


# 各月基准气温（℃），模拟源用
_MONTH_TEMP = {
    1: -12.0,
    2: -9.0,
    3: -3.0,
    4: 4.0,
    5: 9.0,
    6: 13.0,
    7: 16.0,
    8: 15.0,
    9: 11.0,
    10: 4.0,
    11: -4.0,
    12: -10.0,
}


def _seeded_int(seed: str, modulo: int) -> int:
    """确定性伪随机（md5）：同一 seed 永远得到同一值，便于复现与测试。"""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def _mock_temperature(city: str, day: date) -> Decimal:
    base = _MONTH_TEMP.get(day.month, 5.0)
    jitter = _seeded_int(f"{city}:{day.isoformat()}", 50) / 10 - 2.5  # -2.5 .. +2.5
    return Decimal(str(round(base + jitter, 1)))


def _mock_soil_moisture(city: str, day: date) -> Decimal:
    return Decimal(str(round(15 + _seeded_int(f"soil:{city}:{day.isoformat()}", 200) / 10, 1)))


class MockProvider:
    """确定性模拟源：断网回退与固定演示数据（快照 source=mock）。"""

    source = MOCK_SOURCE

    def fetch_daily(self, city: str, days: int) -> list[DailyWeather]:
        today = datetime.now(CN_TZ).date()
        rows: list[DailyWeather] = []
        for offset in range(days + 1):
            day = today + timedelta(days=offset)
            rows.append(
                DailyWeather(
                    day=day,
                    temperature_c=_mock_temperature(city, day),
                    soil_moisture_pct=_mock_soil_moisture(city, day),
                )
            )
        return rows


def get_provider() -> WeatherProvider:
    """按配置选择数据源（WEATHER_PROVIDER=mock 强制模拟，其余一律走真实源）。"""
    if get_settings().weather_provider.lower() == MOCK_SOURCE:
        return MockProvider()
    return OpenMeteoProvider()

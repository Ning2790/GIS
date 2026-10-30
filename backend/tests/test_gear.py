"""gear 模块：环境快照采集与装备建议测试。

采集用例全部打桩（桩 provider / httpx.MockTransport），不连外网。
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.gear import repository as gear_repository
from app.modules.gear import service as gear_service
from app.modules.gear.models import GearRecommendation, WeatherSnapshot
from app.modules.gear.weather_provider import (
    CN_TZ,
    DailyWeather,
    MockProvider,
    OpenMeteoProvider,
    WeatherProviderError,
    get_provider,
)


class _StubProvider:
    """测试桩数据源：返回固定数据；对指定城市抛数据源错误。"""

    source = "stub"

    def __init__(self, *, fail: set[str] | None = None, temperature: float = 5.0) -> None:
        self._fail = fail or set()
        self._temperature = temperature

    def fetch_daily(self, city: str, days: int) -> list[DailyWeather]:
        if city in self._fail:
            raise WeatherProviderError(f"{city} 桩数据源故障")
        today = datetime.now(CN_TZ).date()
        return [
            DailyWeather(
                day=today + timedelta(days=offset),
                temperature_c=Decimal(str(self._temperature)),
                soil_moisture_pct=Decimal("20.0"),
            )
            for offset in range(days + 1)
        ]


def _seed_snapshot(
    city: str,
    day: date,
    *,
    temp: float,
    altitude: int,
    moisture: float,
    pressure: float,
    source: str = "test",
) -> None:
    with SessionLocal() as db:
        db.add(
            WeatherSnapshot(
                city=city,
                snapshot_date=day,
                temperature_c=temp,
                soil_moisture_pct=moisture,
                altitude_m=altitude,
                pressure_hpa=pressure,
                source=source,
            )
        )
        db.commit()


def _snapshot_row(city: str, day: date) -> tuple[float, float, str] | None:
    """返回 (气温, 土壤湿度, 来源)；无该快照则 None。"""
    with SessionLocal() as db:
        snapshot = gear_repository.get_snapshot(db, city=city, snapshot_date=day)
        if snapshot is None:
            return None
        return float(snapshot.temperature_c), float(snapshot.soil_moisture_pct), snapshot.source


# ---------- 采集：幂等 / 逐城容错 / 整批回退 / 刷新 ----------


def test_collect_is_idempotent() -> None:
    with SessionLocal() as db:
        first = gear_service.collect_snapshots(
            db, cities=["测试州市"], days=2, provider=MockProvider()
        )
        second = gear_service.collect_snapshots(
            db, cities=["测试州市"], days=2, provider=MockProvider()
        )
    assert first == 3  # 今天 + 未来 2 天
    assert second == 0


def test_collect_skips_failed_city_only() -> None:
    """逐城容错：一城失败只跳过该城，其他城市照常采集。"""
    provider = _StubProvider(fail={"故障城"})
    with SessionLocal() as db:
        created = gear_service.collect_snapshots(
            db, cities=["故障城", "正常城"], days=1, provider=provider
        )
    assert created == 2  # 仅正常城：今天 + 1 天
    today = datetime.now(CN_TZ).date()
    assert _snapshot_row("故障城", today) is None
    row = _snapshot_row("正常城", today)
    assert row is not None and row[2] == "stub"


def test_collect_falls_back_to_mock_when_all_fail() -> None:
    """整批失败（疑似断网）：自动降级模拟源，快照 source=mock 区分。"""
    provider = _StubProvider(fail={"甲城", "乙城"})
    with SessionLocal() as db:
        created = gear_service.collect_snapshots(
            db, cities=["甲城", "乙城"], days=1, provider=provider
        )
    assert created == 4  # 两城 ×（今天 + 1 天），全部来自回退的模拟源
    today = datetime.now(CN_TZ).date()
    for city in ("甲城", "乙城"):
        row = _snapshot_row(city, today)
        assert row is not None and row[2] == "mock"


def test_refresh_replaces_snapshot_and_advice() -> None:
    """--refresh：删除区间内旧快照与建议后重新采集。"""
    today = datetime.now(CN_TZ).date()
    _seed_snapshot("刷新城", today, temp=-30.0, altitude=2500, moisture=1.0, pressure=750.0)
    with SessionLocal() as db:
        snapshot = gear_repository.get_snapshot(db, city="刷新城", snapshot_date=today)
        assert snapshot is not None
        db.add(GearRecommendation(snapshot_id=snapshot.id, items='["旧建议"]', notes="旧文案"))
        db.commit()

    provider = _StubProvider(temperature=8.0)
    with SessionLocal() as db:
        created = gear_service.collect_snapshots(
            db, cities=["刷新城"], days=0, provider=provider, refresh=True
        )
    assert created == 1

    row = _snapshot_row("刷新城", today)
    assert row is not None
    assert row[0] == 8.0  # 旧值 -30.0 已被替换
    assert row[2] == "stub"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GearRecommendation)) == 0


def test_refresh_keeps_other_cities() -> None:
    """--refresh 只清理目标城市，其他城市既有快照不动。"""
    today = datetime.now(CN_TZ).date()
    _seed_snapshot("保留城", today, temp=1.0, altitude=2500, moisture=10.0, pressure=750.0)
    with SessionLocal() as db:
        gear_service.collect_snapshots(
            db, cities=["刷新城"], days=0, provider=_StubProvider(), refresh=True
        )
    row = _snapshot_row("保留城", today)
    assert row is not None and row[0] == 1.0 and row[2] == "test"


def test_refresh_keeps_data_when_fetch_fails() -> None:
    """--refresh 下取数失败的城市保留原数据（不先删后采造成空窗）。"""
    today = datetime.now(CN_TZ).date()
    _seed_snapshot("断网城", today, temp=-30.0, altitude=2500, moisture=1.0, pressure=750.0)
    with SessionLocal() as db:
        created = gear_service.collect_snapshots(
            db,
            cities=["断网城"],
            days=0,
            provider=_StubProvider(fail={"断网城"}),
            refresh=True,
        )
    # 既有数据未被删除；整批失败触发的模拟源回退也因该日已存在而跳过
    assert created == 0
    row = _snapshot_row("断网城", today)
    assert row is not None and row[0] == -30.0 and row[2] == "test"


# ---------- Open-Meteo 真实源：解析 / 换算 / 异常 ----------


def _openmeteo_payload() -> dict:
    """两天的最小响应：日均温 (17+3)/2=10.0、(12+2)/2=7.0；土壤湿度 0.1→10%、0.3→30%。"""
    return {
        "daily": {
            "time": ["2026-10-14", "2026-10-15"],
            "temperature_2m_max": [17.0, 12.0],
            "temperature_2m_min": [3.0, 2.0],
        },
        "hourly": {
            "time": [f"2026-10-14T{hour:02d}:00" for hour in range(24)]
            + [f"2026-10-15T{hour:02d}:00" for hour in range(24)],
            "soil_moisture_0_to_7cm": [0.1] * 24 + [0.3] * 24,
        },
    }


def test_openmeteo_provider_parses_and_converts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["timezone"] == "Asia/Shanghai"
        assert request.url.params["forecast_days"] == "2"
        return httpx.Response(200, json=_openmeteo_payload())

    provider = OpenMeteoProvider(transport=httpx.MockTransport(handler))
    rows = provider.fetch_daily("西宁市", days=1)

    assert rows == [
        DailyWeather(
            day=date(2026, 10, 14),
            temperature_c=Decimal("10.0"),
            soil_moisture_pct=Decimal("10.0"),  # 0.1 m³/m³ → 10%
        ),
        DailyWeather(
            day=date(2026, 10, 15),
            temperature_c=Decimal("7.0"),
            soil_moisture_pct=Decimal("30.0"),
        ),
    ]


def test_openmeteo_provider_raises_on_error_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": True, "reason": "Invalid value"})

    provider = OpenMeteoProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(WeatherProviderError, match="Invalid value"):
        provider.fetch_daily("西宁市", days=1)


def test_openmeteo_provider_raises_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OpenMeteoProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(WeatherProviderError):
        provider.fetch_daily("西宁市", days=1)


def test_openmeteo_provider_rejects_unknown_city() -> None:
    provider = OpenMeteoProvider(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(WeatherProviderError, match="坐标"):
        provider.fetch_daily("不存在城", days=1)


def test_openmeteo_provider_requires_soil_moisture() -> None:
    payload = _openmeteo_payload()
    payload["hourly"]["soil_moisture_0_to_7cm"] = [None] * 48

    provider = OpenMeteoProvider(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    with pytest.raises(WeatherProviderError, match="土壤湿度"):
        provider.fetch_daily("西宁市", days=1)


def test_get_provider_respects_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "weather_provider", "mock")
    assert isinstance(get_provider(), MockProvider)
    monkeypatch.setattr(settings, "weather_provider", "openmeteo")
    assert isinstance(get_provider(), OpenMeteoProvider)


# ---------- 装备建议接口 ----------


def test_advice_rules_and_cache(client: TestClient) -> None:
    day = datetime.now(UTC).date() + timedelta(days=1)
    _seed_snapshot("测试高原城", day, temp=-8.5, altitude=3700, moisture=30.5, pressure=650.2)

    resp = client.get("/api/v1/gear/advice", params={"city": "测试高原城", "date": day.isoformat()})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["snapshot"]["altitude_m"] == 3700
    assert data["snapshot"]["temperature_c"] == -8.5

    items = data["items"]
    assert any("羽绒服" in item for item in items)  # 低温
    assert any("氧气" in item for item in items)  # 高海拔
    assert any("防水" in item for item in items)  # 土壤湿度高
    assert any("防晒" in item for item in items)  # 青海常备
    assert data["notes"]

    # 缓存：同一快照第二次请求返回同一组建议
    resp2 = client.get(
        "/api/v1/gear/advice", params={"city": "测试高原城", "date": day.isoformat()}
    )
    assert resp2.json()["data"]["items"] == items


def test_advice_requires_snapshot(client: TestClient) -> None:
    resp = client.get("/api/v1/gear/advice", params={"city": "不存在市", "date": "2099-01-01"})
    assert resp.status_code == 404
    assert resp.json()["code"] == 40400


def test_snapshots_list_with_filter(client: TestClient) -> None:
    day = datetime.now(UTC).date() + timedelta(days=2)
    _seed_snapshot("测试列表城", day, temp=5, altitude=2200, moisture=18, pressure=780)

    resp = client.get("/api/v1/gear/snapshots", params={"city": "测试列表城", "page_size": 10})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["city"] == "测试列表城"
    assert data["items"][0]["source"] == "test"


def test_worker_task_is_registered() -> None:
    """Celery 任务注册检查（不启动 worker，仅确认接线正确）。"""
    from app.worker import celery_app

    assert "gear.collect_weather_snapshots" in celery_app.tasks

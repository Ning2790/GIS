"""gear 业务逻辑层。

需求 2.2：结合气象 / 土壤 / 海拔 / 气压给行前装备建议。
采集走 `weather_provider` 适配层：默认 Open-Meteo 真实源（免密钥），逐城失败跳过，
整批失败（多为断网）自动回退模拟源；`collect_snapshots(refresh=True)` 可把历史模拟数据换新。
建议为确定性规则 + 模型文案（模型不可用有兜底），同一快照只生成一次（缓存）。
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import llm, pagination, retention
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.pagination import PageQuery
from app.modules.gear import repository
from app.modules.gear.models import GearRecommendation, WeatherSnapshot
from app.modules.gear.weather_provider import (
    CN_TZ,
    MOCK_SOURCE,
    DailyWeather,
    MockProvider,
    WeatherProvider,
    WeatherProviderError,
    get_provider,
)

logger = logging.getLogger(__name__)

# 青海各州市的海拔基准（米）：用于计算气压与高反提示
CITY_ALTITUDE: dict[str, int] = {
    "西宁市": 2261,
    "海东市": 2100,
    "海南州": 2870,
    "海西州": 2980,
    "海北州": 3000,
    "黄南州": 2500,
    "果洛州": 3720,
    "玉树州": 3700,
}
DEFAULT_ALTITUDE = 2500
FORECAST_DAYS = 7

_ALWAYS_ITEMS = ["防晒霜（SPF50+）", "墨镜与遮阳帽", "润唇膏"]
_FALLBACK_NOTES = "高原昼夜温差大，注意保暖防晒；初到高原避免剧烈运动，多饮水。"


def _pressure_for_altitude(altitude_m: int) -> Decimal:
    """国际标准大气近似：海拔越高气压越低。"""
    ratio = 1 - 2.25577e-5 * altitude_m
    return Decimal(str(round(1013.25 * (ratio**5.25588), 1)))


def _persist_rows(db: Session, city: str, rows: list[DailyWeather], *, source: str) -> int:
    """落库一批逐日快照（幂等：已存在的 (city, date) 跳过），返回新增条数。

    逐条提交：并发采集（手动脚本与定时任务同时跑）撞唯一约束时只跳过该条，
    不回滚同批次已写入的其他快照。
    """
    altitude = CITY_ALTITUDE.get(city, DEFAULT_ALTITUDE)
    created = 0
    for row in rows:
        if repository.get_snapshot(db, city=city, snapshot_date=row.day) is not None:
            continue
        try:
            repository.create_snapshot(
                db,
                WeatherSnapshot(
                    city=city,
                    snapshot_date=row.day,
                    temperature_c=row.temperature_c,
                    soil_moisture_pct=row.soil_moisture_pct,
                    altitude_m=altitude,
                    pressure_hpa=_pressure_for_altitude(altitude),
                    source=source,
                ),
            )
            db.commit()
            created += 1
        except IntegrityError:
            # 并发采集撞 (city, date) 唯一约束：跳过该条即可（幂等语义）
            db.rollback()
    return created


def collect_snapshots(
    db: Session,
    *,
    cities: list[str] | None = None,
    days: int = FORECAST_DAYS,
    provider: WeatherProvider | None = None,
    refresh: bool = False,
) -> int:
    """采集各城市未来数日（含今天）的环境快照，返回新增条数。

    - 逐城容错：某城请求失败只跳过该城并告警，不影响其他城市；
    - 整批失败：全部城市都失败时（多为断网）自动降级模拟源，只补缺失的城市 / 日期
      （快照 source=mock 以区分），不覆盖既有数据；
    - `refresh=True`：**逐城先取数、成功后**才删除该城区间内的旧快照与对应建议，再写入新数据
      （用于把历史模拟数据换成真实数据；取数失败的城市保留原数据，不清空）。
    """
    target_cities = cities or list(CITY_ALTITUDE.keys())
    if not target_cities:
        return 0
    today = datetime.now(CN_TZ).date()
    end = today + timedelta(days=days)

    active = provider or get_provider()
    created = 0
    failed: list[str] = []
    for city in target_cities:
        try:
            rows = active.fetch_daily(city, days)
        except WeatherProviderError as exc:
            logger.warning("气象采集失败，跳过 %s：%s", city, exc)
            failed.append(city)
            continue
        if refresh:
            deleted = repository.delete_snapshots_in_range(db, cities=[city], start=today, end=end)
            db.commit()
            if deleted:
                logger.info("refresh：%s 已删除 %s 条旧快照（及其建议），重新采集", city, deleted)
        created += _persist_rows(db, city, rows, source=active.source)

    if len(failed) == len(target_cities) and active.source != MOCK_SOURCE:
        logger.warning("气象源 %s 全部城市采集失败（疑似断网），本次降级模拟源", active.source)
        fallback = MockProvider()
        for city in target_cities:
            rows = fallback.fetch_daily(city, days)
            created += _persist_rows(db, city, rows, source=fallback.source)
    return created


def _build_items(snapshot: WeatherSnapshot) -> list[str]:
    """确定性建议规则：温度 / 海拔 / 土壤湿度 / 气压。"""
    items: list[str] = list(_ALWAYS_ITEMS)
    temperature = float(snapshot.temperature_c)
    if temperature <= 0:
        items += ["羽绒服 / 厚棉衣", "保暖内衣与手套"]
    elif temperature <= 10:
        items += ["冲锋衣 + 抓绒内胆"]
    else:
        items += ["薄外套（早晚温差大）"]
    if snapshot.altitude_m >= 3000:
        items += ["便携氧气瓶", "红景天（建议提前 3-5 天服用）"]
    if snapshot.altitude_m >= 3500:
        items += ["血氧仪与常用高反药物"]
    if float(snapshot.soil_moisture_pct) >= 25:
        items += ["防水鞋套 / 雨具"]
    if float(snapshot.pressure_hpa) < 700:
        items += ["行程放缓，给身体适应海拔的时间"]
    return items


def get_advice(
    db: Session, *, city: str, day: date | None = None
) -> tuple[WeatherSnapshot, GearRecommendation]:
    """按城市 / 日期给装备建议（公开）。同一快照只生成一次，结果缓存复用。"""
    target = day or datetime.now(CN_TZ).date()
    snapshot = repository.get_snapshot(db, city=city, snapshot_date=target)
    if snapshot is None:
        raise NotFoundError(
            "暂无该城市该日期的环境数据，请先运行采集（scripts/collect_weather.py）"
        )
    cached = repository.get_recommendation_by_snapshot(db, snapshot.id)
    if cached is not None:
        return snapshot, cached

    items = _build_items(snapshot)
    try:
        notes = llm.chat(
            [
                {"role": "system", "content": "你是青海旅行装备顾问。"},
                {
                    "role": "user",
                    "content": (
                        f"游客将在 {target} 前往 {city}，气温约 {snapshot.temperature_c}℃、"
                        f"海拔 {snapshot.altitude_m} 米，请用一句话给出装备与高原注意事项。"
                    ),
                },
            ]
        )
    except Exception:  # 模型不可用时用兜底文案
        notes = _FALLBACK_NOTES
    try:
        # try 从 create_recommendation 起：其内部 flush 时即执行 INSERT，
        # 并发首访的 snapshot_id 唯一约束冲突在这一步抛出。
        recommendation = repository.create_recommendation(
            db,
            GearRecommendation(
                snapshot_id=snapshot.id,
                items=json.dumps(items, ensure_ascii=False),
                notes=notes,
            ),
        )
        db.commit()
    except IntegrityError:
        # 并发首访同一快照：回滚并复用先到者已生成的建议
        db.rollback()
        cached = repository.get_recommendation_by_snapshot(db, snapshot.id)
        if cached is not None:
            return snapshot, cached
        raise
    return snapshot, recommendation


def list_snapshots(
    db: Session,
    page: PageQuery,
    *,
    city: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[WeatherSnapshot], int]:
    stmt = repository.snapshot_list_query(city=city, date_from=date_from, date_to=date_to)
    return pagination.paginate(db, stmt, page)


def purge_expired(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的气象快照（按 snapshot_date；默认 30 天）。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days).date()
    condition = WeatherSnapshot.snapshot_date < cutoff
    if dry_run:
        return retention.count_expired(
            db, WeatherSnapshot, condition=condition, limit=settings.retention_max_per_run
        )
    return retention.batch_delete(
        db,
        WeatherSnapshot,
        condition=condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )

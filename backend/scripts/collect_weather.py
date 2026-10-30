"""手动触发一次环境快照采集（幂等：已存在的城市 / 日期跳过）。

用法（在 backend 目录下）：
    uv run python scripts/collect_weather.py            # 增量采集（默认 Open-Meteo 真实源）
    uv run python scripts/collect_weather.py --refresh  # 先删旧快照与建议再重采（换成真实数据）

数据源由 .env 的 WEATHER_PROVIDER 决定（openmeteo 默认 / mock 模拟）；
真实源整批失败（断网）时自动回退模拟源并告警日志。
定时采集见 app/worker.py（Celery Beat 每天 06:00）。
"""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.gear import service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="采集青海各州市环境快照")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="先删除目标城市区间内的既有快照与建议，再重新采集（把模拟数据换成真实数据）",
    )
    parser.add_argument(
        "--days", type=int, default=service.FORECAST_DAYS, help="采集未来天数（含今天）"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        created = service.collect_snapshots(db, days=args.days, refresh=args.refresh)
    print(f"本次新增 {created} 条环境快照（已存在的城市 / 日期跳过）。")


if __name__ == "__main__":
    main()

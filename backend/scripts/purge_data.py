"""按保留期清理超期数据（维护卡 P1，方案见 docs/数据增长与归档方案.md）。

用法（backend 目录）：
    uv run python scripts/purge_data.py          # 演练：只统计各表将删除的条数（默认）
    uv run python scripts/purge_data.py --yes    # 实际执行删除（分批、带单次上限）

保留期在 `app/core/config.py` 的 `retention_*`（0 = 关闭该类清理）。
Celery Beat 每天 04:00 也会自动跑一次（任务 `maintenance.purge_expired_data`）。
"""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.maintenance import service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="按保留期清理超期数据")
    parser.add_argument(
        "--yes", action="store_true", help="实际执行删除（不加此参数只演练、不改数据）"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if not args.yes:
            results = service.purge_expired_data(db, dry_run=True)
            print("【演练】以下为按当前保留期**将**删除的条数（加 --yes 才真正执行）：")
        else:
            before = service.table_growth(db)
            results = service.purge_expired_data(db)
            after = service.table_growth(db)
            print("【执行】按保留期清理完成；删除前后行数对比：")
            for name in before:
                print(f"  {name:20} {before[name]:>8} → {after[name]:>8}")
        print(service.summary(results))
        for item in results:
            if item.get("skipped"):
                print(f"  - {item['table']}：跳过（{item['skipped']}）")


if __name__ == "__main__":
    main()

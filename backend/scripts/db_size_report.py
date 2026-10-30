"""表增长与体量巡检（P0 观测，见 docs/数据增长与归档方案.md）。

用法（backend 目录）：
    uv run python scripts/db_size_report.py            # 全表行数 + 大小 + 超阈值标红
    uv run python scripts/db_size_report.py --top 20   # 只看最大的 20 张表

口径：
- PostgreSQL：读 `pg_stat_user_tables`（行数为统计值，非精确值）+ `pg_total_relation_size`；
- SQLite：退化为精确 `count(*)`（无大小统计）——够开发环境看行数趋势。
- 阈值：单表 > 200 万行或 > 1 GB 标 `!`；> 500 万行或 > 2 GB 标 `!!`（仅提示，不阻断）。

为什么需要它：保留期清理（P1）与归档/分区（P3/P4）的触发条件都依赖"表有多大、涨得多快"，
先有观测再动刀。建议每周跑一次并把输出存档（或接进运维巡检）。
"""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import engine  # noqa: E402

#: (行数阈值, 大小阈值字节) → 级别；从高到低匹配
LEVELS = [
    (5_000_000, 2 * 1024**3, "!!"),
    (2_000_000, 1 * 1024**3, "! "),
]


def _rows_pg(conn) -> list[tuple[str, int, int]]:
    """PG：返回 [(表, 行数, 字节)]，按大小降序。"""
    result = conn.execute(
        text(
            "select relname, n_live_tup, pg_total_relation_size(relid) "
            "from pg_stat_user_tables order by pg_total_relation_size(relid) desc"
        )
    )
    return [(name, int(rows), int(size)) for name, rows, size in result]


def _rows_sqlite(conn) -> list[tuple[str, int, int]]:
    """SQLite：无大小统计，返回 [(表, 行数, 0)]，按行数降序。"""
    names = inspect(conn).get_table_names()
    rows: list[tuple[str, int, int]] = []
    for name in names:
        count = conn.execute(text(f'select count(*) from "{name}"')).scalar_one()
        rows.append((name, int(count), 0))
    return sorted(rows, key=lambda item: item[1], reverse=True)


def _human(size: int) -> str:
    """字节数转可读（B 取整，其余保留一位小数）。"""
    if not size:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _level(rows: int, size: int) -> str:
    for row_limit, size_limit, mark in LEVELS:
        if rows >= row_limit or (size and size >= size_limit):
            return mark
    return "  "


def main() -> None:
    parser = argparse.ArgumentParser(description="表增长与体量巡检")
    parser.add_argument("--top", type=int, default=0, help="只显示最大的 N 张表（0 = 全部）")
    args = parser.parse_args()

    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            rows = _rows_pg(conn)
        else:
            rows = _rows_sqlite(conn)
        dialect = engine.dialect.name

    if args.top > 0:
        rows = rows[: args.top]
    if not rows:
        print("没有用户表。")
        return

    total_rows = sum(item[1] for item in rows)
    total_size = sum(item[2] for item in rows)
    print(
        f"数据库方言: {dialect}｜表数: {len(rows)}"
        f"｜行数合计: {total_rows:,}｜体量合计: {_human(total_size)}"
    )
    print(f"{'':2} {'表':38} {'行数':>12} {'大小':>10}")
    for name, count, size in rows:
        print(f"{_level(count, size)} {name:38} {count:>12,} {_human(size):>10}")
    alerts = [name for name, count, size in rows if _level(count, size) != "  "]
    if alerts:
        print("\n超过阈值（建议纳入归档/分区评估）：" + "、".join(alerts))
        print("判定与处置见 docs/数据增长与归档方案.md §三。")
    else:
        print("\n当前所有表均低于阈值（200 万行 / 1 GB）。")


if __name__ == "__main__":
    main()

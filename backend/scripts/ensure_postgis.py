"""确保当前数据库已创建 PostGIS 扩展（幂等；N15 容器化）。

为什么需要：`attractions.geom` 等迁移依赖 PostGIS，而 postgis 镜像**只对默认库**
（`POSTGRES_DB`）自动建扩展——手动新建的库、或外部托管的 PostgreSQL 不会带上它，
首次 `alembic upgrade head` 会直接失败（本仓库曾经的手工步骤，见 docs/部署.md）。

用法（容器入口在迁移前调用；也可手动执行）：
    uv run python scripts/ensure_postgis.py

SQLite（本地开发默认）直接跳过；非 PostgreSQL 方言、或不具备建扩展权限时**只警告不阻断**
（环境可能已由 DBA 建好扩展）。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import engine  # noqa: E402


def main() -> int:
    url = get_settings().database_url
    if not url.startswith(("postgresql", "postgres")):
        print(f"[ensure_postgis] 非 PostgreSQL（{url.split(':', 1)[0]}），跳过")
        return 0
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        print("[ensure_postgis] postgis 扩展已就绪")
    except Exception as exc:
        # 失败就是硬错误：后续迁移必然缺类型/函数，早报比晚报好定位（实测无权限时报
        # `permission denied to create extension`，需超级用户或由 DBA 预建）
        detail = f"{exc.__class__.__name__}: {exc}"
        print(f"[ensure_postgis] 失败：{detail}", file=sys.stderr)
        print(
            "  请确认：① DATABASE_URL 指向的库可连；② 该库允许建扩展"
            "（postgis 镜像的默认库会自动建好；外部托管 PG 需 DBA 执行 "
            "CREATE EXTENSION postgis）",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

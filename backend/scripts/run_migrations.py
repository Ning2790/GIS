"""带分布式锁的迁移执行器（N15：多副本 / 多机并发安全）。

问题：`alembic upgrade head` 没有跨进程互斥。两个 api 副本同时对**空库**迁移时，
第二个会因 `pg_type_typname_nsp_index` 唯一约束冲突而崩溃（实测：exit 1），
配合 `restart: unless-stopped` 会进入崩溃-重启循环。

做法：PostgreSQL 上先取会话级 advisory lock（带超时重试），拿到锁的实例执行迁移，
其余实例等锁；迁移完成后释放。SQLite / 其它方言直接执行（单机开发场景）。

用法（容器入口在迁移前调用；也可手动执行）：
    uv run python scripts/run_migrations.py
"""

import subprocess
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import engine  # noqa: E402

# 任意常量：只要全项目一致即可（不同项目间也不会互相阻塞——锁的命名空间是数据库级）
_LOCK_KEY = 8_927_411
_LOCK_WAIT_SECONDS = 180


def _alembic_upgrade() -> int:
    return subprocess.call(["alembic", "upgrade", "head"])


def main() -> int:
    url = get_settings().database_url
    if not url.startswith(("postgresql", "postgres")):
        return _alembic_upgrade()

    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    with engine.connect() as conn:
        while True:
            acquired = conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY}
            ).scalar()
            if acquired:
                break
            if time.monotonic() > deadline:
                print(
                    f"[migrate] 等待迁移锁超过 {_LOCK_WAIT_SECONDS}s"
                    "（可能有其它实例正在迁移），放弃",
                    file=sys.stderr,
                )
                return 1
            print("[migrate] 其它实例正在迁移，等待锁…", file=sys.stderr)
            time.sleep(2)
        try:
            return _alembic_upgrade()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})


if __name__ == "__main__":
    raise SystemExit(main())

"""手动触发一次「超时未支付订单自动取消」（演示 / 运维用，幂等）。

用法（在 backend 目录下）：
    uv run python scripts/expire_orders.py

超时窗口由 .env 的 ORDER_EXPIRE_MINUTES 决定（默认 30；演示时可临时调小，如 1，实测超时取消）。
定时任务见 app/worker.py（Celery Beat 每分钟扫描）。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.shop import service  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        expired = service.expire_unpaid_orders(db)
    minutes = get_settings().order_expire_minutes
    print(f"本次自动取消 {expired} 个超时未支付订单（超时窗口 {minutes} 分钟，库存已回补）。")


if __name__ == "__main__":
    main()

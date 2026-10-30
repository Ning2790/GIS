"""手动触发一次「自动确认收货」（演示 / 运维用，幂等）。

用法（在 backend 目录下）：
    uv run python scripts/auto_confirm_orders.py

触发条件（谁先到算谁）：签收后 ORDER_AUTO_CONFIRM_DAYS（默认 7）天未确认收货；
一直未标记签收时，发货后 ORDER_AUTO_CONFIRM_FALLBACK_DAYS（默认 15）天兜底。
演示可用 .env 临时调小这两个值。
定时任务见 app/worker.py（Celery Beat 每小时扫描）。
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
        confirmed = service.auto_confirm_received_orders(db)
    settings = get_settings()
    print(
        f"本次自动确认收货 {confirmed} 个订单"
        f"（签收后 {settings.order_auto_confirm_days} 天 / 发货后兜底 "
        f"{settings.order_auto_confirm_fallback_days} 天）。"
    )


if __name__ == "__main__":
    main()

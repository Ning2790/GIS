"""Celery 应用与定时任务（气象采集 / 订单超时等后台任务）。

启动（backend 目录；需先配置 CELERY_BROKER_URL，见 .env.example）：
    uv run celery -A app.worker worker -B -l info
未配置 broker 时 worker / beat 无法启动，但手动脚本不受影响：
    uv run python scripts/collect_weather.py
    uv run python scripts/expire_orders.py
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()

# worker 也走 N8 的日志装配（dev 可读 / 非 dev JSON + 脱敏）。Celery 默认会「劫持」根 logger
# 并套用自己的格式（且不脱敏），故显式关闭劫持——任务里 logger.exception 的堆栈因此同样脱敏。
setup_logging()

celery_app = Celery(
    "qh_platform",
    broker=settings.celery_broker_url or "memory://",
    backend=settings.celery_broker_url or None,
)
celery_app.conf.worker_hijack_root_logger = False
celery_app.conf.timezone = "Asia/Shanghai"
celery_app.conf.beat_schedule = {
    "collect-weather-snapshots": {
        "task": "gear.collect_weather_snapshots",
        "schedule": crontab(hour=6, minute=0),  # 每天 06:00 采集各城市未来数日快照
    },
    "cleanup-expired-sessions": {
        "task": "auth.cleanup_expired_sessions",
        "schedule": crontab(hour=3, minute=0),  # 每天 03:00 清理过期 / 久撤销登录会话
    },
    "expire-unpaid-orders": {
        "task": "shop.expire_unpaid_orders",
        # 每分钟扫描一次：超过 ORDER_EXPIRE_MINUTES（默认 30）未支付的订单自动取消并回补库存
        "schedule": crontab(minute="*"),
    },
    "purge-expired-data": {
        "task": "maintenance.purge_expired_data",
        # 每天 04:00（避开 03:00 会话清理）：按保留期清理行为 / 日志类数据，见数据增长方案
        "schedule": crontab(hour=4, minute=0),
    },
    "auto-confirm-received-orders": {
        "task": "shop.auto_confirm_received_orders",
        # 每小时扫描：签收后 N 天（默认 7）/ 发货后兜底天数未确认，则自动确认收货
        "schedule": crontab(minute=10),
    },
}


@celery_app.task(name="gear.collect_weather_snapshots")
def collect_weather_snapshots() -> int:
    """定时采集环境快照（跨模块只走 gear 的 service）。"""
    from app.db.session import SessionLocal
    from app.modules.gear import service

    with SessionLocal() as db:
        return service.collect_snapshots(db)


@celery_app.task(name="auth.cleanup_expired_sessions")
def cleanup_expired_sessions() -> int:
    """定时清理登录会话（跨模块只走 auth 的 service）。"""
    from app.db.session import SessionLocal
    from app.modules.auth import service

    with SessionLocal() as db:
        return service.cleanup_expired_sessions(db)


@celery_app.task(name="maintenance.purge_expired_data")
def purge_expired_data() -> str:
    """定时按保留期清理（跨模块只走 maintenance 的 service）；返回一行摘要进任务日志。"""
    from app.db.session import SessionLocal
    from app.modules.maintenance import service

    with SessionLocal() as db:
        results = service.purge_expired_data(db)
        return service.summary(results)


@celery_app.task(name="shop.expire_unpaid_orders")
def expire_unpaid_orders() -> int:
    """定时取消超时未支付订单（跨模块只走 shop 的 service）。"""
    from app.db.session import SessionLocal
    from app.modules.shop import service

    with SessionLocal() as db:
        return service.expire_unpaid_orders(db)


@celery_app.task(name="shop.auto_confirm_received_orders")
def auto_confirm_received_orders() -> int:
    """定时自动确认收货（签收后超期 / 发货后兜底；跨模块只走 shop 的 service）。"""
    from app.db.session import SessionLocal
    from app.modules.shop import service

    with SessionLocal() as db:
        return service.auto_confirm_received_orders(db)

"""数据保留期清理（维护卡 P0+P1，方案见 docs/数据增长与归档方案.md）。

分工：
- `app/core/retention.py`：通用的「按时间列批量删除」助手（限速、分批、可计数）；
- 本模块只做**编排与只读统计**：跨模块的业务调用一律走各自 service（清理函数与审计写入），
  仅 `table_growth` 的只读计数直接查表（无业务逻辑）；
- 各业务模块 `service.purge_expired(...)`：定义**自己模块**的保留期与删除条件
  （跨模块只走 service）；
- `app/modules/maintenance/service.py`：编排各模块 + 读配置 + 汇总结果（本文件）。

为什么分批：大表一次 DELETE 几十万行会持有长事务、膨胀 WAL 并阻塞其他写入；
这里每批 `retention_batch_size` 条、批间由外层循环自然间隔，单表单次上限 `retention_max_per_run`，
超出的留到下一次（任务每天跑，能持续收敛）。
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import get_settings
from app.core.retention import batch_delete, count_expired
from app.modules.admin import service as admin_service
from app.modules.ai import service as ai_service
from app.modules.cs import service as cs_service
from app.modules.gear import service as gear_service
from app.modules.notifications import service as notifications_service
from app.modules.shop import service as shop_service

logger = logging.getLogger(__name__)


def purge_expired_data(db: Session, *, dry_run: bool = False) -> list[dict[str, int | str]]:
    """按配置清理超期数据，返回每张表的处理结果（table / days / deleted 或 skipped）。

    `dry_run=True` 只统计（截至单次上限），不删除——运维先看量再动手。
    保留期配置 <= 0 表示该类清理关闭（跳过）。
    """
    settings = get_settings()
    specs = [
        ("ai_messages", settings.retention_ai_messages_days, ai_service.purge_expired),
        ("cs_messages", settings.retention_cs_messages_days, cs_service.purge_expired),
        ("product_views", settings.retention_product_views_days, shop_service.purge_expired_views),
        ("audit_logs", settings.retention_audit_logs_days, admin_service.purge_expired_audit_logs),
        (
            "weather_snapshots",
            settings.retention_weather_snapshots_days,
            gear_service.purge_expired,
        ),
        ("inventory", settings.retention_inventory_days, shop_service.purge_expired_inventory),
        (
            "notifications",
            settings.retention_notifications_days,
            notifications_service.purge_expired,
        ),
    ]

    results: list[dict[str, int | str]] = []
    for table, days, purge in specs:
        if days <= 0:
            results.append({"table": table, "days": days, "skipped": "保留期配置为 0（关闭）"})
            continue
        try:
            if dry_run:
                deleted = purge(db, days=days, dry_run=True)
            else:
                deleted = purge(db, days=days)
                metrics.retention_deleted_total.labels(table=table).inc(deleted)
        except Exception as exc:  # noqa: BLE001 - 单表失败不拖垮其它表的清理
            db.rollback()
            logger.error("保留期清理失败：table=%s days=%s error=%s", table, days, exc)
            results.append({"table": table, "days": days, "skipped": f"失败：{exc}"})
            continue
        results.append({"table": table, "days": days, "deleted": deleted})
        if deleted:
            logger.info("保留期清理：table=%s days=%s deleted=%s", table, days, deleted)
    return results


def summary(results: list[dict[str, int | str]]) -> str:
    """一行摘要（worker 日志 / 脚本输出共用）。"""
    total = sum(int(item.get("deleted") or 0) for item in results)
    parts = [f"{item['table']}={item.get('deleted', '跳过')}" for item in results]
    return f"保留期清理合计 {total} 条：" + "，".join(parts)


def table_growth(db: Session) -> dict[str, int]:
    """各表当前行数（维护脚本与测试用；PostgreSQL 走统计值，其它方言走 count）。"""
    from app.modules.admin.models import AuditLog
    from app.modules.ai.models import AiConversation, AiMessage
    from app.modules.cs.models import CsMessage, CsSession
    from app.modules.gear.models import WeatherSnapshot
    from app.modules.notifications.models import Notification
    from app.modules.shop.models import InventoryMovement, ProductView

    counts: dict[str, int] = {}
    for name, model in (
        ("ai_messages", AiMessage),
        ("ai_conversations", AiConversation),
        ("cs_messages", CsMessage),
        ("cs_sessions", CsSession),
        ("audit_logs", AuditLog),
        ("weather_snapshots", WeatherSnapshot),
        ("product_views", ProductView),
        ("inventory", InventoryMovement),
        ("notifications", Notification),
    ):
        counts[name] = int(db.scalar(select(func.count()).select_from(model)) or 0)
    return counts


def count_before_purge(db: Session, *, days: int, model: type) -> int:
    """辅助：按天数统计将删除条数（脚本 dry-run 与测试用）。"""
    return count_expired(db, model, days=days)


__all__ = ["batch_delete", "count_expired", "purge_expired_data", "summary", "table_growth"]

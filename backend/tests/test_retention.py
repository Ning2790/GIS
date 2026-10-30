"""数据保留期清理（维护卡 P0+P1）测试：旧数据删、新数据留、关闭态跳过、dry-run 不改数据、单次上限。

断言一律按**本次插入的行 id** 判断（不按内容或全局计数），用例之间互不干扰。
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.admin.models import AuditLog
from app.modules.ai.models import AiConversation, AiMessage, AiMessageRole
from app.modules.cs.models import CsMessage, CsSenderType, CsSession, CsSessionStatus
from app.modules.gear.models import WeatherSnapshot
from app.modules.notifications.models import Notification
from app.modules.shop.models import InventoryMovement, ProductView
from app.modules.users.models import User, UserRole, UserStatus


def _old(days: int = 3) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _seed_old_and_new() -> dict[str, object]:
    """造「旧 + 新」各一条数据；返回 {名称: 行 id}（旧数据应被删、新数据应保留）。"""
    ids: dict[str, object] = {}
    with SessionLocal() as db:
        suffix = "".join("012345"[(ord(char) % 6)] for char in uuid.uuid4().hex[:8])
        user = User(
            phone="137" + suffix,
            password_hash="x",
            role=UserRole.TOURIST,
            status=UserStatus.ACTIVE,
            nickname="保留期用例",
        )
        db.add(user)
        db.flush()

        old_conversation = AiConversation(user_id=user.id, title="保留期-旧", updated_at=_old())
        new_conversation = AiConversation(user_id=user.id, title="保留期-新")
        db.add_all([old_conversation, new_conversation])
        db.flush()
        old_message = AiMessage(
            conversation_id=old_conversation.id,
            role=AiMessageRole.USER,
            content="旧消息",
            created_at=_old(),
        )
        new_message = AiMessage(
            conversation_id=new_conversation.id, role=AiMessageRole.USER, content="新消息"
        )
        db.add_all([old_message, new_message])

        closed = CsSession(user_id=user.id, status=CsSessionStatus.CLOSED, updated_at=_old())
        open_session = CsSession(user_id=user.id, status=CsSessionStatus.HUMAN)
        db.add_all([closed, open_session])
        db.flush()
        old_cs_message = CsMessage(
            session_id=closed.id,
            sender_type=CsSenderType.USER,
            content="旧客服消息",
            created_at=_old(),
        )
        new_cs_message = CsMessage(
            session_id=closed.id, sender_type=CsSenderType.USER, content="新客服消息"
        )
        open_session_old_message = CsMessage(
            session_id=open_session.id,
            sender_type=CsSenderType.USER,
            content="未结单的旧消息（必须保留）",
            created_at=_old(),
        )
        db.add_all([old_cs_message, new_cs_message, open_session_old_message])

        old_view = ProductView(user_id=user.id, product_id=1, viewed_at=_old())
        new_view = ProductView(user_id=user.id, product_id=2)
        old_inventory = InventoryMovement(product_id=1, change=-1, created_at=_old())
        new_inventory = InventoryMovement(product_id=1, change=1)
        old_audit = AuditLog(actor_id=user.id, action="test.old", target_id=1, created_at=_old())
        new_audit = AuditLog(actor_id=user.id, action="test.new", target_id=1)
        old_notification = Notification(
            user_id=user.id,
            type="order.paid",
            title="旧通知",
            content="旧通知",
            created_at=_old(),
        )
        new_notification = Notification(
            user_id=user.id, type="order.paid", title="新通知", content="新通知"
        )
        today = datetime.now(UTC).date()
        weather_city = f"保留期城-{uuid.uuid4().hex[:6]}"
        old_weather = WeatherSnapshot(
            city=weather_city,
            snapshot_date=today - timedelta(days=10),
            temperature_c=1,
            soil_moisture_pct=1,
            altitude_m=1,
            pressure_hpa=1,
        )
        new_weather = WeatherSnapshot(
            city=weather_city,
            snapshot_date=today,
            temperature_c=1,
            soil_moisture_pct=1,
            altitude_m=1,
            pressure_hpa=1,
        )
        db.add_all(
            [
                old_view,
                new_view,
                old_inventory,
                new_inventory,
                old_audit,
                new_audit,
                old_notification,
                new_notification,
                old_weather,
                new_weather,
            ]
        )
        db.commit()

        ids = {
            "old_conversation": old_conversation.id,
            "old_ai_message": old_message.id,
            "new_ai_message": new_message.id,
            "old_cs_message": old_cs_message.id,
            "new_cs_message": new_cs_message.id,
            "open_session_old_message": open_session_old_message.id,
            "old_view": old_view.id,
            "new_view": new_view.id,
            "old_inventory": old_inventory.id,
            "new_inventory": new_inventory.id,
            "old_audit": old_audit.id,
            "new_audit": new_audit.id,
            "old_notification": old_notification.id,
            "new_notification": new_notification.id,
            "old_weather": old_weather.id,
            "new_weather": new_weather.id,
        }
    return ids


def _exists(model: type, row_id: int) -> bool:
    with SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(model).where(model.id == row_id)) or 0
    return int(count) > 0


def _configure(monkeypatch, *, days: int) -> None:
    settings = get_settings()
    for field in (
        "retention_ai_messages_days",
        "retention_cs_messages_days",
        "retention_product_views_days",
        "retention_audit_logs_days",
        "retention_weather_snapshots_days",
        "retention_inventory_days",
        "retention_notifications_days",
    ):
        monkeypatch.setattr(settings, field, days)
    monkeypatch.setattr(settings, "retention_batch_size", 10)
    monkeypatch.setattr(settings, "retention_max_per_run", 100)


def test_purge_removes_only_expired_rows(monkeypatch, client) -> None:
    ids = _seed_old_and_new()
    _configure(monkeypatch, days=1)
    from app.modules.maintenance import service as maintenance

    with SessionLocal() as db:
        results = maintenance.purge_expired_data(db)
    deleted = {item["table"]: item.get("deleted", 0) for item in results}
    assert all(
        deleted[table] >= 1
        for table in (
            "ai_messages",
            "cs_messages",
            "product_views",
            "audit_logs",
            "weather_snapshots",
            "inventory",
            "notifications",
        )
    )

    # 旧数据全删；新数据全留；未结单会话的旧消息必须保留
    assert not _exists(AiMessage, int(ids["old_ai_message"]))
    assert _exists(AiMessage, int(ids["new_ai_message"]))
    assert not _exists(AiConversation, int(ids["old_conversation"]))
    assert not _exists(CsMessage, int(ids["old_cs_message"]))
    assert _exists(CsMessage, int(ids["new_cs_message"]))
    assert _exists(CsMessage, int(ids["open_session_old_message"]))
    assert not _exists(ProductView, int(ids["old_view"]))
    assert _exists(ProductView, int(ids["new_view"]))
    assert not _exists(InventoryMovement, int(ids["old_inventory"]))
    assert _exists(InventoryMovement, int(ids["new_inventory"]))
    assert not _exists(AuditLog, int(ids["old_audit"]))
    assert _exists(AuditLog, int(ids["new_audit"]))
    assert not _exists(Notification, int(ids["old_notification"]))
    assert _exists(Notification, int(ids["new_notification"]))
    assert not _exists(WeatherSnapshot, int(ids["old_weather"]))
    assert _exists(WeatherSnapshot, int(ids["new_weather"]))


def test_dry_run_does_not_delete(monkeypatch, client) -> None:
    ids = _seed_old_and_new()
    _configure(monkeypatch, days=1)
    from app.modules.maintenance import service as maintenance

    with SessionLocal() as db:
        results = maintenance.purge_expired_data(db, dry_run=True)
    # dry-run 只统计：报告「将删除 N 条」，但一条都不删
    assert any(int(item.get("deleted") or 0) > 0 for item in results)
    assert _exists(AiMessage, int(ids["old_ai_message"]))
    assert _exists(AuditLog, int(ids["old_audit"]))


def test_retention_zero_disables_table(monkeypatch, client) -> None:
    ids = _seed_old_and_new()
    _configure(monkeypatch, days=0)
    from app.modules.maintenance import service as maintenance

    with SessionLocal() as db:
        results = maintenance.purge_expired_data(db)
    assert all("skipped" in item for item in results)
    assert _exists(AiMessage, int(ids["old_ai_message"]))  # 关闭后不删
    assert _exists(AuditLog, int(ids["old_audit"]))


def test_purge_respects_per_run_limit(monkeypatch, client) -> None:
    # 清掉其它用例留下的旧审计行，让本用例的 5 行成为唯一候选
    with SessionLocal() as db:
        db.execute(delete(AuditLog).where(AuditLog.created_at < _old()))
        db.commit()
        rows = [
            AuditLog(actor_id=1, action="limit.test", target_id=1, created_at=_old())
            for _ in range(5)
        ]
        db.add_all(rows)
        db.commit()
        ids = [row.id for row in rows]

    _configure(monkeypatch, days=1)
    monkeypatch.setattr(get_settings(), "retention_max_per_run", 2)
    from app.modules.maintenance import service as maintenance

    with SessionLocal() as db:
        results = maintenance.purge_expired_data(db)
    audit = next(item for item in results if item["table"] == "audit_logs")
    assert audit["deleted"] == 2  # 单次上限 2：其余留到下次
    with SessionLocal() as db:
        left = db.scalars(select(AuditLog.id).where(AuditLog.id.in_(ids))).all()
    assert len(left) == 3  # 5 条删 2 条，剩 3 条等下次运行

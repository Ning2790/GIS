"""admin 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
"""

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.modules.admin.models import AuditLog


def create_log(db: Session, log: AuditLog) -> AuditLog:
    """写入一条审计日志（只 flush；提交由 service 决定，见 record_action）。"""
    db.add(log)
    db.flush()
    db.refresh(log)
    return log


def audit_log_query(
    *,
    action: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
) -> Select[tuple[AuditLog]]:
    """审计日志查询：按动作 / 目标类型 / 目标过滤，最新在前。"""
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if target_id is not None:
        stmt = stmt.where(AuditLog.target_id == target_id)
    return stmt.order_by(AuditLog.id.desc())

"""admin 业务逻辑层。

管理员专属操作。用户数据一律通过 app.modules.users.service 读写（跨模块只走 service）；
本模块负责审计日志（audit_logs）的落库与查询，并提供**跨模块公共审计入口**
`record_action`（其他模块的关键操作经它记录，见 cs 的接入 / 转接 / 结束）。
"""

from sqlalchemy.orm import Session

from app.core import retention
from app.core.config import get_settings
from app.core.pagination import PageQuery, paginate
from app.modules.admin import repository
from app.modules.admin.models import AuditLog
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus

# 审计动作码（写入 audit_logs.action）
ACTION_REVIEW_APPROVE = "review.approve"
ACTION_REVIEW_REJECT = "review.reject"
ACTION_USER_DISABLE = "user.disable"
ACTION_USER_ENABLE = "user.enable"
# 业务动作（买家 / 管理员 / 系统在关键链路上的操作）
ACTION_ORDER_CANCEL = "order.cancel"
ACTION_ORDER_EXPIRE = "order.expire"
ACTION_ORDER_SHIP = "order.ship"
ACTION_ORDER_DELIVER = "order.deliver"
ACTION_ORDER_RECEIVE = "order.receive"
ACTION_ORDER_AUTO_CONFIRM = "order.auto_confirm"
# 售后单（N4）：买家申请 / 商户受理 / 完成 / 拒绝 / 买家撤销
ACTION_AFTER_SALE_CREATE = "after_sale.create"
ACTION_AFTER_SALE_ACCEPT = "after_sale.accept"
ACTION_AFTER_SALE_RESOLVE = "after_sale.resolve"
ACTION_AFTER_SALE_REJECT = "after_sale.reject"
ACTION_AFTER_SALE_WITHDRAW = "after_sale.withdraw"
ACTION_PAYMENT_CALLBACK = "payment.callback"
ACTION_PAYMENT_EXCEPTION = "payment.exception"  # 支付成功但订单不可支付（待退款）
ACTION_PAYMENT_REFUND = "payment.refund"  # 管理员登记退款完成
ACTION_ROUTE_CREATE = "route.create"
ACTION_ROUTE_UPDATE = "route.update"
ACTION_ROUTE_DELETE = "route.delete"
# 客服会话流转（参与方为商户 / 企业客服，供运营追溯）
ACTION_CS_CLAIM = "cs.claim"
ACTION_CS_RELEASE = "cs.release"
ACTION_CS_TRANSFER = "cs.transfer"
ACTION_CS_CLOSE = "cs.close"


def record_action(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    target_id: int,
    target_type: str = "user",
    detail: str | None = None,
    commit: bool = True,
) -> AuditLog:
    """公共审计入口：记一条审计日志（其他模块只能经本函数写日志）。

    actor_id 为 None 表示系统动作（如待支付订单超时自动取消），不是某个人发起的。

    commit=True（默认）表示「业务已经提交、这里补记一条日志」，写完即提交；
    commit=False 时只 flush，把日志并入调用方事务，由调用方一起提交——
    适合「状态变更与日志必须同生共死」的场景（此时调用方需自行 db.commit()）。
    """
    log = repository.create_log(
        db,
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        ),
    )
    if commit:
        db.commit()
    return log


def _log(
    db: Session,
    *,
    actor_id: int,
    action: str,
    target_id: int,
    detail: str | None = None,
) -> AuditLog:
    """记录一条用户维度的审计日志（管理员操作）。"""
    return record_action(db, actor_id=actor_id, action=action, target_id=target_id, detail=detail)


def list_pending_reviews(db: Session, page: PageQuery) -> tuple[list[User], int]:
    """待审核的商户 / 企业列表（游客不存在待审核状态，无需再按角色过滤）。"""
    return users_service.list_users(db, page, status=UserStatus.PENDING_REVIEW)


def approve(db: Session, user_id: int, *, actor_id: int) -> User:
    """资质审核通过并记录日志，返回更新后的用户。"""
    user = users_service.approve(db, user_id)
    _log(
        db,
        actor_id=actor_id,
        action=ACTION_REVIEW_APPROVE,
        target_id=user.id,
        detail=f"{user.phone} 资质审核通过",
    )
    return user


def reject(db: Session, user_id: int, *, actor_id: int) -> User:
    """驳回资质并记录日志，返回更新后的用户。"""
    user = users_service.reject(db, user_id)
    _log(
        db,
        actor_id=actor_id,
        action=ACTION_REVIEW_REJECT,
        target_id=user.id,
        detail=f"{user.phone} 资质被驳回",
    )
    return user


def disable_user(db: Session, user_id: int, *, actor_id: int) -> User:
    """禁用账号并记录日志，返回更新后的用户。"""
    user = users_service.disable(db, user_id)
    _log(
        db,
        actor_id=actor_id,
        action=ACTION_USER_DISABLE,
        target_id=user.id,
        detail=f"{user.phone} 被禁用",
    )
    return user


def enable_user(db: Session, user_id: int, *, actor_id: int) -> User:
    """解除禁用并记录日志，返回更新后的用户。"""
    user = users_service.enable(db, user_id)
    _log(
        db,
        actor_id=actor_id,
        action=ACTION_USER_ENABLE,
        target_id=user.id,
        detail=f"{user.phone} 已启用",
    )
    return user


def list_audit_logs(
    db: Session,
    page: PageQuery,
    *,
    action: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
) -> tuple[list[AuditLog], int]:
    """分页查询审计日志（最新在前），可按动作 / 目标类型 / 目标过滤。"""
    stmt = repository.audit_log_query(action=action, target_type=target_type, target_id=target_id)
    return paginate(db, stmt, page)


def purge_expired_audit_logs(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的审计日志（保留期默认 365 天，高于合规下限 6 个月）。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days)
    condition = AuditLog.created_at < cutoff
    if dry_run:
        return retention.count_expired(
            db, AuditLog, condition=condition, limit=settings.retention_max_per_run
        )
    return retention.batch_delete(
        db,
        AuditLog,
        condition=condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )

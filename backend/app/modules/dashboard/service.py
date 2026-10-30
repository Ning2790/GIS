"""dashboard 业务逻辑层：控制台首页概览聚合。

跨模块数据一律经各模块 service 获取（不直接读别人 repository / models）。

角色差异：
- admin：全平台商品 / 订单统计 + 用户总数 / 待审核数 + 最近审计日志；
- merchant / enterprise：自己的商品 / 订单统计 + 库存预警；
- cs 排队数：两者都看（客服工作台入口）。
"""

from sqlalchemy.orm import Session

from app.core.pagination import PageQuery
from app.modules.admin import service as admin_service
from app.modules.admin.schemas import AuditLogPublic
from app.modules.cs import service as cs_service
from app.modules.dashboard.schemas import DashboardSummary
from app.modules.shop import service as shop_service
from app.modules.users import service as users_service
from app.modules.users.models import User, UserRole, UserStatus

RECENT_LOG_LIMIT = 5


def get_summary(db: Session, user: User) -> DashboardSummary:
    """按角色聚合控制台首页概览。"""
    is_admin = user.role == UserRole.ADMIN
    counts = shop_service.dashboard_counts(db, merchant_id=None if is_admin else user.id)

    summary = DashboardSummary(
        role=user.role,
        my_products=counts["products_total"],
        my_products_on_sale=counts["products_on_sale"],
        my_products_off_shelf=counts["products_off_shelf"],
        my_orders_created=counts["orders_created"],
        my_orders_paid=counts["orders_paid"],
        my_orders_cancelled=counts["orders_cancelled"],
        today_orders=counts["today_orders"],
        today_revenue=float(counts["today_revenue"]),
        low_stock=counts["low_stock"],
        low_stock_threshold=counts["low_stock_threshold"],
        cs_queue=cs_service.queue_count(db),
    )

    if is_admin:
        summary.products_total = counts["products_total"]
        summary.users_total = users_service.count_users(db)
        summary.pending_reviews = users_service.count_users(db, status=UserStatus.PENDING_REVIEW)
        logs, _total = admin_service.list_audit_logs(
            db, PageQuery(page=1, page_size=RECENT_LOG_LIMIT)
        )
        summary.recent_logs = [AuditLogPublic.model_validate(log) for log in logs]

    return summary

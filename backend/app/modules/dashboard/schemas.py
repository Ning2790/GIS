"""dashboard 模块 schema：控制台首页概览。

同一接口按角色返回不同字段（未涉及的字段为 None），前端按角色渲染各自的卡片。
"""

from pydantic import BaseModel

from app.modules.admin.schemas import AuditLogPublic


class DashboardSummary(BaseModel):
    """控制台首页概览（merchant / enterprise 与 admin 两套字段）。"""

    role: str

    # ---- 商品 / 订单（商户看自己；管理员看全平台，字段名统一为 my_*）----
    my_products: int | None = None
    my_products_on_sale: int | None = None
    my_products_off_shelf: int | None = None
    my_orders_created: int | None = None
    my_orders_paid: int | None = None
    my_orders_cancelled: int | None = None
    today_orders: int | None = None
    today_revenue: float | None = None
    low_stock: int | None = None
    low_stock_threshold: int | None = None

    # ---- 管理员专属 ----
    users_total: int | None = None
    pending_reviews: int | None = None
    products_total: int | None = None

    # ---- 公共 ----
    cs_queue: int | None = None
    recent_logs: list[AuditLogPublic] = []

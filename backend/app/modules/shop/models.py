"""shop ORM 模型。

新增或修改表后，需生成 Alembic 迁移：
    uv run alembic revision --autogenerate -m "描述"
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductStatus:
    """商品状态。"""

    ON_SALE = "on_sale"
    OFF_SHELF = "off_shelf"


class OrderStatus:
    """订单状态机：下单 →（支付成功）已支付 →（商户发货）已发货 →（确认收货）已完成；待支付可取消。

    「已签收」不是独立状态，而是 shipped 阶段内的一个时间信号（`delivered_at`）：
    签收后 N 天未确认收货则自动确认（见 service.auto_confirm_received_orders）。
    """

    CREATED = "created"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    # 「已付款」状态集合（已支付 / 已发货 / 已完成）：金额与成交统计口径用——
    # 发货后订单不能从「已支付」「今日成交额」里消失。
    PAID_STATUSES = (PAID, SHIPPED, COMPLETED)


class CancelReason:
    """取消原因：区分买家主动取消与超时未支付自动取消（库存流水 / 审计据此区分）。"""

    BUYER = "buyer"
    EXPIRED = "expired"


class InventoryReason:
    """库存变动原因。"""

    ORDER = "order"
    CANCEL = "cancel"
    RESTOCK = "restock"
    EXPIRE = "expire"  # 超时未支付自动取消的回补（与买家主动取消区分）


class PaymentStatus:
    """支付单状态。"""

    CREATED = "created"
    SUCCESS = "success"
    FAILED = "failed"


class PaymentRefundStatus:
    """退款状态：支付成功但订单已不可支付（取消 / 重复支付）时进入异常退款流程。"""

    NONE = "none"
    PENDING = "pending"
    REFUNDED = "refunded"


class Product(Base):
    """商品。归属商户 / 企业；跨模块只存 users 表的 id，不建外键。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default=ProductStatus.ON_SALE, index=True)
    # 商品主图：平台文件 id（files 模块的公开图片）；图片地址由下面 image_url 推导
    image_file_id: Mapped[int | None] = mapped_column(index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    @property
    def image_url(self) -> str | None:
        """商品图的平台受控读取地址（files 路由；公开文件任何人可读）。"""
        return f"/api/v1/files/{self.image_file_id}" if self.image_file_id else None

    @property
    def image_thumbnail_url(self) -> str | None:
        """商品图缩略图地址（列表页用；服务端无缩略图时自动回退原图）。"""
        return f"/api/v1/files/{self.image_file_id}?variant=thumb" if self.image_file_id else None


class Order(Base):
    """订单。金额 = 订单项之和；明细在 order_items；同一订单只含一个商户的商品。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)  # 买家
    merchant_id: Mapped[int] = mapped_column(index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.CREATED, index=True)
    # 超时取消：下单即写 expire_at（config.order_expire_minutes），到期未支付由定时任务自动取消
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, default=None
    )
    # 取消原因：buyer（买家主动）/ expired（超时未支付），见 CancelReason
    cancel_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    # 收货信息（下单时快照，改个人中心的地址不影响历史订单；历史订单可为空）
    receiver_name: Mapped[str | None] = mapped_column(String(32), default=None)
    receiver_phone: Mapped[str | None] = mapped_column(String(20), default=None)
    receiver_address: Mapped[str | None] = mapped_column(String(255), default=None)
    # 履约（N3）：发货信息与签收 / 完成时间
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    carrier: Mapped[str | None] = mapped_column(String(32), default=None)
    tracking_no: Mapped[str | None] = mapped_column(String(64), default=None)
    # 签收信号：商户 / 管理员标记（当前无物流查询接口；接入后由适配层写入同一字段）
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # 幂等键：同一用户重复提交（网络重试 / 双击）返回首次的订单；并发下由唯一约束兜底
    idem_key: Mapped[str | None] = mapped_column(String(64), default=None)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # 归档 / 超时扫描按时间过滤（数据增长方案 P3 预置索引）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (UniqueConstraint("user_id", "idem_key", name="uq_orders_user_idem_key"),)


class OrderItem(Base):
    """订单项（下单时快照商品名与单价，后续改价不影响历史订单）。"""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(index=True)
    product_id: Mapped[int] = mapped_column(index=True)
    product_name: Mapped[str] = mapped_column(String(128))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CartItem(Base):
    """购物车条目：每人一辆车，直接按 user_id 归属（未单独建 carts 表，按需再拆）。"""

    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    product_id: Mapped[int] = mapped_column(index=True)
    quantity: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_cart_items_user_product"),)


class InventoryMovement(Base):
    """库存流水（每次扣减 / 回补记一条，便于对账）。"""

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(index=True)
    change: Mapped[int]  # 负数=扣减，正数=回补
    reason: Mapped[str] = mapped_column(String(20), default=InventoryReason.ORDER)
    ref_id: Mapped[int | None] = mapped_column(default=None)  # 关联订单 id（可空）
    # 保留期清理按 created_at 删（数据增长方案）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class Payment(Base):
    """支付单：平台不做资金池，支付走第三方；本表只记录状态与第三方单号。"""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    channel: Mapped[str] = mapped_column(String(20), default="third_party")
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.CREATED, index=True)
    trade_no: Mapped[str | None] = mapped_column(String(64), default=None)  # 第三方支付单号
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # 异常退款：支付成功但订单已取消 / 重复支付时置 pending，管理员线下退款后置 refunded
    refund_status: Mapped[str] = mapped_column(
        String(16), default=PaymentRefundStatus.NONE, server_default=PaymentRefundStatus.NONE
    )
    refund_note: Mapped[str | None] = mapped_column(String(255), default=None)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        # 同一订单同时只允许一张待支付支付单：并发点“支付”由数据库决出唯一赢家
        Index(
            "uq_payments_open_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'created'"),
            sqlite_where=text("status = 'created'"),
        ),
    )


class AfterSaleStatus:
    """售后单状态机（N4）：待处理 →（商户受理）处理中 →（商户完成）已解决。

    - 商户可在**结单前**拒绝（待处理或处理中 → 已拒绝，需给出理由）；
    - 买家可在受理前撤销（→ 已撤销）；
    - 已解决 / 已拒绝 / 已撤销为终态，结单后可再次发起（同一订单同时只允许一条未结单）。
    """

    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

    # 未结单（同一订单只允许存在一条）
    OPEN_STATUSES = (PENDING, PROCESSING)
    # 终态
    CLOSED_STATUSES = (RESOLVED, REJECTED, WITHDRAWN)


class AfterSaleReason:
    """售后原因（预设类别，前端做中文映射；自由文本放 description）。"""

    QUALITY = "quality"  # 质量问题
    MISSING = "missing"  # 少发 / 漏发
    MISMATCH = "mismatch"  # 与描述不符
    DAMAGED = "damaged"  # 包装 / 商品破损
    OTHER = "other"  # 其他


class AfterSale(Base):
    """售后单（需求 2.3 售后 / 4.4 客服并行入口）。

    平台不做资金池：售后单只跟踪原因、状态与双方留言，退款 / 换货由商户线下或经第三方处理。
    同一订单同时只允许一条未结单（OPEN_STATUSES），结单后可再发起。
    """

    __tablename__ = "after_sales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)  # 买家
    merchant_id: Mapped[int] = mapped_column(index=True)  # 订单归属商户（商户侧查询用）
    reason: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(300), default=None)
    status: Mapped[str] = mapped_column(String(16), default=AfterSaleStatus.PENDING, index=True)
    handler_id: Mapped[int | None] = mapped_column(default=None)  # 受理 / 处理人（商户或管理员）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # 「同一订单同时只允许一条未结单」由数据库兜底（PG / SQLite 都支持部分唯一索引）：
    # 服务层的「先查后插」在并发下是 TOCTOU，两个请求会各插一条。
    __table_args__ = (
        Index(
            "uq_after_sales_open_order",
            "order_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing')"),
            sqlite_where=text("status IN ('pending', 'processing')"),
        ),
    )


class AfterSaleMessage(Base):
    """售后留言（买卖双方 + 管理员可见；结单后不再允许新增）。"""

    __tablename__ = "after_sale_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    after_sale_id: Mapped[int] = mapped_column(index=True)
    author_id: Mapped[int] = mapped_column()
    author_role: Mapped[str] = mapped_column(String(16))  # buyer / merchant / admin
    content: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Favorite(Base):
    """商品收藏（增强项）：唯一约束保证「每人每商品一条」，重复收藏幂等。

    收藏数是「被关注度」信号，也参与首页推荐的兴趣打分（见 service.recommend_products）。
    """

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    product_id: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),)


class ProductView(Base):
    """商品浏览记录（增强项）：每人每商品一条，重复浏览更新时间并累加次数。

    登录用户看商品详情时写入（匿名不记）；「浏览历史」按 viewed_at 倒序展示，
    view_count 参与全站热度（首页推荐的游客兜底）。
    """

    __tablename__ = "product_views"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    product_id: Mapped[int] = mapped_column(index=True)
    view_count: Mapped[int] = mapped_column(default=1)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_product_views_user_product"),
    )

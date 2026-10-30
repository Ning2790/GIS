"""shop 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
本层只 flush 不 commit：交易路径要求原子性，事务边界由 service 统一控制。
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, and_, delete, func, insert, literal, or_, select, update
from sqlalchemy.orm import Session

from app.modules.shop.models import (
    AfterSale,
    AfterSaleMessage,
    AfterSaleStatus,
    CancelReason,
    CartItem,
    Favorite,
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    ProductStatus,
    ProductView,
)


def _like_pattern(keyword: str) -> str:
    """转义 LIKE 通配符（% _ \\），避免用户输入被当通配符扫描全表。"""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def product_list_query(
    *,
    keyword: str | None = None,
    merchant_id: int | None = None,
    sort: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
) -> Select[tuple[Product]]:
    """商品列表：只露在售商品；keyword 模糊匹配名称；支持排序与价格区间。

    过滤与排序都**下推到 SQL**（不是在应用层筛），这样分页 total 与筛选条件一致。
    排序为 None / 未知值 → 默认「最新」（id 倒序，与历史行为一致）。
    """
    stmt = select(Product).where(Product.status == ProductStatus.ON_SALE)
    if merchant_id is not None:
        stmt = stmt.where(Product.merchant_id == merchant_id)
    if keyword:
        stmt = stmt.where(Product.name.like(_like_pattern(keyword), escape="\\"))
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)

    order_by = {
        "price_asc": (Product.price.asc(), Product.id.desc()),
        "price_desc": (Product.price.desc(), Product.id.desc()),
        "newest": (Product.id.desc(),),
    }.get(sort or "newest", (Product.id.desc(),))
    return stmt.order_by(*order_by)


def merchant_product_list_query(
    *, merchant_id: int | None, status: str | None = None
) -> Select[tuple[Product]]:
    """商户自己的商品（含已下架），用于管理端列表；merchant_id 为空时返回全部（管理员）。

    status 可选：按「在售 / 已下架」筛选。
    """
    stmt = select(Product)
    if merchant_id is not None:
        stmt = stmt.where(Product.merchant_id == merchant_id)
    if status is not None:
        stmt = stmt.where(Product.status == status)
    return stmt.order_by(Product.id.desc())


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def get_products_by_ids(db: Session, product_ids: list[int]) -> dict[int, Product]:
    if not product_ids:
        return {}
    rows = db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    return {row.id: row for row in rows}


def create_product(db: Session, product: Product) -> Product:
    db.add(product)
    db.flush()
    db.refresh(product)
    return product


def decrease_stock(db: Session, product_id: int, quantity: int) -> bool:
    """条件扣减库存（原子 UPDATE，避免先读后写）：库存不足或已下架返回 False。

    不提交——由调用方与服务层的其他写入放进同一个事务（见 service.create_order）。
    """
    result = db.execute(
        update(Product)
        .where(
            Product.id == product_id,
            Product.status == ProductStatus.ON_SALE,
            Product.stock >= quantity,
        )
        .values(stock=Product.stock - quantity)
    )
    return result.rowcount == 1


def create_order(db: Session, order: Order) -> Order:
    db.add(order)
    db.flush()
    db.refresh(order)
    return order


def cancel_order_if_created(db: Session, order_id: int, user_id: int) -> bool:
    """原子取消：仅当订单仍为待支付且属于该用户时置为已取消，返回是否成功。

    并发重复取消只有一个能拿到 True，避免库存被回补两次。
    """
    result = db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.user_id == user_id,
            Order.status == OrderStatus.CREATED,
        )
        .values(status=OrderStatus.CANCELLED, cancel_reason=CancelReason.BUYER)
    )
    db.flush()
    return result.rowcount == 1


def list_expired_order_ids(db: Session, *, now: datetime, limit: int = 200) -> list[int]:
    """超时未支付的订单 id（待支付且 expire_at 已过），按到期先后取一批。"""
    return list(
        db.scalars(
            select(Order.id)
            .where(
                Order.status == OrderStatus.CREATED,
                Order.expire_at.is_not(None),
                Order.expire_at <= now,
            )
            .order_by(Order.expire_at.asc())
            .limit(limit)
        ).all()
    )


def cancel_if_expired(db: Session, order_id: int, now: datetime) -> bool:
    """原子超时取消：仅当订单仍为待支付且确实已超时时置为已取消，返回是否成功。

    与买家手动取消（cancel_order_if_created）条件更新竞争时只有一个能生效，
    库存不会被回补两次。
    """
    result = db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == OrderStatus.CREATED,
            Order.expire_at.is_not(None),
            Order.expire_at <= now,
        )
        .values(status=OrderStatus.CANCELLED, cancel_reason=CancelReason.EXPIRED)
    )
    db.flush()
    return result.rowcount == 1


def fail_pending_payments(db: Session, order_id: int) -> int:
    """把该订单尚未处理的支付单置为失败（订单超时取消时调用），返回条数。"""
    result = db.execute(
        update(Payment)
        .where(Payment.order_id == order_id, Payment.status == PaymentStatus.CREATED)
        .values(status=PaymentStatus.FAILED)
    )
    db.flush()
    return result.rowcount or 0


def claim_payment_success(
    db: Session,
    payment_id: int,
    *,
    trade_no: str | None,
    paid_at: datetime,
    allow_failed: bool = False,
) -> bool:
    """原子抢占支付成功：仅当支付单仍为 created（或允许时 failed）时置为成功。

    支付回调天然会重试（网关重投 / 管理员双击），并发下必须由数据库条件更新
    决出唯一赢家——否则两个请求都会写「订单已支付」通知。
    `allow_failed` 用于**订单已取消**后的迟到支付：旧逻辑可能已把支付单置 failed，
    但网关侧钱已收到，仍要落 success 并进入退款流程。
    """
    statuses = (
        (PaymentStatus.CREATED, PaymentStatus.FAILED) if allow_failed else (PaymentStatus.CREATED,)
    )
    result = db.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status.in_(statuses))
        .values(status=PaymentStatus.SUCCESS, trade_no=trade_no, paid_at=paid_at)
    )
    db.flush()
    return result.rowcount == 1


def claim_payment_failed(db: Session, payment_id: int, *, trade_no: str | None) -> bool:
    """原子抢占支付失败（同上，仅 created → failed 生效一次）。"""
    result = db.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status == PaymentStatus.CREATED)
        .values(status=PaymentStatus.FAILED, trade_no=trade_no)
    )
    db.flush()
    return result.rowcount == 1


def mark_order_paid_if_created(db: Session, order_id: int, *, paid_at: datetime) -> bool:
    """原子把订单从待支付翻为已支付，返回是否由本次请求完成翻转。"""
    result = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == OrderStatus.CREATED)
        .values(status=OrderStatus.PAID, paid_at=paid_at)
    )
    db.flush()
    return result.rowcount == 1


# ---------- 履约：发货 / 签收 / 确认收货（N3） ----------


def ship_if_paid(
    db: Session,
    order_id: int,
    merchant_id: int,
    *,
    carrier: str,
    tracking_no: str,
    now: datetime,
) -> bool:
    """原子发货：仅当订单属于该商户且仍为已支付时置为已发货，返回是否成功。"""
    result = db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.merchant_id == merchant_id,
            Order.status == OrderStatus.PAID,
        )
        .values(
            status=OrderStatus.SHIPPED,
            shipped_at=now,
            carrier=carrier,
            tracking_no=tracking_no,
        )
    )
    db.flush()
    return result.rowcount == 1


def mark_delivered_if_shipped(db: Session, order_id: int, now: datetime) -> bool:
    """原子标记签收：仅当订单仍为已发货且尚未标记签收时写入签收时间，返回是否成功。"""
    result = db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == OrderStatus.SHIPPED,
            Order.delivered_at.is_(None),
        )
        .values(delivered_at=now)
    )
    db.flush()
    return result.rowcount == 1


def complete_if_shipped(db: Session, order_id: int, user_id: int, now: datetime) -> bool:
    """原子确认收货（买家本人）：已发货 → 已完成，返回是否成功。"""
    result = db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.user_id == user_id,
            Order.status == OrderStatus.SHIPPED,
        )
        .values(status=OrderStatus.COMPLETED, completed_at=now)
    )
    db.flush()
    return result.rowcount == 1


def _auto_confirm_condition(delivered_cutoff: datetime, shipped_cutoff: datetime):
    """自动确认收货条件：签收后已超期；或一直未标记签收、发货后已超兜底期。"""
    return or_(
        and_(Order.delivered_at.is_not(None), Order.delivered_at <= delivered_cutoff),
        and_(
            Order.delivered_at.is_(None),
            Order.shipped_at.is_not(None),
            Order.shipped_at <= shipped_cutoff,
        ),
    )


def list_auto_confirm_candidates(
    db: Session, *, delivered_cutoff: datetime, shipped_cutoff: datetime, limit: int = 200
) -> list[int]:
    """待自动确认收货的订单 id（已发货且满足签收超期 / 发货兜底条件）。"""
    return list(
        db.scalars(
            select(Order.id)
            .where(
                Order.status == OrderStatus.SHIPPED,
                _auto_confirm_condition(delivered_cutoff, shipped_cutoff),
            )
            .order_by(Order.id.asc())
            .limit(limit)
        ).all()
    )


def auto_complete_if_shippable(
    db: Session,
    order_id: int,
    *,
    delivered_cutoff: datetime,
    shipped_cutoff: datetime,
    now: datetime,
) -> bool:
    """原子自动确认收货：条件与候选查询一致，与买家手动确认并发只有一个生效。"""
    result = db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == OrderStatus.SHIPPED,
            _auto_confirm_condition(delivered_cutoff, shipped_cutoff),
        )
        .values(status=OrderStatus.COMPLETED, completed_at=now)
    )
    db.flush()
    return result.rowcount == 1


def increase_stock(db: Session, product_id: int, quantity: int) -> None:
    """原子回补库存（取消订单用）。不提交——由 service 与取消动作放进同一事务。"""
    db.execute(
        update(Product).where(Product.id == product_id).values(stock=Product.stock + quantity)
    )
    db.flush()


def product_status_counts(db: Session, *, merchant_id: int | None = None) -> dict[str, int]:
    """商品按状态计数（控制台首页概览用）。"""
    stmt = select(Product.status, func.count()).group_by(Product.status)
    if merchant_id is not None:
        stmt = stmt.where(Product.merchant_id == merchant_id)
    return {status: count for status, count in db.execute(stmt).all()}


def order_status_counts(db: Session, *, merchant_id: int | None = None) -> dict[str, int]:
    """订单按状态计数（控制台首页概览用）。"""
    stmt = select(Order.status, func.count()).group_by(Order.status)
    if merchant_id is not None:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    return {status: count for status, count in db.execute(stmt).all()}


def low_stock_count(db: Session, *, merchant_id: int | None, threshold: int) -> int:
    """在售且库存不高于阈值的商品数（库存预警）。"""
    stmt = (
        select(func.count())
        .select_from(Product)
        .where(Product.status == ProductStatus.ON_SALE, Product.stock <= threshold)
    )
    if merchant_id is not None:
        stmt = stmt.where(Product.merchant_id == merchant_id)
    return db.scalar(stmt) or 0


def order_today_stats(
    db: Session, *, since: datetime, merchant_id: int | None = None
) -> tuple[int, Decimal]:
    """今日下单数与今日成交额：下单按 created_at，成交按「已付款且 paid_at ≥ since」。

    已付款含 已支付 / 已发货 / 已完成（发货后订单不能从成交额里消失）。
    """
    created_stmt = select(func.count()).select_from(Order).where(Order.created_at >= since)
    revenue_stmt = select(func.coalesce(func.sum(Order.amount), 0)).where(
        Order.status.in_(OrderStatus.PAID_STATUSES), Order.paid_at >= since
    )
    if merchant_id is not None:
        created_stmt = created_stmt.where(Order.merchant_id == merchant_id)
        revenue_stmt = revenue_stmt.where(Order.merchant_id == merchant_id)
    return db.scalar(created_stmt) or 0, db.scalar(revenue_stmt) or Decimal("0")


def get_order(db: Session, order_id: int) -> Order | None:
    return db.get(Order, order_id)


def get_order_for_update(db: Session, order_id: int) -> Order | None:
    """锁定订单行（PG 行锁；SQLite 方言忽略 FOR UPDATE）。

    取消 / 支付回调 / 创建支付单都以订单为锁粒度串行化，避免
    「已取消订单被支付成功」与「同单多张支付单」的竞态。
    """
    return db.scalar(select(Order).where(Order.id == order_id).with_for_update())


def get_order_by_idem_key(db: Session, user_id: int, idem_key: str) -> Order | None:
    return db.scalar(select(Order).where(Order.user_id == user_id, Order.idem_key == idem_key))


def add_order_items(db: Session, items: Sequence[OrderItem]) -> None:
    db.add_all(items)
    db.flush()


def list_order_items(db: Session, order_id: int) -> list[OrderItem]:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id.asc())
    return list(db.scalars(stmt).all())


def order_list_query(
    *,
    user_id: int | None = None,
    merchant_id: int | None = None,
) -> Select[tuple[Order]]:
    stmt = select(Order)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if merchant_id is not None:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    return stmt.order_by(Order.id.desc())


def list_cart_items(db: Session, user_id: int) -> list[CartItem]:
    stmt = select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.id.asc())
    return list(db.scalars(stmt).all())


def get_cart_item(db: Session, user_id: int, item_id: int) -> CartItem | None:
    return db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user_id))


def get_cart_item_by_product(db: Session, user_id: int, product_id: int) -> CartItem | None:
    return db.scalar(
        select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
    )


def add_cart_item(db: Session, item: CartItem) -> CartItem:
    db.add(item)
    db.flush()
    db.refresh(item)
    return item


def increase_cart_quantity(
    db: Session, user_id: int, product_id: int, delta: int, limit: int
) -> bool:
    """原子累加购物车数量（含上限判定）：条目不存在或累加后超限时返回 False。"""
    result = db.execute(
        update(CartItem)
        .where(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id,
            CartItem.quantity + delta <= limit,
        )
        .values(quantity=CartItem.quantity + delta)
    )
    return result.rowcount == 1


def delete_cart_item(db: Session, item: CartItem) -> None:
    db.delete(item)
    db.flush()


def clear_cart(db: Session, user_id: int) -> int:
    """清空购物车，返回删除的行数（0 表示购物车已被其他请求结算）。"""
    result = db.execute(delete(CartItem).where(CartItem.user_id == user_id))
    db.flush()
    return result.rowcount or 0


def add_inventory_movement(db: Session, movement: InventoryMovement) -> None:
    db.add(movement)
    db.flush()


def create_payment(db: Session, payment: Payment) -> Payment:
    db.add(payment)
    db.flush()
    db.refresh(payment)
    return payment


def get_payment(db: Session, payment_id: int) -> Payment | None:
    return db.get(Payment, payment_id)


def get_latest_payment(db: Session, order_id: int) -> Payment | None:
    stmt = select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc())
    return db.scalar(stmt)


def get_open_payment(db: Session, order_id: int) -> Payment | None:
    """该订单当前待支付的支付单（部分唯一索引保证最多一张）。"""
    return db.scalar(
        select(Payment)
        .where(Payment.order_id == order_id, Payment.status == PaymentStatus.CREATED)
        .order_by(Payment.id.desc())
    )


def latest_payments_for_orders(db: Session, order_ids: list[int]) -> dict[int, Payment]:
    """批量取每个订单最新一张支付单（订单列表展示退款状态，避免 N+1）。"""
    if not order_ids:
        return {}
    rows = db.scalars(
        select(Payment)
        .where(Payment.order_id.in_(order_ids))
        .order_by(Payment.order_id.asc(), Payment.id.desc())
    ).all()
    latest: dict[int, Payment] = {}
    for payment in rows:
        latest.setdefault(payment.order_id, payment)
    return latest


# ---------- 售后（N4） ----------


def create_after_sale(db: Session, after_sale: AfterSale) -> AfterSale:
    db.add(after_sale)
    db.flush()
    db.refresh(after_sale)
    return after_sale


def get_after_sale(db: Session, after_sale_id: int) -> AfterSale | None:
    return db.get(AfterSale, after_sale_id)


def open_after_sale_for_order(db: Session, order_id: int) -> AfterSale | None:
    """该订单的未结单售后（待处理 / 处理中）；同一订单同时只允许一条。"""
    return db.scalar(
        select(AfterSale).where(
            AfterSale.order_id == order_id,
            AfterSale.status.in_(AfterSaleStatus.OPEN_STATUSES),
        )
    )


def latest_after_sale_for_order(db: Session, order_id: int) -> AfterSale | None:
    """该订单最近一条售后（任意状态）：订单详情展示售后进度用。"""
    return db.scalar(
        select(AfterSale)
        .where(AfterSale.order_id == order_id)
        .order_by(AfterSale.id.desc())
        .limit(1)
    )


def after_sale_list_query(
    *,
    user_id: int | None = None,
    merchant_id: int | None = None,
    participant_id: int | None = None,
    status: str | None = None,
) -> Select[tuple[AfterSale]]:
    """售后列表查询：按买家 / 商户过滤（管理员都不传 = 全平台），可按状态过滤。

    participant_id = 「我参与的」（既是买家又是商户身份都能看到自己的）。
    """
    stmt = select(AfterSale)
    if user_id is not None:
        stmt = stmt.where(AfterSale.user_id == user_id)
    if merchant_id is not None:
        stmt = stmt.where(AfterSale.merchant_id == merchant_id)
    if participant_id is not None:
        stmt = stmt.where(
            or_(AfterSale.user_id == participant_id, AfterSale.merchant_id == participant_id)
        )
    if status is not None:
        stmt = stmt.where(AfterSale.status == status)
    return stmt.order_by(AfterSale.id.desc())


def transition_after_sale(
    db: Session,
    after_sale_id: int,
    *,
    from_statuses: tuple[str, ...],
    to_status: str,
    now: datetime,
    handler_id: int | None = None,
    close: bool = False,
) -> bool:
    """原子状态流转：仅当当前状态在 from_statuses 内才更新，返回是否成功。

    并发（例如买家撤销与商户受理同时到达）只有一个能生效。
    """
    values: dict = {"status": to_status, "updated_at": now}
    if handler_id is not None:
        values["handler_id"] = handler_id
    if close:
        values["closed_at"] = now
    result = db.execute(
        update(AfterSale)
        .where(AfterSale.id == after_sale_id, AfterSale.status.in_(from_statuses))
        .values(**values)
    )
    db.flush()
    return result.rowcount == 1


def add_after_sale_message(db: Session, message: AfterSaleMessage) -> AfterSaleMessage:
    """无条件插入（内部 / 状态流转同一事务里使用，如拒绝理由、完成说明）。"""
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def add_after_sale_message_if_open(
    db: Session,
    *,
    after_sale_id: int,
    author_id: int,
    author_role: str,
    content: str,
    now: datetime,
) -> AfterSaleMessage | None:
    """条件插入留言：仅当售后单仍**未结单**时写入，返回新留言（否则 None）。

    「先读状态再插入」在并发下会漏（商户结单与买家留言交错），这里用
    INSERT ... SELECT ... WHERE status IN (未结单) 把判断与写入合成一条原子语句。
    """
    stmt = insert(AfterSaleMessage).from_select(
        ["after_sale_id", "author_id", "author_role", "content", "created_at"],
        select(
            literal(after_sale_id),
            literal(author_id),
            literal(author_role),
            literal(content),
            literal(now),
        ).where(
            select(AfterSale.status)
            .where(AfterSale.id == after_sale_id)
            .scalar_subquery()
            .in_(AfterSaleStatus.OPEN_STATUSES)
        ),
    )
    result = db.execute(stmt)
    db.flush()
    if not result.rowcount:
        return None
    return db.scalar(
        select(AfterSaleMessage)
        .where(AfterSaleMessage.after_sale_id == after_sale_id)
        .order_by(AfterSaleMessage.id.desc())
        .limit(1)
    )


def list_after_sale_messages(db: Session, after_sale_id: int) -> list[AfterSaleMessage]:
    return list(
        db.scalars(
            select(AfterSaleMessage)
            .where(AfterSaleMessage.after_sale_id == after_sale_id)
            .order_by(AfterSaleMessage.id.asc())
        ).all()
    )


# ---------- 收藏 / 浏览历史（增强项）----------


def on_sale_products(db: Session, *, limit: int) -> list[Product]:
    """在售商品候选（推荐用）：按 id 倒序取最近上架的一批，控制打分规模。"""
    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ON_SALE)
        .order_by(Product.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_favorite(db: Session, user_id: int, product_id: int) -> Favorite | None:
    return db.scalar(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )


def add_favorite(db: Session, favorite: Favorite) -> Favorite:
    db.add(favorite)
    db.flush()
    db.refresh(favorite)
    return favorite


def delete_favorite(db: Session, favorite: Favorite) -> None:
    db.delete(favorite)
    db.flush()


def favorite_list_query(user_id: int) -> Select:
    """我的收藏（商品列表，最近收藏在前）。下架的仍展示（用户自己的清单，自行取关）。"""
    return (
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.id.desc())
    )


def recent_favorite_product_ids(db: Session, user_id: int, *, limit: int) -> list[int]:
    stmt = (
        select(Favorite.product_id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def upsert_product_view(db: Session, user_id: int, product_id: int, *, now: datetime) -> bool:
    """记录一次浏览：已存在则累加次数并刷新时间（返回 False），否则新建（返回 True）。

    先条件更新再插入（与库存 / 订单同一套「条件写」思路）：并发下两者都可能命中，
    插入撞唯一约束时由 service 兜底重试更新。
    """
    result = db.execute(
        update(ProductView)
        .where(ProductView.user_id == user_id, ProductView.product_id == product_id)
        .values(view_count=ProductView.view_count + 1, viewed_at=now)
    )
    if result.rowcount:
        return False
    db.add(ProductView(user_id=user_id, product_id=product_id, view_count=1, viewed_at=now))
    db.flush()
    return True


def history_list_query(user_id: int) -> Select:
    """浏览历史（商品列表，最近浏览在前；同一商品只出现一次）。"""
    return (
        select(Product)
        .join(ProductView, ProductView.product_id == Product.id)
        .where(ProductView.user_id == user_id)
        .order_by(ProductView.viewed_at.desc(), ProductView.id.desc())
    )


def recent_viewed_product_ids(db: Session, user_id: int, *, limit: int) -> list[int]:
    stmt = (
        select(ProductView.product_id)
        .where(ProductView.user_id == user_id)
        .order_by(ProductView.viewed_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def delete_history(db: Session, user_id: int) -> int:
    result = db.execute(delete(ProductView).where(ProductView.user_id == user_id))
    db.flush()
    return int(result.rowcount or 0)


def favorite_counts(db: Session, product_ids: Sequence[int]) -> dict[int, int]:
    """商品 -> 收藏数（批量，供商户商品列表展示关注度）。"""
    if not product_ids:
        return {}
    stmt = (
        select(Favorite.product_id, func.count())
        .where(Favorite.product_id.in_(product_ids))
        .group_by(Favorite.product_id)
    )
    return {int(pid): int(count) for pid, count in db.execute(stmt).all()}


def popularity_scores(db: Session, product_ids: Sequence[int]) -> dict[int, int]:
    """商品 -> 全站热度（收藏数 × 2 + 浏览去重用户数），供推荐的游客兜底排序。

    收藏天然按人唯一；浏览按**去重用户数**计（不是次数）——单账号反复看不能刷榜。
    """
    if not product_ids:
        return {}
    favorite_rows = db.execute(
        select(Favorite.product_id, func.count())
        .where(Favorite.product_id.in_(product_ids))
        .group_by(Favorite.product_id)
    ).all()
    view_rows = db.execute(
        # 去重用户数而非浏览次数：单账号反复刷详情不能把商品顶到首页推荐位
        select(ProductView.product_id, func.count(func.distinct(ProductView.user_id)))
        .where(ProductView.product_id.in_(product_ids))
        .group_by(ProductView.product_id)
    ).all()
    scores: dict[int, int] = {}
    for product_id, count in favorite_rows:
        scores[int(product_id)] = scores.get(int(product_id), 0) + 2 * int(count)
    for product_id, total in view_rows:
        scores[int(product_id)] = scores.get(int(product_id), 0) + int(total or 0)
    return scores


def export_order_count(
    db: Session,
    *,
    merchant_id: int | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """导出行数（用于判断是否超过单次上限，超过时响应头标记截断）。"""
    stmt = select(func.count()).select_from(Order)
    if merchant_id is not None:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if start is not None:
        stmt = stmt.where(Order.created_at >= start)
    if end is not None:
        stmt = stmt.where(Order.created_at <= end)
    return int(db.scalar(stmt) or 0)


def export_order_batch(
    db: Session,
    *,
    merchant_id: int | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    last_id: int | None = None,
    limit: int = 500,
) -> list[Order]:
    """按 id 倒序取一批导出订单（游标分页，边查边发，避免一次加载 5 万行）。

    倒序保证超过单次上限时优先导出**最新**订单（对账 / 发货场景关心近期）。
    """
    stmt = select(Order)
    if merchant_id is not None:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if start is not None:
        stmt = stmt.where(Order.created_at >= start)
    if end is not None:
        stmt = stmt.where(Order.created_at <= end)
    if last_id is not None:
        stmt = stmt.where(Order.id < last_id)
    return list(db.scalars(stmt.order_by(Order.id.desc()).limit(limit)).all())


def items_by_order_ids(db: Session, order_ids: list[int]) -> dict[int, list[OrderItem]]:
    """批量取订单项（导出避免逐单查询的 N+1）。"""
    if not order_ids:
        return {}
    rows = db.scalars(
        select(OrderItem).where(OrderItem.order_id.in_(order_ids)).order_by(OrderItem.id.asc())
    ).all()
    grouped: dict[int, list[OrderItem]] = {order_id: [] for order_id in order_ids}
    for item in rows:
        grouped.setdefault(item.order_id, []).append(item)
    return grouped


def paid_orders_in_window(
    db: Session, *, merchant_id: int | None, since: datetime
) -> list[tuple[datetime, Decimal]]:
    """窗口内已支付及之后订单的 (成交时间, 金额)，供按业务时区在应用层分日。

    按支付时间统计（与概览页「今日成交额」口径一致）；历史 / 手工数据可能
    `paid_at` 为空，此时回退到创建时间，避免已支付订单从成交口径里消失。
    """
    occurred_at = func.coalesce(Order.paid_at, Order.created_at)
    stmt = select(occurred_at, Order.amount).where(
        occurred_at >= since,
        Order.status.in_(OrderStatus.PAID_STATUSES),
    )
    if merchant_id is not None:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    return [(row[0], Decimal(str(row[1] or 0))) for row in db.execute(stmt).all()]


def top_selling_products(
    db: Session, *, merchant_id: int | None, since: datetime, limit: int = 5
) -> list[tuple[str, int, Decimal]]:
    """窗口内热销商品：(商品名, 销量, 销售额)，按销量降序；按商品 ID 聚合避免同名合并。"""
    stmt = (
        select(
            OrderItem.product_id,
            func.min(OrderItem.product_name),
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.amount), 0),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            func.coalesce(Order.paid_at, Order.created_at) >= since,
            Order.status.in_(OrderStatus.PAID_STATUSES),
        )
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.quantity).desc(), func.min(OrderItem.product_name))
        .limit(limit)
    )
    if merchant_id is not None:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    return [
        (str(row[1]), int(row[2] or 0), Decimal(str(row[3] or 0))) for row in db.execute(stmt).all()
    ]

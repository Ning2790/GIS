"""shop 业务逻辑层。

交易闭环（C2）：购物车 → 结算下单（Redis 预扣闸门 + 数据库条件更新双保险、
幂等键防重复下单）→ 支付单占位（平台不做资金池，接第三方后只改回调校验）。
金额一律用 Decimal 计算（对应 Numeric(10,2)），事务由本层统一提交。
"""

import logging
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from redis import Redis
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import cache, compute, metrics, pagination, retention
from app.core.config import get_settings
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageQuery
from app.modules.admin import service as admin_service
from app.modules.files import service as files_service
from app.modules.notifications import service as notifications_service
from app.modules.notifications.models import NotificationType
from app.modules.shop import payment_gateway, repository
from app.modules.shop.models import (
    AfterSale,
    AfterSaleMessage,
    AfterSaleReason,
    AfterSaleStatus,
    CartItem,
    Favorite,
    InventoryMovement,
    InventoryReason,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentRefundStatus,
    PaymentStatus,
    Product,
    ProductStatus,
    ProductView,
)
from app.modules.users import service as users_service
from app.modules.users.models import User, UserRole

# 单笔订单金额上限，与 orders.amount 的 Numeric(10,2) 保持一致。
MAX_ORDER_AMOUNT = Decimal("99999999.99")
MAX_QUANTITY_PER_ITEM = 999
# 业务时区：日界 / 看板切日 / 筛选入参的 naive 解释都用它（中国商户口径）。
_BUSINESS_TZ = ZoneInfo("Asia/Shanghai")
# 库存闸门键的存活时间：到期后从数据库重新同步，避免 Redis 与数据库长期漂移。
STOCK_KEY_TTL_SECONDS = 3600

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _order_expire_at() -> datetime:
    """订单支付截止时间：下单时刻 + config.order_expire_minutes。

    到期未支付由定时任务自动取消并回补库存（见 expire_unpaid_orders / worker）。
    """
    return _now() + timedelta(minutes=get_settings().order_expire_minutes)


def _get_redis() -> Redis | None:
    """Redis 客户端（懒加载）。未配置 redis_url 或不可用时返回 None（自动降级）。"""
    global _redis_client
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            decode_responses=True,
        )
    return _redis_client


def _redis_reserve(product_id: int, quantity: int, db_stock: int) -> bool | None:
    """Redis 预扣（高并发快速失败闸门）。

    True=预扣成功；False=库存不足（立即拒绝）；None=未启用 / 不可用（降级走数据库）。
    数据库的条件更新仍是权威判定，这里只是减少无效的数据库竞争。
    """
    client = _get_redis()
    if client is None:
        return None
    key = f"shop:stock:{product_id}"
    try:
        if not client.exists(key):
            client.set(key, db_stock, nx=True)  # 首次使用从数据库同步（防并发覆盖）
            client.expire(key, STOCK_KEY_TTL_SECONDS)
        remaining = client.decrby(key, quantity)
        if remaining < 0:
            client.incrby(key, quantity)  # 回补
            return False
        return True
    except Exception:  # Redis 故障不影响主流程
        return None


def _redis_sync(product_id: int, db_stock: int) -> None:
    """把闸门重置为数据库权威值；带 TTL，保证到期后仍会强制从数据库重新同步。

    写入前若与 Redis 现值不一致，计一次「闸门回补」指标（N10 可观测性）。
    """
    client = _get_redis()
    if client is None:
        return
    try:
        key = f"shop:stock:{product_id}"
        current = client.get(key)
        try:
            drifted = current is not None and int(current) != db_stock
        except (TypeError, ValueError):
            drifted = True  # 值损坏同样算漂移，随后照常覆盖回数据库权威值
        if drifted:
            metrics.record_stock_gate_drift()
        # 无论解析成功与否都要写回权威值（解析失败不能连带跳过校准）
        client.set(key, db_stock, ex=STOCK_KEY_TTL_SECONDS)
    except Exception:  # 闸门写回失败不影响主流程（下次仍会重试同步）
        pass


def amount_of(unit_price: Decimal, quantity: int) -> Decimal:
    """金额 = 单价 × 数量，四舍五入到分（与 Numeric(10,2) 对齐）。"""
    return (Decimal(unit_price) * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _reserve_and_decrease(
    db: Session, product: Product, quantity: int, reserved: list[tuple[int, int]]
) -> None:
    """双保险扣减：Redis 预扣（可降级）+ 数据库条件更新（权威）。

    预扣成功时登记到 reserved，调用方在校验失败时统一回补。
    """
    gate = _redis_reserve(product.id, quantity, product.stock)
    if gate is False:
        raise ConflictError(f"「{product.name}」库存不足")
    if gate is True:
        reserved.append((product.id, quantity))
    if not repository.decrease_stock(db, product.id, quantity):
        raise ConflictError(f"「{product.name}」库存不足")


def _compensate_all(db: Session, reserved: list[tuple[int, int]]) -> None:
    """回补预扣：按数据库权威值对齐闸门（而非简单加回数量）。

    并发下"加回数量"会与成功请求的同步 SET 相互交错、造成可正可负的漂移；
    对齐到数据库值后，每个请求退出（成交或失败）都会把闸门校准一次，
    系统在无进行中请求时必然一致。调用前须先 db.rollback()，
    保证读到的库存不含本请求未提交的扣减。
    """
    for product_id, _quantity in reserved:
        product = repository.get_product(db, product_id)
        if product is not None:
            _redis_sync(product_id, product.stock)


def _sync_all(db: Session, products: dict[int, Product]) -> None:
    """把闸门校准到数据库权威值（**提交后**的尽力而为动作）。

    本函数在 db.commit() 之后调用，此时订单与库存变更**已经落库**。若这里因连接池
    等连接超时（过载）而抛出，请求会以失败返回，而客户端按 Retry-After 重试（下单的
    idem_key 又是可选字段）会造成重复下单——故此处只记日志、不上抛；闸门漂移由下一次
    请求的补偿逻辑自愈（见 _compensate_all 的一致性说明）。
    """
    for product in products.values():
        try:
            db.refresh(product)
            _redis_sync(product.id, product.stock)
        except SQLAlchemyError as exc:
            logger.warning("提交后闸门对账失败（订单已成交，不影响结果）：%s", exc)
            db.rollback()  # 清掉失败的只读事务，避免污染会话状态
            return


def _find_by_idem_key(db: Session, user: User, idem_key: str | None) -> Order | None:
    if not idem_key:
        return None
    return repository.get_order_by_idem_key(db, user.id, idem_key)


def _replay_order(
    db: Session, user: User, idem_key: str | None, *, product_id: int, quantity: int
) -> Order | None:
    """按幂等键重放（直购）：命中但请求参数与已创建订单不一致时按冲突处理。

    避免幂等键被复用到其他商品 / 数量时静默返回首单（用户以为下的是新单）。
    """
    order = _find_by_idem_key(db, user, idem_key)
    if order is None:
        return None
    items = repository.list_order_items(db, order.id)
    if len(items) != 1 or items[0].product_id != product_id or items[0].quantity != quantity:
        raise ConflictError("该幂等键已用于其他订单，请更换后重试")
    return order


def create_product(
    db: Session,
    merchant: User,
    *,
    name: str,
    price: float,
    stock: int,
    description: str = "",
    image_file_id: int | None = None,
) -> Product:
    """商户 / 企业上架商品（归属自己）。

    image_file_id 为平台文件 id：必须是本人上传的文件（跨模块走 files service 校验），
    否则按「文件不存在」处理。
    """
    if image_file_id is not None:
        files_service.require_owned(db, image_file_id, merchant)
    product = Product(
        merchant_id=merchant.id,
        name=name,
        description=description,
        price=Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        stock=stock,
        status=ProductStatus.ON_SALE,
        image_file_id=image_file_id,
    )
    repository.create_product(db, product)
    db.commit()
    cache.bump_version("shop:products")  # 新商品立即出现在列表（不吃陈旧缓存）
    return product


def list_products(
    db: Session,
    page: PageQuery,
    *,
    keyword: str | None = None,
    merchant_id: int | None = None,
    sort: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
) -> tuple[list[Product], int]:
    """商品列表（分页，只含在售；支持排序与价格区间，过滤/排序均下推 SQL）。"""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise BadRequestError("价格区间不正确：最低价不能高于最高价")
    stmt = repository.product_list_query(
        keyword=keyword,
        merchant_id=merchant_id,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
    )
    return pagination.paginate(db, stmt, page)


LOW_STOCK_THRESHOLD = 10  # 库存预警线（控制台首页）


def dashboard_counts(db: Session, *, merchant_id: int | None) -> dict[str, object]:
    """控制台首页用统计：商品 / 订单按状态、低库存、今日下单与成交额。

    merchant_id=None 表示全平台（管理员视角），否则只看该商户。
    """
    # 业务日界按 Asia/Shanghai（与销量看板一致）：中国时间 00:00–08:00 不能算到前一天
    today_start = datetime.combine(
        datetime.now(_BUSINESS_TZ).date(), time.min, tzinfo=_BUSINESS_TZ
    ).astimezone(UTC)
    product_counts = repository.product_status_counts(db, merchant_id=merchant_id)
    order_counts = repository.order_status_counts(db, merchant_id=merchant_id)
    today_orders, today_revenue = repository.order_today_stats(
        db, since=today_start, merchant_id=merchant_id
    )
    return {
        "products_total": sum(product_counts.values()),
        "products_on_sale": product_counts.get(ProductStatus.ON_SALE, 0),
        "products_off_shelf": product_counts.get(ProductStatus.OFF_SHELF, 0),
        "orders_created": order_counts.get(OrderStatus.CREATED, 0),
        # 已支付 = 已付款（含已发货 / 已完成）
        "orders_paid": sum(order_counts.get(status, 0) for status in OrderStatus.PAID_STATUSES),
        "orders_cancelled": order_counts.get(OrderStatus.CANCELLED, 0),
        "orders_total": sum(order_counts.values()),
        "low_stock": repository.low_stock_count(
            db, merchant_id=merchant_id, threshold=LOW_STOCK_THRESHOLD
        ),
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "today_orders": today_orders,
        "today_revenue": today_revenue,
    }


def list_my_products(
    db: Session, merchant: User, page: PageQuery, *, status: str | None = None
) -> tuple[list[Product], int]:
    """商品列表（含已下架）：商户看自己；管理员看全平台；可按状态筛选。"""
    if status is not None and status not in (ProductStatus.ON_SALE, ProductStatus.OFF_SHELF):
        raise BadRequestError("状态只能是 on_sale 或 off_shelf")
    merchant_id = None if merchant.role == UserRole.ADMIN else merchant.id
    stmt = repository.merchant_product_list_query(merchant_id=merchant_id, status=status)
    return pagination.paginate(db, stmt, page)


def set_product_status(db: Session, merchant: User, product_id: int, status: str) -> Product:
    """上架 / 下架商品（仅归属商户本人，管理员可操作任意商品）。

    下架后公开列表不再展示（同时在售过滤），购物车结算也会被「已下架」校验拦下。
    """
    if status not in (ProductStatus.ON_SALE, ProductStatus.OFF_SHELF):
        raise BadRequestError("状态只能是 on_sale / off_shelf")
    product = repository.get_product(db, product_id)
    if product is None:
        raise NotFoundError("商品不存在")
    if product.merchant_id != merchant.id and merchant.role != UserRole.ADMIN:
        raise ForbiddenError("只能操作自己上架的商品")
    product.status = status
    db.commit()
    db.refresh(product)
    cache.bump_version("shop:products")  # 状态变化后公开列表缓存立即失效
    return product


def get_product_detail(db: Session, product_id: int) -> Product:
    product = repository.get_product(db, product_id)
    if product is None or product.status != ProductStatus.ON_SALE:
        raise NotFoundError("商品不存在或已下架")
    return product


# ---------- 收藏 / 浏览历史 / 首页推荐（增强项）----------

# 推荐候选与兴趣来源的上限：控制打分规模（打分是内存计算，规模必须可预期）。
RECOMMEND_CANDIDATES = 300
RECOMMEND_INTEREST_FAVORITES = 6
RECOMMEND_INTEREST_VIEWS = 12


def add_favorite(db: Session, user: User, product_id: int) -> int:
    """收藏商品（幂等），返回该商品最新的全站收藏数。

    幂等的两层兜底：先查（常见路径），并发下唯一约束再兜一次——撞约束只回滚
    **这一条插入**（SAVEPOINT），不影响同一请求里其它待提交的写。
    """
    product = repository.get_product(db, product_id)
    if product is None or product.status != ProductStatus.ON_SALE:
        raise NotFoundError("商品不存在或已下架")
    if repository.get_favorite(db, user.id, product_id) is None:
        try:
            with db.begin_nested():  # 只回滚这一句，不牵连整个请求的事务
                repository.add_favorite(db, Favorite(user_id=user.id, product_id=product_id))
        except IntegrityError:  # 并发重复收藏：唯一约束兜底，按已收藏处理
            pass
    db.commit()
    return repository.favorite_counts(db, [product_id]).get(product_id, 0)


def remove_favorite(db: Session, user: User, product_id: int) -> int:
    """取消收藏（幂等：没收藏过也算成功），返回该商品最新的全站收藏数。"""
    favorite = repository.get_favorite(db, user.id, product_id)
    if favorite is not None:
        repository.delete_favorite(db, favorite)
        db.commit()
    return repository.favorite_counts(db, [product_id]).get(product_id, 0)


def list_favorites(db: Session, user: User, page: PageQuery) -> tuple[list[Product], int]:
    """我的收藏（最近收藏在前；已下架的商品仍展示，用户可自行取关）。"""
    return pagination.paginate(db, repository.favorite_list_query(user.id), page)


def favorite_state(db: Session, user: User | None, product_id: int) -> tuple[bool, int]:
    """商品详情的收藏态：(我是否收藏, 全站收藏数)。未登录时第一项恒为 False。"""
    is_favorited = (
        repository.get_favorite(db, user.id, product_id) is not None if user is not None else False
    )
    counts = repository.favorite_counts(db, [product_id])
    return is_favorited, counts.get(product_id, 0)


def record_view(db: Session, user: User, product_id: int) -> None:
    """记录一次浏览（失败不影响详情：浏览历史是附加功能，不能拖垮主链路）。"""
    user_id = user.id  # 先取值：失败回滚会让 ORM 实例过期，日志里再读会多打一次库
    try:
        repository.upsert_product_view(db, user.id, product_id, now=_now())
        db.commit()
    except IntegrityError:  # 并发首访：另一请求已插入，退化为累加
        db.rollback()
        try:
            repository.upsert_product_view(db, user.id, product_id, now=_now())
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.warning(
                "浏览记录写入失败（忽略）：user_id=%s product_id=%s", user.id, product_id
            )
    except SQLAlchemyError:
        db.rollback()
        logger.warning("浏览记录写入失败（忽略）：user_id=%s product_id=%s", user_id, product_id)


def list_history(db: Session, user: User, page: PageQuery) -> tuple[list[Product], int]:
    """浏览历史（最近浏览在前，同一商品只出现一次）。"""
    return pagination.paginate(db, repository.history_list_query(user.id), page)


def clear_history(db: Session, user: User) -> int:
    """清空浏览历史，返回删除条数。"""
    deleted = repository.delete_history(db, user.id)
    db.commit()
    return deleted


# 商品命名里常见、但与品类无关的通用后缀 / 卖点词：提取核心前先剥离。
# 不剥离的后果（复审实测）：看过「青海黑枸杞礼盒」后，关键词里的「礼盒」会让
# **所有礼盒类商品**都命中高相关分（Top8 同品类 0/8），个人推荐直接跑偏。
_GENERIC_SUFFIXES = (
    "高原特产",
    "大容量",
    "组合装",
    "旗舰店",
    "礼盒装",
    "礼盒",
    "礼包",
    "套装",
    "罐装",
    "袋装",
    "瓶装",
    "盒装",
    "散装",
    "整箱",
    "特级",
    "一级",
    "精选",
    "正宗",
    "包邮",
    "特产",
)


def _strip_generic_suffixes(core: str) -> str:
    """反复剥离尾部通用后缀（「…礼盒特级」→「…」），至少保留 1 个字。"""
    changed = True
    while changed and len(core) > 1:
        changed = False
        for suffix in _GENERIC_SUFFIXES:
            if len(core) > len(suffix) and core.endswith(suffix):
                core = core[: -len(suffix)]
                changed = True
                break
    return core


def _interest_keywords(names: list[str]) -> list[str]:
    """把「看过的商品名」提炼成兴趣关键词（去重保序）。

    规则：去掉括号规格（如「（250g×2）」）与尾部通用词（礼盒 / 特产 / 特级…），
    再补 2–4 字的尾部片段——中文品名核心在尾部（「柴达木黑枸杞」→「黑枸杞」、
    「青海雪菊」→「雪菊」），多给几个长度是为了让「产地前缀长 / 短」的品名都能命中；
    打分取关键词间的最大值，多给不冲突（见 recommend_products）。
    """
    keywords: list[str] = []
    for name in names:
        core = _strip_generic_suffixes(name.split("（")[0].split("(")[0].strip())
        if not core:
            continue
        for candidate in (core, core[-4:], core[-3:], core[-2:]):
            if len(candidate) >= 2 and candidate not in keywords:
                keywords.append(candidate)
    return keywords


def recommend_products(
    db: Session, user: User | None, *, limit: int = 8
) -> tuple[list[Product], str]:
    """首页「为你推荐」：返回 (商品, 依据)。依据 = personal（按兴趣打分）/ popular（全站热度）。

    打分（0-100 归一到同量纲后加权）：
    - 名称相关性 0.6：偏好关键词（来自本人最近收藏 / 浏览过的商品名）逐个与候选商品名
      做相关性打分，计算下沉到 C++ 计算核心（app/core/compute.py 的 planning_score，
      未编译时自动回退等价 Python 实现），取关键词间的最大值；
    - 价格接近度 0.4：与本人兴趣商品均价的距离（1 - 价差 / 均价，负值截断为 0）。
    游客 / 新用户（没有收藏与浏览）走**全站热度**兜底：收藏数 × 2 + 浏览去重用户数，
    同分按 id 升序。刚看过 / 收藏过的商品会因名称与价格同时高度贴合而排在最前（复购导向，
    鲜食特产属有意行为）。
    """
    candidates = repository.on_sale_products(db, limit=RECOMMEND_CANDIDATES)
    if not candidates:
        return [], "popular"

    interest_ids: list[int] = []
    if user is not None:
        # 收藏在前（更强的兴趣信号）、浏览在后；同一件商品只算一次，避免均价被重复计权
        interest_ids = list(
            dict.fromkeys(
                repository.recent_favorite_product_ids(
                    db, user.id, limit=RECOMMEND_INTEREST_FAVORITES
                )
                + repository.recent_viewed_product_ids(db, user.id, limit=RECOMMEND_INTEREST_VIEWS)
            )
        )
    interest_products = repository.get_products_by_ids(db, interest_ids)
    interest_names = [
        interest_products[pid].name for pid in interest_ids if pid in interest_products
    ]

    if not interest_names:
        # 游客 / 无行为：全站热度（收藏 × 2 + 浏览去重用户数）
        popularity = repository.popularity_scores(db, [product.id for product in candidates])
        ranked = sorted(candidates, key=lambda p: (-popularity.get(p.id, 0), p.id))
        return ranked[:limit], "popular"

    keywords = _interest_keywords(interest_names)
    average_price = sum(
        (interest_products[pid].price for pid in interest_ids if pid in interest_products),
        Decimal("0"),
    ) / Decimal(len(interest_names))

    scored: list[tuple[float, int, Product]] = []
    for product in candidates:
        relevance = 0.0
        if keywords:
            relevance = max(
                compute.planning_score(product.name, "", keyword) for keyword in keywords
            )
        if average_price > 0:
            gap = abs(Decimal(product.price) - average_price) / average_price
            price_score = float(max(Decimal("0"), Decimal("1") - gap)) * 100.0
        else:
            price_score = 0.0
        scored.append((0.6 * relevance + 0.4 * price_score, product.id, product))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [product for _score, _pid, product in scored[:limit]], "personal"


def update_product(
    db: Session,
    merchant: User,
    product_id: int,
    *,
    changes: dict[str, object],
) -> Product:
    """编辑商品（仅归属商户本人）：部分更新，只应用 changes 里给出的字段。

    `image_file_id=None` 表示移除主图；给出新的文件 id 时必须是本人上传的文件。
    状态（上 / 下架）不在这里改，走 set_product_status。
    """
    product = repository.get_product(db, product_id)
    if product is None:
        raise NotFoundError("商品不存在")
    if product.merchant_id != merchant.id:
        raise ForbiddenError("只能编辑自己的商品")

    if "image_file_id" in changes and changes["image_file_id"] is not None:
        files_service.require_owned(db, int(changes["image_file_id"]), merchant)
    for field in ("name", "description", "price", "stock", "image_file_id"):
        if field not in changes:
            continue
        value = changes[field]
        if field == "price" and value is not None:
            value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    cache.bump_version("shop:products")  # 改价 / 改图后公开列表缓存立即失效
    return product


def create_order(
    db: Session,
    user: User,
    *,
    product_id: int,
    quantity: int,
    idem_key: str | None = None,
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
) -> Order:
    """直接购买（单商品下单）。

    幂等：同 idem_key 重复提交（且参数一致）返回首次订单（并发由唯一约束兜底）；
    扣减与落单同一事务；库存不足抛 409。
    收货信息随订单**快照**落库（改个人中心地址不影响历史订单）。
    """
    existing = _replay_order(db, user, idem_key, product_id=product_id, quantity=quantity)
    if existing is not None:
        return existing

    product = repository.get_product(db, product_id)
    if product is None or product.status != ProductStatus.ON_SALE:
        raise NotFoundError("商品不存在或已下架")
    amount = amount_of(product.price, quantity)
    if amount > MAX_ORDER_AMOUNT:
        raise BadRequestError("订单金额超出上限，请减少购买数量")

    reserved: list[tuple[int, int]] = []
    try:
        _reserve_and_decrease(db, product, quantity, reserved)
    except Exception:
        db.rollback()  # 先撤销本请求扣减，再按权威值回补闸门
        _compensate_all(db, reserved)
        raise

    order = Order(
        user_id=user.id,
        merchant_id=product.merchant_id,
        amount=amount,
        status=OrderStatus.CREATED,
        idem_key=idem_key,
        expire_at=_order_expire_at(),
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        receiver_address=receiver_address,
    )
    try:
        # try 必须从 create_order 开始：它在内部 flush 时就执行 INSERT，
        # 并发同 idem_key 的唯一约束冲突在这一步抛出（早于 commit），
        # 只包住 commit 会让冲突绕过下面的重放逻辑直接冒泡成 500。
        repository.create_order(db, order)
        repository.add_order_items(
            db,
            [
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    unit_price=product.price,
                    quantity=quantity,
                    amount=amount,
                )
            ],
        )
        repository.add_inventory_movement(
            db,
            InventoryMovement(
                product_id=product.id,
                change=-quantity,
                reason=InventoryReason.ORDER,
                ref_id=order.id,
            ),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        _compensate_all(db, reserved)  # 本次请求无成交，闸门按权威值回补
        existing = _replay_order(db, user, idem_key, product_id=product_id, quantity=quantity)
        if existing is not None:
            return existing  # 并发重放：返回先到者已创建的订单
        raise
    # 注意：id 必须在 commit 之前取出——提交后对象已过期，`{product.id: ...}` 会在
    # `_sync_all` 的 try **之外**触发一次 SELECT，失败会让「已成交」的请求返回错误，
    # 从而诱导客户端重试（幂等键可选，可能重复下单）。
    _sync_all(db, {product_id: product})
    return order


def get_cart_detail(db: Session, user: User) -> tuple[list[CartItem], dict[int, Product], Decimal]:
    """购物车详情：返回 (条目, 商品映射, 总金额)。"""
    items = repository.list_cart_items(db, user.id)
    products = repository.get_products_by_ids(db, [item.product_id for item in items])
    total = Decimal("0.00")
    for item in items:
        product = products.get(item.product_id)
        if product is not None:
            total += amount_of(product.price, item.quantity)
    return items, products, total


def add_cart_item(db: Session, user: User, *, product_id: int, quantity: int) -> None:
    """加入购物车（同商品合并数量），并发安全。

    先原子累加（含上限判定）；无匹配再走首插。注意"累加 0 行"有三种成因：
    条目不存在、条目存在但超限、**并发创建窗口**（UPDATE 与后续查询之间，
    其他请求刚提交了同条目）——因此不能凭"查询到条目"就判定超限，
    而是存在时再原子累加一次，仍失败才确认超限。
    """
    product = repository.get_product(db, product_id)
    if product is None or product.status != ProductStatus.ON_SALE:
        raise NotFoundError("商品不存在或已下架")

    if repository.increase_cart_quantity(db, user.id, product_id, quantity, MAX_QUANTITY_PER_ITEM):
        db.commit()
        return

    if repository.get_cart_item_by_product(db, user.id, product_id) is not None:
        # 条目存在却累加 0 行：并发创建窗口（重试可命中）或确实超限
        if repository.increase_cart_quantity(
            db, user.id, product_id, quantity, MAX_QUANTITY_PER_ITEM
        ):
            db.commit()
            return
        raise BadRequestError(f"单个商品一次最多 {MAX_QUANTITY_PER_ITEM} 件")

    try:
        repository.add_cart_item(
            db, CartItem(user_id=user.id, product_id=product_id, quantity=quantity)
        )
        db.commit()
    except IntegrityError:
        # 并发下条目已被其他请求创建：回滚后回退为原子累加
        db.rollback()
        if not repository.increase_cart_quantity(
            db, user.id, product_id, quantity, MAX_QUANTITY_PER_ITEM
        ):
            raise BadRequestError(f"单个商品一次最多 {MAX_QUANTITY_PER_ITEM} 件") from None
        db.commit()


def update_cart_item(db: Session, user: User, *, item_id: int, quantity: int) -> None:
    item = repository.get_cart_item(db, user.id, item_id)
    if item is None:
        raise NotFoundError("购物车条目不存在")
    item.quantity = quantity
    db.commit()


def remove_cart_item(db: Session, user: User, *, item_id: int) -> None:
    item = repository.get_cart_item(db, user.id, item_id)
    if item is None:
        raise NotFoundError("购物车条目不存在")
    repository.delete_cart_item(db, item)
    db.commit()


def checkout_cart(
    db: Session,
    user: User,
    *,
    idem_key: str | None = None,
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
) -> Order:
    """购物车结算：一次只能结算同一商户的商品；扣减与建单同一事务；幂等同 create_order。

    收货信息随订单快照落库。
    """
    existing = _find_by_idem_key(db, user, idem_key)
    if existing is not None:
        return existing

    items = repository.list_cart_items(db, user.id)
    if not items:
        raise ConflictError("购物车为空")
    products = repository.get_products_by_ids(db, [item.product_id for item in items])
    for item in items:
        product = products.get(item.product_id)
        if product is None or product.status != ProductStatus.ON_SALE:
            raise ConflictError("购物车中有已下架的商品，请先移除")
    merchants = {product.merchant_id for product in products.values()}
    if len(merchants) != 1:
        raise BadRequestError("一次只能结算同一商户的商品，请分批下单")

    total = Decimal("0.00")
    for item in items:
        total += amount_of(products[item.product_id].price, item.quantity)
    if total > MAX_ORDER_AMOUNT:
        raise BadRequestError("订单金额超出上限，请减少购买数量")

    reserved: list[tuple[int, int]] = []
    try:
        for item in items:
            _reserve_and_decrease(db, products[item.product_id], item.quantity, reserved)
    except Exception:
        db.rollback()  # 先撤销本请求扣减，再按权威值回补闸门
        _compensate_all(db, reserved)
        raise

    order = Order(
        user_id=user.id,
        merchant_id=next(iter(merchants)),
        amount=total,
        status=OrderStatus.CREATED,
        idem_key=idem_key,
        expire_at=_order_expire_at(),
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        receiver_address=receiver_address,
    )
    try:
        # 同 create_order：try 从 create_order 起（其内部 flush 会先执行 INSERT）。
        repository.create_order(db, order)
        repository.add_order_items(
            db,
            [
                OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    product_name=products[item.product_id].name,
                    unit_price=products[item.product_id].price,
                    quantity=item.quantity,
                    amount=amount_of(products[item.product_id].price, item.quantity),
                )
                for item in items
            ],
        )
        for item in items:
            repository.add_inventory_movement(
                db,
                InventoryMovement(
                    product_id=item.product_id,
                    change=-item.quantity,
                    reason=InventoryReason.ORDER,
                    ref_id=order.id,
                ),
            )
        # 清车 0 行说明另一个结算请求已抢先处理该购物车：本次请求整体放弃，
        # 避免同一车内容（不同幂等键）被重复下单。
        if not repository.clear_cart(db, user.id):
            db.rollback()  # 先撤销本请求扣减，再按权威值回补闸门
            _compensate_all(db, reserved)
            raise ConflictError("购物车已结算，请刷新后重试")
        db.commit()
    except IntegrityError:
        db.rollback()
        _compensate_all(db, reserved)  # 本次请求无成交，闸门按权威值回补
        existing = _find_by_idem_key(db, user, idem_key)
        if existing is not None:
            return existing  # 并发重放：返回先到者已创建的订单
        raise
    _sync_all(db, products)
    return order


def list_my_orders(db: Session, user: User, page: PageQuery) -> tuple[list[Order], int]:
    rows, total = pagination.paginate(db, repository.order_list_query(user_id=user.id), page)
    _attach_refund_status(db, rows)
    return rows, total


def _attach_refund_status(db: Session, orders: list[Order]) -> None:
    """给订单列表挂上最新支付单的退款状态（动态属性，供 OrderPublic 序列化）。"""
    payments = repository.latest_payments_for_orders(db, [order.id for order in orders])
    for order in orders:
        payment = payments.get(order.id)
        order.payment_refund_status = payment.refund_status if payment is not None else None
        order.payment_id = payment.id if payment is not None else None


def _restore_order_stock(db: Session, order: Order, *, reason: str) -> dict[int, Product]:
    """回补订单项库存并记流水，返回受影响商品映射（供提交后同步 Redis 闸门）。"""
    products: dict[int, Product] = {}
    for item in repository.list_order_items(db, order.id):
        repository.increase_stock(db, item.product_id, item.quantity)
        repository.add_inventory_movement(
            db,
            InventoryMovement(
                product_id=item.product_id,
                change=item.quantity,
                reason=reason,
                ref_id=order.id,
            ),
        )
        product = repository.get_product(db, item.product_id)
        if product is not None:
            products[item.product_id] = product
    return products


def cancel_order(db: Session, user: User, order_id: int) -> Order:
    """取消订单（买家本人，仅待支付）：原子状态翻转防并发双取消，库存同事务回补。

    已支付订单不可取消（平台不做资金池，退款类诉求走在线客服）；
    回补后按数据库权威值同步 Redis 闸门。
    """
    order = repository.get_order_for_update(db, order_id)
    if order is None or order.user_id != user.id:
        raise NotFoundError("订单不存在")
    if order.status != OrderStatus.CREATED:
        raise ConflictError("只有待支付的订单可以取消")

    if not repository.cancel_order_if_created(db, order.id, user.id):
        # 并发：另一请求已抢先取消（或状态刚变化）
        raise ConflictError("订单状态已变化，请刷新后重试")

    products = _restore_order_stock(db, order, reason=InventoryReason.CANCEL)
    admin_service.record_action(
        db,
        actor_id=user.id,
        action=admin_service.ACTION_ORDER_CANCEL,
        target_type="order",
        target_id=order.id,
        detail=f"买家 {user.phone} 取消订单 #{order.id}（￥{order.amount}），库存已回补",
        commit=False,  # 与取消动作同一事务
    )
    db.commit()
    _sync_all(db, products)  # 回补后闸门按数据库权威值重置
    return order


def expire_unpaid_orders(db: Session, *, now: datetime | None = None, limit: int = 200) -> int:
    """超时未支付的订单自动取消（定时任务 / 手动脚本调用），返回处理条数。

    - 复用买家取消语义：**原子条件更新** `created → cancelled`（与买家手动取消并发时
      只有一个生效，库存不会回补两次）；幂等，重复执行不会重复处理；
    - 库存同事务回补 + 流水（reason=expire，与买家取消区分）；
    - 支付单不置 failed：支付链接可能已被打开，迟到回调由支付回调落 success + 待退款；
    - 审计 `order.expire`（系统动作，actor_id 为空）与状态变更同事务；
    - 逐条提交 + 单条异常回滚跳过：一个订单出问题不拖垮同批次其他订单（下一轮会重试）。
    """
    moment = now or _now()
    order_ids = repository.list_expired_order_ids(db, now=moment, limit=limit)
    expired = 0
    for order_id in order_ids:
        try:
            if not repository.cancel_if_expired(db, order_id, moment):
                continue  # 与买家取消并发：对方已处理
            order = repository.get_order(db, order_id)
            if order is None:
                continue
            products = _restore_order_stock(db, order, reason=InventoryReason.EXPIRE)
            # 不改支付单状态：支付链接可能已被用户打开，网关侧仍可能收款；
            # 迟到回调由 handle_payment_callback 落 success + 待退款，而非直接丢弃。
            detail = f"订单 #{order.id} 超时未支付自动取消（￥{order.amount}），库存已回补"
            admin_service.record_action(
                db,
                actor_id=None,  # 系统动作
                action=admin_service.ACTION_ORDER_EXPIRE,
                target_type="order",
                target_id=order.id,
                detail=detail,
                commit=False,  # 与取消动作同一事务
            )
            db.commit()
        except Exception:  # 单条失败跳过，不影响同批次其他订单（下一轮重试）
            db.rollback()
            logger.exception("超时取消订单 #%s 失败，已跳过（将在下一轮重试）", order_id)
            continue
        _sync_all(db, products)  # 回补后闸门按数据库权威值重置
        expired += 1
    return expired


def list_merchant_orders(db: Session, merchant: User, page: PageQuery) -> tuple[list[Order], int]:
    """订单列表：商户 / 企业看自己；管理员看全平台（演示与运营需要）。"""
    merchant_id = None if merchant.role == UserRole.ADMIN else merchant.id
    rows, total = pagination.paginate(
        db, repository.order_list_query(merchant_id=merchant_id), page
    )
    _attach_refund_status(db, rows)
    return rows, total


def get_order_detail(
    db: Session, order_id: int, user: User
) -> tuple[Order, list[OrderItem], Payment | None]:
    """订单详情：买家 / 该笔商户 / 管理员可见，其余按不存在处理。"""
    order = repository.get_order(db, order_id)
    if order is None or not (
        order.user_id == user.id or order.merchant_id == user.id or user.role == UserRole.ADMIN
    ):
        raise NotFoundError("订单不存在")
    return (
        order,
        repository.list_order_items(db, order.id),
        repository.get_latest_payment(db, order.id),
    )


def create_payment(db: Session, user: User, *, order_id: int) -> tuple[Payment, str | None]:
    """创建支付单，返回 (支付单, 支付链接)。

    同一订单已有未处理（created）支付单时直接复用——重复点击 / 重试
    不再新开支付单，避免对账时同单多单。

    下单动作经支付网关适配层（N13）：mock 网关没有支付链接（pay_url 为 None，前端仍走
    管理员模拟回调）；接真实网关后这里返回收银台链接 / 二维码，业务代码不变。
    """
    order = repository.get_order_for_update(db, order_id)
    if order is None or order.user_id != user.id:
        raise NotFoundError("订单不存在")
    if order.status != OrderStatus.CREATED:
        raise ConflictError("订单当前状态不可支付")
    latest = repository.get_open_payment(db, order.id)
    if latest is not None:
        gateway_payment = payment_gateway.get_gateway().create_payment(
            payment_id=latest.id,
            order_id=order.id,
            amount=latest.amount,
            subject=f"平台订单 #{order.id}",
        )
        return latest, gateway_payment.pay_url
    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        amount=order.amount,
        status=PaymentStatus.CREATED,
    )
    try:
        repository.create_payment(db, payment)
        db.commit()
    except IntegrityError:
        # 并发双击：另一个请求先建成功（部分唯一索引兜底）→ 返回已存在的那张
        db.rollback()
        existing = repository.get_open_payment(db, order.id)
        if existing is None:
            raise ConflictError("支付单创建冲突，请重试") from None
        gateway_payment = payment_gateway.get_gateway().create_payment(
            payment_id=existing.id,
            order_id=order.id,
            amount=existing.amount,
            subject=f"平台订单 #{order.id}",
        )
        return existing, gateway_payment.pay_url
    gateway_payment = payment_gateway.get_gateway().create_payment(
        payment_id=payment.id,
        order_id=order.id,
        amount=payment.amount,
        subject=f"平台订单 #{order.id}",
    )
    return payment, gateway_payment.pay_url


def handle_gateway_notify(db: Session, *, headers: Mapping[str, str], body: bytes) -> Payment:
    """处理**第三方网关**的异步回调：验签 → 解析 → 落到本地支付单。

    这是接真实网关时回调端点要调用的入口（当前不暴露公网端点：mock 网关无签名可验，
    开放等于任何人都能标记支付成功——接入步骤见 docs/部署.md）。
    """
    gateway = payment_gateway.get_gateway()
    if not gateway.verify_notify(headers=headers, body=body):
        raise ForbiddenError("回调验签失败")
    notify = gateway.parse_notify(headers=headers, body=body)
    payment_id = payment_gateway.payment_id_from_out_trade_no(notify.out_trade_no)
    if payment_id is None:
        raise NotFoundError("回调单号无法定位支付单")
    return handle_payment_callback(
        db, payment_id=payment_id, success=notify.success, trade_no=notify.trade_no, actor=None
    )


def handle_payment_callback(
    db: Session,
    *,
    payment_id: int,
    success: bool,
    trade_no: str | None,
    actor: User | None = None,
) -> Payment:
    """模拟第三方支付回调（当前仅管理员可触发；接真实网关后改为验签通过再调用本函数）。

    actor 为触发回调的操作人（管理员），用于审计留痕；接真实网关后可为 None
    （此时以网关验签为准，不记录操作人）。
    """
    payment = repository.get_payment(db, payment_id)
    if payment is None:
        raise NotFoundError("支付单不存在")
    if payment.status not in (PaymentStatus.CREATED, PaymentStatus.FAILED):
        raise ConflictError("支付单已处理")
    # 先锁订单：与取消 / 建支付单串行化，保证「订单状态判定 + 支付单翻转」不被插队
    order = repository.get_order_for_update(db, payment.order_id)
    if order is None:
        raise NotFoundError("订单不存在")
    now = _now()
    payable = order.status == OrderStatus.CREATED
    # 原子抢占：并发回调（网关重投 / 管理员双击）只有一个请求能把支付单改走，
    # 落败者返回 409，且不会重复写通知。
    if success:
        claimed = repository.claim_payment_success(
            db,
            payment_id,
            trade_no=trade_no,
            paid_at=now,
            # 订单已取消 / 已支付时，历史 failed 支付单也可能收到迟到回调（钱已收）
            allow_failed=not payable,
        )
    else:
        claimed = repository.claim_payment_failed(db, payment_id, trade_no=trade_no)
    if not claimed:
        raise ConflictError("支付单已处理")

    if success and payable:
        repository.mark_order_paid_if_created(db, order.id, paid_at=now)
        notifications_service.notify(
            db,
            order.merchant_id,
            type=NotificationType.ORDER_PAID,
            title="订单已支付",
            content=f"订单 #{order.id} 已支付 ￥{order.amount:.2f}，请及时发货",
            ref_type="order",
            ref_id=order.id,
        )
    elif success:
        # 钱已收到，但订单已不可支付（取消 / 重复支付）：落 success + 待退款，
        # 通知买家、商户与管理员，由管理员线下退款后登记关闭。
        reason = (
            "订单已取消"
            if order.status == OrderStatus.CANCELLED
            else f"订单状态为 {order.status}，疑似重复支付"
        )
        payment.refund_status = PaymentRefundStatus.PENDING
        payment.refund_note = reason
        admin_service.record_action(
            db,
            actor_id=actor.id if actor is not None else None,
            action=admin_service.ACTION_PAYMENT_EXCEPTION,
            target_type="payment",
            target_id=payment.id,
            detail=(
                f"支付单 #{payment.id} / 订单 #{order.id}：{reason}，"
                f"收到支付 ￥{payment.amount}，进入待退款"
            ),
            commit=False,
        )
        _notify_payment_exception(db, order, payment, reason)

    if actor is not None:
        admin_service.record_action(
            db,
            actor_id=actor.id,
            action=admin_service.ACTION_PAYMENT_CALLBACK,
            target_type="payment",
            target_id=payment.id,
            detail=(
                f"{actor.phone} 模拟支付回调：支付单 #{payment.id} / 订单 "
                f"#{payment.order_id}，{'成功' if success else '失败'}"
            ),
            commit=False,
        )
    db.commit()
    db.refresh(payment)
    return payment


def _notify_payment_exception(db: Session, order: Order, payment: Payment, reason: str) -> None:
    """异常支付通知买家 / 商户 / 全部管理员（同事务，随回调一起提交）。"""
    recipients = {order.user_id, order.merchant_id, *users_service.list_active_admin_ids(db)}
    content = (
        f"订单 #{order.id} {reason}，但收到支付 ￥{payment.amount:.2f}"
        f"（支付单 #{payment.id}），需退款处理"
    )
    for user_id in recipients:
        notifications_service.notify(
            db,
            user_id,
            type=NotificationType.PAYMENT_EXCEPTION,
            title="支付异常，需退款",
            content=content,
            ref_type="order",
            ref_id=order.id,
        )


def refund_payment(
    db: Session, operator: User, payment_id: int, *, note: str | None = None
) -> Payment:
    """管理员登记异常支付已退款（线下退款后关闭流程）。"""
    if operator.role != UserRole.ADMIN:
        raise ForbiddenError("仅管理员可登记退款")
    payment = repository.get_payment(db, payment_id)
    if payment is None:
        raise NotFoundError("支付单不存在")
    if payment.refund_status != PaymentRefundStatus.PENDING:
        raise ConflictError("该支付单不在待退款状态")
    payment.refund_status = PaymentRefundStatus.REFUNDED
    payment.refunded_at = _now()
    payment.refund_note = (note or payment.refund_note or "")[:255] or None
    admin_service.record_action(
        db,
        actor_id=operator.id,
        action=admin_service.ACTION_PAYMENT_REFUND,
        target_type="payment",
        target_id=payment.id,
        detail=f"{operator.phone} 登记退款：支付单 #{payment.id} ￥{payment.amount}",
        commit=False,
    )
    order = repository.get_order(db, payment.order_id)
    recipients = {payment.user_id}
    if order is not None:
        recipients.add(order.merchant_id)
    for user_id in recipients:
        notifications_service.notify(
            db,
            user_id,
            type=NotificationType.PAYMENT_REFUNDED,
            title="支付已退款",
            content=(
                f"支付单 #{payment.id}（订单 #{payment.order_id}）已退款 ￥{payment.amount:.2f}"
            ),
            ref_type="order",
            ref_id=payment.order_id,
        )
    db.commit()
    db.refresh(payment)
    return payment


# ---------- 履约：发货 / 签收 / 确认收货（N3） ----------


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def ship_order(
    db: Session, operator: User, order_id: int, *, carrier: str, tracking_no: str
) -> Order:
    """发货（订单归属商户 / 管理员）：仅已支付订单；原子翻转防重复发货。

    运单号必填（买家据此查物流）；发货后买家可确认收货，或按
    「签收 + ORDER_AUTO_CONFIRM_DAYS / 发货 + fallback」自动确认。
    """
    order = repository.get_order(db, order_id)
    if order is None or (not _is_admin(operator) and order.merchant_id != operator.id):
        raise NotFoundError("订单不存在")
    if order.status != OrderStatus.PAID:
        raise ConflictError("只有已支付的订单可以发货")
    now = _now()
    if not repository.ship_if_paid(
        db, order.id, order.merchant_id, carrier=carrier, tracking_no=tracking_no, now=now
    ):
        raise ConflictError("订单状态已变化，请刷新后重试")
    admin_service.record_action(
        db,
        actor_id=operator.id,
        action=admin_service.ACTION_ORDER_SHIP,
        target_type="order",
        target_id=order.id,
        detail=f"订单 #{order.id} 已发货（{carrier} {tracking_no}）",
        commit=False,
    )
    notifications_service.notify(
        db,
        order.user_id,
        type=NotificationType.ORDER_SHIPPED,
        title="订单已发货",
        content=f"订单 #{order.id} 已由 {carrier} 发出，运单号 {tracking_no}",
        ref_type="order",
        ref_id=order.id,
    )
    db.commit()
    db.refresh(order)
    return order


def mark_order_delivered(db: Session, operator: User, order_id: int) -> Order:
    """标记已签收（订单归属商户 / 管理员）：作为自动确认收货的计时起点。

    当前没有物流查询接口，签收信号由人工标记；将来接入快递查询服务后，
    由适配层写同一个字段，订单流程不变。
    """
    order = repository.get_order(db, order_id)
    if order is None or (not _is_admin(operator) and order.merchant_id != operator.id):
        raise NotFoundError("订单不存在")
    if order.status != OrderStatus.SHIPPED:
        raise ConflictError("只有已发货的订单可以标记签收")
    if order.delivered_at is not None:
        raise ConflictError("该订单已标记签收")
    now = _now()
    if not repository.mark_delivered_if_shipped(db, order.id, now):
        raise ConflictError("订单状态已变化，请刷新后重试")
    days = get_settings().order_auto_confirm_days
    admin_service.record_action(
        db,
        actor_id=operator.id,
        action=admin_service.ACTION_ORDER_DELIVER,
        target_type="order",
        target_id=order.id,
        detail=f"订单 #{order.id} 已签收（{days} 天内未确认收货将自动确认）",
        commit=False,
    )
    db.commit()
    db.refresh(order)
    return order


def receive_order(db: Session, buyer: User, order_id: int) -> Order:
    """买家确认收货：已发货 → 已完成。"""
    order = repository.get_order(db, order_id)
    if order is None or order.user_id != buyer.id:
        raise NotFoundError("订单不存在")
    if order.status != OrderStatus.SHIPPED:
        raise ConflictError("只有已发货的订单可以确认收货")
    now = _now()
    if not repository.complete_if_shipped(db, order.id, buyer.id, now):
        raise ConflictError("订单状态已变化，请刷新后重试")
    admin_service.record_action(
        db,
        actor_id=buyer.id,
        action=admin_service.ACTION_ORDER_RECEIVE,
        target_type="order",
        target_id=order.id,
        detail=f"买家 {buyer.phone} 确认收货，订单 #{order.id} 已完成",
        commit=False,
    )
    db.commit()
    db.refresh(order)
    return order


def auto_confirm_received_orders(
    db: Session, *, now: datetime | None = None, limit: int = 200
) -> int:
    """自动确认收货（定时任务 / 手动脚本），返回处理条数。

    触发条件（按标记情况二选一）：
    - 已标记签收的订单：以**签收时间**为起点，签收后 ORDER_AUTO_CONFIRM_DAYS（默认 7）天未确认；
    - 未标记签收的订单：以**发货时间**为起点，发货后 ORDER_AUTO_CONFIRM_FALLBACK_DAYS（默认 15）
      天兜底，避免订单永远停在已发货（若商户在兜底期之后才补标记签收，则改按签收时间再等满窗口）。

    逐条原子条件更新（幂等；与买家手动确认并发只有一个生效）；单条异常回滚跳过；
    系统动作写审计。
    """
    moment = now or _now()
    settings = get_settings()
    delivered_cutoff = moment - timedelta(days=settings.order_auto_confirm_days)
    shipped_cutoff = moment - timedelta(days=settings.order_auto_confirm_fallback_days)
    order_ids = repository.list_auto_confirm_candidates(
        db, delivered_cutoff=delivered_cutoff, shipped_cutoff=shipped_cutoff, limit=limit
    )
    confirmed = 0
    for order_id in order_ids:
        try:
            if not repository.auto_complete_if_shippable(
                db,
                order_id,
                delivered_cutoff=delivered_cutoff,
                shipped_cutoff=shipped_cutoff,
                now=moment,
            ):
                continue  # 与买家手动确认并发：对方已处理
            order = repository.get_order(db, order_id)
            if order is None:
                continue
            reason = (
                f"签收后超过 {settings.order_auto_confirm_days} 天未确认"
                if order.delivered_at is not None
                else f"发货后超过 {settings.order_auto_confirm_fallback_days} 天未确认"
                "（商户未标记签收）"
            )
            admin_service.record_action(
                db,
                actor_id=None,  # 系统动作
                action=admin_service.ACTION_ORDER_AUTO_CONFIRM,
                target_type="order",
                target_id=order.id,
                detail=f"订单 #{order.id} 自动确认收货（{reason}）",
                commit=False,
            )
            db.commit()
        except Exception:  # 单条失败跳过，不影响同批次（下一轮重试）
            db.rollback()
            logger.exception("自动确认收货订单 #%s 失败，已跳过（将在下一轮重试）", order_id)
            continue
        confirmed += 1
    return confirmed


# ---------- 售后（N4） ----------

# 可选的售后原因（预设类别，避免自由文本无法统计）
ALLOWED_AFTER_SALE_REASONS = (
    AfterSaleReason.QUALITY,
    AfterSaleReason.MISSING,
    AfterSaleReason.MISMATCH,
    AfterSaleReason.DAMAGED,
    AfterSaleReason.OTHER,
)


def _as_utc(moment: datetime) -> datetime:
    """SQLite 读出的时间会丢时区信息，统一按 UTC 处理后再比较。"""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


_AFTER_SALE_REASON_LABEL = {
    AfterSaleReason.QUALITY: "质量问题",
    AfterSaleReason.MISSING: "少发 / 漏发",
    AfterSaleReason.MISMATCH: "与描述不符",
    AfterSaleReason.DAMAGED: "包装 / 商品破损",
    AfterSaleReason.OTHER: "其他",
}


def _notify_after_sale(db: Session, sale: AfterSale, *, resolved: bool) -> None:
    """售后结单后通知买家（完成 / 拒绝两种结果）。"""
    notifications_service.notify(
        db,
        sale.user_id,
        type=(
            NotificationType.AFTER_SALE_RESOLVED
            if resolved
            else NotificationType.AFTER_SALE_REJECTED
        ),
        title="售后已处理" if resolved else "售后被拒绝",
        content=(
            f"售后 #{sale.id}（订单 #{sale.order_id}）已处理完成"
            if resolved
            else f"售后 #{sale.id}（订单 #{sale.order_id}）被商户拒绝，可在售后详情查看说明"
        ),
        ref_type="after_sale",
        ref_id=sale.id,
    )


def _role_of(user: User) -> str:
    """留言作者角色（前端据此区分展示）。"""
    if user.role == UserRole.ADMIN:
        return "admin"
    if user.role in (UserRole.MERCHANT, UserRole.ENTERPRISE):
        return "merchant"
    return "buyer"


def _get_sale_for_viewer(db: Session, viewer: User, sale_id: int) -> AfterSale:
    """按归属取售后单：管理员看全部；买家看自己的；商户看自己订单的。其余一律 404。"""
    sale = repository.get_after_sale(db, sale_id)
    if sale is None or not (
        viewer.role == UserRole.ADMIN or sale.user_id == viewer.id or sale.merchant_id == viewer.id
    ):
        raise NotFoundError("售后单不存在")
    return sale


def _get_sale_for_operator(db: Session, operator: User, sale_id: int) -> AfterSale:
    """商户 / 管理员操作售后单（受理 / 完成 / 拒绝）：他人订单一律 404。"""
    sale = repository.get_after_sale(db, sale_id)
    if sale is None or (not _is_admin(operator) and sale.merchant_id != operator.id):
        raise NotFoundError("售后单不存在")
    return sale


def apply_after_sale(
    db: Session,
    user: User,
    *,
    order_id: int,
    reason: str,
    description: str | None = None,
) -> AfterSale:
    """买家申请售后。

    规则：已支付（含已发货 / 已完成）的订单可申请；**已完成**的订单须在完成时间后
    `AFTER_SALE_WINDOW_DAYS`（默认 15）天内；同一订单同时只允许一条未结单。
    平台不做资金池——售后单只跟踪原因与处理过程，退款 / 换货由商户线下或经第三方处理。
    """
    if reason not in ALLOWED_AFTER_SALE_REASONS:
        raise BadRequestError("售后原因不在可选范围内")
    order = repository.get_order(db, order_id)
    if order is None or order.user_id != user.id:
        raise NotFoundError("订单不存在")
    if order.status not in (
        OrderStatus.PAID,
        OrderStatus.SHIPPED,
        OrderStatus.COMPLETED,
    ):
        raise ConflictError("只有已支付（含已发货 / 已完成）的订单可以申请售后")
    if order.status == OrderStatus.COMPLETED:
        window_days = get_settings().after_sale_window_days
        # 兜底链：completed_at 缺失（历史 / 手工数据）时回退 paid_at / created_at，
        # 而不是当成「刚刚完成」——否则售后窗口会被无限放宽（fail-closed）。
        reference = order.completed_at or order.paid_at or order.created_at
        if reference is not None and _now() - _as_utc(reference) > timedelta(days=window_days):
            raise ConflictError(f"已超过售后有效期（确认收货后 {window_days} 天内可申请）")
    if repository.open_after_sale_for_order(db, order.id) is not None:
        raise ConflictError("该订单已有一条未结单的售后申请")

    try:
        created = repository.create_after_sale(
            db,
            AfterSale(
                order_id=order.id,
                user_id=user.id,
                merchant_id=order.merchant_id,
                reason=reason,
                description=description,
            ),
        )
    except IntegrityError:
        # 并发双开：两个请求都通过了「未结单」检查，靠偏唯一索引
        # uq_after_sales_open_order 兜底——后到者回滚并提示已有未结单
        db.rollback()
        raise ConflictError("该订单已有一条未结单的售后申请") from None
    admin_service.record_action(
        db,
        actor_id=user.id,
        action=admin_service.ACTION_AFTER_SALE_CREATE,
        target_type="after_sale",
        target_id=created.id,
        detail=f"买家 {user.phone} 对订单 #{order.id} 申请售后（{reason}）",
        commit=False,
    )
    notifications_service.notify(
        db,
        order.merchant_id,
        type=NotificationType.AFTER_SALE_CREATED,
        title="新的售后申请",
        content=(
            f"订单 #{order.id} 有新的售后申请"
            f"（{_AFTER_SALE_REASON_LABEL.get(reason, reason)}），请尽快处理"
        ),
        ref_type="after_sale",
        ref_id=created.id,
    )
    db.commit()
    db.refresh(created)
    return created


def list_after_sales(
    db: Session, viewer: User, page: PageQuery, *, status: str | None = None
) -> tuple[list[AfterSale], int]:
    """售后列表：管理员看全平台；商户 / 企业看自己参与的；游客看自己的。"""
    if viewer.role == UserRole.ADMIN:
        stmt = repository.after_sale_list_query(status=status)
    elif viewer.role in (UserRole.MERCHANT, UserRole.ENTERPRISE):
        stmt = repository.after_sale_list_query(status=status, participant_id=viewer.id)
    else:
        stmt = repository.after_sale_list_query(status=status, user_id=viewer.id)
    return pagination.paginate(db, stmt, page)


def get_after_sale_detail(
    db: Session, viewer: User, sale_id: int
) -> tuple[AfterSale, list[AfterSaleMessage], Order | None]:
    """售后详情：单据 + 留言流 + 关联订单（供界面展示上下文）。"""
    sale = _get_sale_for_viewer(db, viewer, sale_id)
    messages = repository.list_after_sale_messages(db, sale.id)
    order = repository.get_order(db, sale.order_id)
    return sale, messages, order


def accept_after_sale(db: Session, operator: User, sale_id: int) -> AfterSale:
    """商户受理：待处理 → 处理中（原子条件更新，与买家撤销并发只有一个生效）。"""
    sale = _get_sale_for_operator(db, operator, sale_id)
    if sale.status != AfterSaleStatus.PENDING:
        raise ConflictError("只有待处理的售后申请可以受理")
    now = _now()
    if not repository.transition_after_sale(
        db,
        sale.id,
        from_statuses=(AfterSaleStatus.PENDING,),
        to_status=AfterSaleStatus.PROCESSING,
        handler_id=operator.id,
        now=now,
    ):
        raise ConflictError("售后单状态已变化，请刷新后重试")
    admin_service.record_action(
        db,
        actor_id=operator.id,
        action=admin_service.ACTION_AFTER_SALE_ACCEPT,
        target_type="after_sale",
        target_id=sale.id,
        detail=f"商户受理售后 #{sale.id}（订单 #{sale.order_id}）",
        commit=False,
    )
    db.commit()
    db.refresh(sale)
    return sale


def resolve_after_sale(
    db: Session, operator: User, sale_id: int, *, note: str | None = None
) -> AfterSale:
    """商户完成售后：处理中 → 已解决；可选附一条处理说明（进留言流）。"""
    sale = _get_sale_for_operator(db, operator, sale_id)
    if sale.status != AfterSaleStatus.PROCESSING:
        raise ConflictError("只有处理中的售后可以标记完成")
    now = _now()
    if not repository.transition_after_sale(
        db,
        sale.id,
        from_statuses=(AfterSaleStatus.PROCESSING,),
        to_status=AfterSaleStatus.RESOLVED,
        handler_id=operator.id,
        close=True,
        now=now,
    ):
        raise ConflictError("售后单状态已变化，请刷新后重试")
    if note and note.strip():
        repository.add_after_sale_message(
            db,
            AfterSaleMessage(
                after_sale_id=sale.id,
                author_id=operator.id,
                author_role=_role_of(operator),
                content=f"【已解决】{note.strip()}",
            ),
        )
    admin_service.record_action(
        db,
        actor_id=operator.id,
        action=admin_service.ACTION_AFTER_SALE_RESOLVE,
        target_type="after_sale",
        target_id=sale.id,
        detail=f"售后 #{sale.id} 已解决（订单 #{sale.order_id}）",
        commit=False,
    )
    _notify_after_sale(db, sale, resolved=True)
    db.commit()
    db.refresh(sale)
    return sale


def reject_after_sale(db: Session, operator: User, sale_id: int, *, reason: str) -> AfterSale:
    """商户拒绝售后：待处理 / 处理中 → 已拒绝；**理由必填**（作为一条留言留痕）。"""
    sale = _get_sale_for_operator(db, operator, sale_id)
    reason = (reason or "").strip()
    if not reason:
        raise BadRequestError("拒绝售后必须填写理由")
    if sale.status not in AfterSaleStatus.OPEN_STATUSES:
        raise ConflictError("已结单的售后不能再拒绝")
    now = _now()
    if not repository.transition_after_sale(
        db,
        sale.id,
        from_statuses=AfterSaleStatus.OPEN_STATUSES,
        to_status=AfterSaleStatus.REJECTED,
        handler_id=operator.id,
        close=True,
        now=now,
    ):
        raise ConflictError("售后单状态已变化，请刷新后重试")
    repository.add_after_sale_message(
        db,
        AfterSaleMessage(
            after_sale_id=sale.id,
            author_id=operator.id,
            author_role=_role_of(operator),
            content=f"【拒绝】{reason}",
        ),
    )
    admin_service.record_action(
        db,
        actor_id=operator.id,
        action=admin_service.ACTION_AFTER_SALE_REJECT,
        target_type="after_sale",
        target_id=sale.id,
        # 审计列 String(255)：理由本身可达 280 字，这里截断避免 PG 上溢出 500
        detail=f"售后 #{sale.id} 被拒绝：{reason[:120]}",
        commit=False,
    )
    _notify_after_sale(db, sale, resolved=False)
    db.commit()
    db.refresh(sale)
    return sale


def withdraw_after_sale(db: Session, user: User, sale_id: int) -> AfterSale:
    """买家撤销申请：仅受理前（待处理）可撤销；商户已受理则需协商或走客服。"""
    sale = repository.get_after_sale(db, sale_id)
    if sale is None or sale.user_id != user.id:
        raise NotFoundError("售后单不存在")
    if sale.status != AfterSaleStatus.PENDING:
        raise ConflictError("商户已受理，不能撤销（可继续与商户沟通或发起在线客服）")
    now = _now()
    if not repository.transition_after_sale(
        db,
        sale.id,
        from_statuses=(AfterSaleStatus.PENDING,),
        to_status=AfterSaleStatus.WITHDRAWN,
        close=True,
        now=now,
    ):
        raise ConflictError("售后单状态已变化，请刷新后重试")
    admin_service.record_action(
        db,
        actor_id=user.id,
        action=admin_service.ACTION_AFTER_SALE_WITHDRAW,
        target_type="after_sale",
        target_id=sale.id,
        detail=f"买家 {user.phone} 撤销售后 #{sale.id}",
        commit=False,
    )
    db.commit()
    db.refresh(sale)
    return sale


def post_after_sale_message(
    db: Session, author: User, sale_id: int, *, content: str
) -> AfterSaleMessage:
    """售后留言（买家 / 商户 / 管理员均可，需有归属）；结单后不再允许新增。"""
    sale = _get_sale_for_viewer(db, author, sale_id)
    content = (content or "").strip()
    if not content:
        raise BadRequestError("留言内容不能为空")
    # 条件插入：与「商户结单」并发交错时，结单后落地的留言会被原子拒绝（而不是先读后写的漏洞）
    message = repository.add_after_sale_message_if_open(
        db,
        after_sale_id=sale.id,
        author_id=author.id,
        author_role=_role_of(author),
        content=content,
        now=_now(),
    )
    if message is None:
        db.rollback()
        raise ConflictError("售后单已结单，不能再留言（如需沟通可再发起售后或走在线客服）")
    db.commit()
    return message


def purge_expired_views(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的商品浏览记录（数据保留期清理）。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days)
    condition = ProductView.viewed_at < cutoff
    if dry_run:
        return retention.count_expired(
            db, ProductView, condition=condition, limit=settings.retention_max_per_run
        )
    return retention.batch_delete(
        db,
        ProductView,
        condition=condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )


def purge_expired_inventory(db: Session, *, days: int, dry_run: bool = False) -> int:
    """删除超过保留期的库存流水（对账窗口之外；库存余额本身在 products.stock）。"""
    settings = get_settings()
    cutoff = retention.cutoff_of(days)
    condition = InventoryMovement.created_at < cutoff
    if dry_run:
        return retention.count_expired(
            db, InventoryMovement, condition=condition, limit=settings.retention_max_per_run
        )
    return retention.batch_delete(
        db,
        InventoryMovement,
        condition=condition,
        batch_size=settings.retention_batch_size,
        limit=settings.retention_max_per_run,
    )


# ---------- 订单导出 / 销量看板（增强）----------


_EXPORT_MAX_ROWS = 50000
_EXPORT_BATCH = 500
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

_EXPORT_HEADER = [
    "订单号",
    "状态",
    "金额",
    "买家ID",
    "商户ID",
    "商户名称",
    "收货人",
    "收货电话",
    "收货地址",
    "承运商",
    "运单号",
    "创建时间（北京时间）",
    "支付时间（北京时间）",
    "发货时间（北京时间）",
    "完成时间（北京时间）",
    "商品明细",
]


def _export_scope(operator: User) -> int | None:
    """导出 / 看板的数据范围：管理员全平台，商户与企业仅自己（service 层兜底）。"""
    if operator.role == UserRole.ADMIN:
        return None
    if operator.role not in (UserRole.MERCHANT, UserRole.ENTERPRISE):
        raise ForbiddenError("仅商户 / 企业 / 管理员可导出订单")
    return operator.id


def _input_utc(value: datetime | None) -> datetime | None:
    """筛选入参归一化为 UTC：naive 按业务时区（Asia/Shanghai）解释，aware 直接换算。

    限定 2000–2100 年：极端日期（0001 / 9999）跨时区换算会触发 OverflowError，
    属于客户端参数错误，应返回 400 而不是 500。
    """
    if value is None:
        return None
    if value.year < 2000 or value.year > 2100:
        raise BadRequestError("时间超出支持范围（2000–2100 年）")
    try:
        if value.tzinfo is None:
            return value.replace(tzinfo=_BUSINESS_TZ).astimezone(UTC)
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise BadRequestError("时间超出支持范围") from exc


def _csv_cell(value: object) -> str:
    """CSV 单元格防公式注入：Excel 会把 = + - @ 制表符 / 回车开头的值当公式执行。"""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_CSV_FORMULA_PREFIXES) else text


def export_orders(
    db: Session,
    operator: User,
    *,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[Iterator[list[str]], int, bool]:
    """返回 (CSV 行生成器, 导出行数, 是否截断)。

    生成器先产出表头，再按 500 单一批游标查库（订单项批量取，避免 N+1），
    调用方边写边发；单次上限 5 万行，超出时只导出前 5 万行并由响应头标记截断。
    """
    merchant_id = _export_scope(operator)
    if status is not None and status not in _ORDER_STATUS_LABEL:
        raise BadRequestError("订单状态不合法")
    start_utc = _input_utc(start)
    end_utc = _input_utc(end)
    if start_utc is not None and end_utc is not None and start_utc > end_utc:
        raise BadRequestError("开始时间不能晚于结束时间")

    total = repository.export_order_count(
        db, merchant_id=merchant_id, status=status, start=start_utc, end=end_utc
    )
    exported = min(total, _EXPORT_MAX_ROWS)
    truncated = total > _EXPORT_MAX_ROWS

    def rows() -> Iterator[list[str]]:
        yield list(_EXPORT_HEADER)
        remaining = exported
        last_id: int | None = None
        while remaining > 0:
            batch = repository.export_order_batch(
                db,
                merchant_id=merchant_id,
                status=status,
                start=start_utc,
                end=end_utc,
                last_id=last_id,
                limit=min(_EXPORT_BATCH, remaining),
            )
            if not batch:
                return
            items_map = repository.items_by_order_ids(db, [order.id for order in batch])
            names = users_service.display_names(db, [order.merchant_id for order in batch])
            for order in batch:
                summary = "；".join(
                    f"{item.product_name}×{item.quantity}" for item in items_map.get(order.id, [])
                )
                yield [
                    _csv_cell(order.id),
                    _csv_cell(_ORDER_STATUS_LABEL.get(order.status, order.status)),
                    _csv_cell(f"{order.amount:.2f}"),
                    _csv_cell(order.user_id),
                    _csv_cell(order.merchant_id),
                    _csv_cell(names.get(order.merchant_id, "")),
                    _csv_cell(order.receiver_name or ""),
                    _csv_cell(order.receiver_phone or ""),
                    _csv_cell(order.receiver_address or ""),
                    _csv_cell(order.carrier or ""),
                    _csv_cell(order.tracking_no or ""),
                    _csv_cell(_iso(order.created_at)),
                    _csv_cell(_iso(order.paid_at)),
                    _csv_cell(_iso(order.shipped_at)),
                    _csv_cell(_iso(order.completed_at)),
                    _csv_cell(summary),
                ]
            last_id = batch[-1].id
            remaining -= len(batch)

    return rows(), exported, truncated


_ORDER_STATUS_LABEL = {
    OrderStatus.CREATED: "待支付",
    OrderStatus.PAID: "已支付",
    OrderStatus.SHIPPED: "已发货",
    OrderStatus.COMPLETED: "已完成",
    OrderStatus.CANCELLED: "已取消",
}


def business_now() -> datetime:
    """业务时区当前时间（导出文件名等对外展示用）。"""
    return datetime.now(_BUSINESS_TZ)


def _iso(value: datetime | None) -> str:
    """导出时间统一为业务时区（Asia/Shanghai）。

    数据库统一存 UTC：SQLite 读回 naive UTC（按 UTC 补标记），PostgreSQL 返回
    aware 值（先换算 UTC），最后转上海时间——与筛选入参、看板日界、控制台展示一致。
    """
    return _as_utc(value).astimezone(_BUSINESS_TZ).strftime("%Y-%m-%d %H:%M:%S") if value else ""


def sales_overview(db: Session, operator: User, *, days: int = 14) -> dict[str, object]:
    """商户 / 管理员的销量看板：近 N 天日趋势（订单数 / 成交额）与热销 Top 5。

    只统计已支付及之后的订单（PAID_STATUSES），按**支付时间**落桶（与概览页
    「今日成交额」一致）；日期按业务时区（Asia/Shanghai）切分并补齐无成交日，
    前端柱状图不会把不连续日期压缩成相邻柱子。
    """
    merchant_id = _export_scope(operator)
    days = max(1, min(int(days), 90))
    today = datetime.now(_BUSINESS_TZ).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, time.min, tzinfo=_BUSINESS_TZ).astimezone(UTC)

    counts: dict[date, int] = {}
    revenues: dict[date, Decimal] = {}
    for paid_at, amount in repository.paid_orders_in_window(
        db, merchant_id=merchant_id, since=since
    ):
        local_day = _as_utc(paid_at).astimezone(_BUSINESS_TZ).date()
        counts[local_day] = counts.get(local_day, 0) + 1
        revenues[local_day] = revenues.get(local_day, Decimal("0")) + amount

    series = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        series.append(
            {
                "date": day.isoformat(),
                "orders": counts.get(day, 0),
                "revenue": float(revenues.get(day, Decimal("0"))),
            }
        )

    top = repository.top_selling_products(db, merchant_id=merchant_id, since=since)
    return {
        "days": days,
        "series": series,
        "top_products": [
            {"name": name, "quantity": quantity, "revenue": float(revenue)}
            for name, quantity, revenue in top
        ],
    }

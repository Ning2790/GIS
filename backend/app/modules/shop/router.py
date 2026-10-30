"""shop 模块路由：商品、购物车、下单与支付（C2 交易闭环）。"""

import csv
import io
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, OptionalUser, require_roles
from app.core import cache, hot_search
from app.core.config import get_settings
from app.core.errors import BadRequestError
from app.core.pagination import PageParams, page_data
from app.core.rate_limit import rate_limit
from app.core.response import ok
from app.modules.shop import repository, service
from app.modules.shop.models import Payment, ProductStatus
from app.modules.shop.schemas import (
    AfterSaleCreateRequest,
    AfterSaleDetail,
    AfterSaleMessagePublic,
    AfterSaleMessageRequest,
    AfterSalePublic,
    AfterSaleRejectRequest,
    AfterSaleResolveRequest,
    CartItemAddRequest,
    CartItemPublic,
    CartItemUpdateRequest,
    CartPublic,
    CheckoutRequest,
    MerchantProductPublic,
    OrderCreateRequest,
    OrderDetail,
    OrderItemPublic,
    OrderPublic,
    PaymentCallbackRequest,
    PaymentPublic,
    PaymentRefundRequest,
    ProductCreateRequest,
    ProductDetailPublic,
    ProductPublic,
    ProductStatusRequest,
    ProductUpdateRequest,
    ShipRequest,
)
from app.modules.users.models import User

router = APIRouter(prefix="/shop", tags=["shop"])

# 商户 / 企业专用依赖（写法见 app/api/deps.py 的 require_roles）。
MerchantUser = Annotated[User, Depends(require_roles("merchant", "enterprise"))]
AdminUser = Annotated[User, Depends(require_roles("admin"))]
# 商户后台视角：商户 / 企业看自己，管理员看全平台（服务层按角色过滤）
OperatorUser = Annotated[User, Depends(require_roles("merchant", "enterprise", "admin"))]


def _cart_payload(db: DbSession, user: User) -> dict:
    items, products, total = service.get_cart_detail(db, user)
    payload_items = []
    for item in items:
        product = products.get(item.product_id)
        if product is None:
            continue
        payload_items.append(
            CartItemPublic(
                id=item.id,
                product_id=product.id,
                name=product.name,
                price=float(product.price),
                quantity=item.quantity,
                amount=float(service.amount_of(product.price, item.quantity)),
                stock=product.stock,
                available=(
                    product.status == ProductStatus.ON_SALE and product.stock >= item.quantity
                ),
            )
        )
    return CartPublic(items=payload_items, total_amount=float(total)).model_dump(mode="json")


def _order_detail_payload(db: DbSession, order_id: int, user: User) -> dict:
    order, items, payment = service.get_order_detail(db, order_id, user)
    after_sale = repository.latest_after_sale_for_order(db, order.id)
    # 列表字段（payment_id / payment_refund_status）由动态属性带入，避免重复 kwargs
    order.payment_id = payment.id if payment is not None else None
    order.payment_refund_status = payment.refund_status if payment is not None else None
    data = OrderDetail(
        **OrderPublic.model_validate(order).model_dump(),
        items=[OrderItemPublic.model_validate(item) for item in items],
        payment_status=payment.status if payment is not None else None,
        after_sale_id=after_sale.id if after_sale is not None else None,
        after_sale_status=after_sale.status if after_sale is not None else None,
    )
    return data.model_dump(mode="json")


def _payment_payload(payment: Payment) -> dict:
    return PaymentPublic.model_validate(payment).model_dump(mode="json")


# ---------- 商品 ----------


@router.post("/products", summary="上架商品（商户 / 企业，可带主图）")
def create_product(payload: ProductCreateRequest, db: DbSession, merchant: MerchantUser) -> dict:
    product = service.create_product(
        db,
        merchant,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        stock=payload.stock,
        image_file_id=payload.image_file_id,
    )
    return ok(ProductPublic.model_validate(product).model_dump(mode="json"), msg="上架成功")


@router.get("/merchant/products", summary="我的商品（商户 / 企业，含已下架，可按状态筛选）")
def list_my_products(
    db: DbSession,
    page: PageParams,
    viewer: OperatorUser,
    status: Annotated[
        str | None, Query(description="按状态筛选：on_sale（在售）/ off_shelf（已下架）")
    ] = None,
) -> dict:
    rows, total = service.list_my_products(db, viewer, page, status=status)
    counts = repository.favorite_counts(db, [row.id for row in rows])
    items = [
        MerchantProductPublic.model_validate(row)
        .model_copy(update={"favorite_count": counts.get(row.id, 0)})
        .model_dump(mode="json")
        for row in rows
    ]
    return ok(page_data(items, total, page))


@router.put("/products/{product_id}", summary="编辑商品（仅归属商户，部分更新）")
def update_product(
    product_id: int,
    payload: ProductUpdateRequest,
    db: DbSession,
    merchant: MerchantUser,
) -> dict:
    # exclude_unset：只应用请求里出现过的字段（未提交的保持不变；显式传 null 表示移除主图）
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise BadRequestError("没有需要更新的字段")
    product = service.update_product(db, merchant, product_id, changes=changes)
    return ok(ProductPublic.model_validate(product).model_dump(mode="json"), msg="已保存")


@router.post("/products/{product_id}/status", summary="上架 / 下架商品（归属商户）")
def set_product_status(
    product_id: int, payload: ProductStatusRequest, db: DbSession, merchant: OperatorUser
) -> dict:
    product = service.set_product_status(db, merchant, product_id, payload.status)
    msg = "已上架" if product.status == ProductStatus.ON_SALE else "已下架"
    return ok(ProductPublic.model_validate(product).model_dump(mode="json"), msg=msg)


@router.get("/products", summary="商品列表（公开；支持排序与价格区间）")
def list_products(
    db: DbSession,
    page: PageParams,
    keyword: Annotated[str | None, Query(max_length=64, description="按名称模糊搜索")] = None,
    merchant_id: Annotated[int | None, Query(description="按商户过滤")] = None,
    sort: Annotated[
        Literal["newest", "price_asc", "price_desc"] | None,
        Query(description="排序：newest（默认）/ price_asc / price_desc"),
    ] = None,
    min_price: Annotated[Decimal | None, Query(ge=0, description="最低价（含）")] = None,
    max_price: Annotated[Decimal | None, Query(ge=0, description="最高价（含）")] = None,
) -> dict:
    # 搜索热词统计放在缓存之外：命中缓存也要记一次（热词是"被搜过"的近似统计）
    hot_search.record(keyword)

    def _payload() -> dict:
        rows, total = service.list_products(
            db,
            page,
            keyword=keyword,
            merchant_id=merchant_id,
            sort=sort,
            min_price=min_price,
            max_price=max_price,
        )
        items = [ProductPublic.model_validate(row).model_dump(mode="json") for row in rows]
        return ok(page_data(items, total, page))

    # 热点：商品列表按（关键词 / 商户 / 排序 / 价格区间 / 页码）缓存（P1 承载能力）；
    # 上架新商品时 create_product 会 bump 版本立即失效。
    # ⚠️ 新增查询参数必须进缓存键，否则不同排序/价格区间会互相串结果。
    key_parts = (
        f"{keyword or '-'}:{merchant_id or '-'}:{sort or 'newest'}:"
        f"{min_price if min_price is not None else '-'}:"
        f"{max_price if max_price is not None else '-'}:"
        f"{page.page}:{page.page_size}"
    )
    return cache.cached("shop:products", key_parts, get_settings().cache_ttl_seconds, _payload)


@router.get("/hot-keywords", summary="搜索热词（公开；Redis 累计，未配置时返回空表）")
def hot_keywords(limit: Annotated[int, Query(ge=1, le=20, description="返回条数")] = 10) -> dict:
    rows = hot_search.top(limit)
    return ok({"items": [{"keyword": keyword, "count": count} for keyword, count in rows]})


@router.get("/products/{product_id}", summary="商品详情（公开；登录用户带收藏态并记一次浏览）")
def get_product(product_id: int, db: DbSession, viewer: OptionalUser) -> dict:
    product = service.get_product_detail(db, product_id)
    is_favorited, favorite_count = service.favorite_state(db, viewer, product_id)
    if viewer is not None:
        service.record_view(db, viewer, product_id)  # 浏览历史（写失败只记日志，不影响详情）
    payload = ProductDetailPublic.model_validate(product).model_copy(
        update={"is_favorited": is_favorited, "favorite_count": favorite_count}
    )
    return ok(payload.model_dump(mode="json"))


# ---------- 收藏 / 浏览历史 / 首页推荐（增强项）----------


@router.post("/favorites/{product_id}", summary="收藏商品（登录用户，幂等）")
def add_favorite(product_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    # 返回权威收藏数：前端直接赋值，不做本地 ±1（幂等命中时不会漂移）
    count = service.add_favorite(db, current_user, product_id)
    return ok(
        {"product_id": product_id, "is_favorited": True, "favorite_count": count}, msg="已收藏"
    )


@router.delete("/favorites/{product_id}", summary="取消收藏（登录用户，幂等）")
def remove_favorite(product_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    count = service.remove_favorite(db, current_user, product_id)
    return ok(
        {"product_id": product_id, "is_favorited": False, "favorite_count": count},
        msg="已取消收藏",
    )


@router.get("/favorites", summary="我的收藏（登录用户，最近收藏在前）")
def list_favorites(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_favorites(db, current_user, page)
    items = [ProductPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/history", summary="我的浏览历史（登录用户，最近浏览在前）")
def list_history(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_history(db, current_user, page)
    items = [ProductPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.delete("/history", summary="清空浏览历史（登录用户）")
def clear_history(db: DbSession, current_user: CurrentUser) -> dict:
    deleted = service.clear_history(db, current_user)
    return ok({"deleted": deleted}, msg="已清空浏览历史")


@router.get("/recommendations", summary="首页推荐（公开；登录用户按兴趣打分，游客按全站热度）")
def recommendations(
    db: DbSession,
    viewer: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=20, description="返回条数")] = 8,
) -> dict:
    products, basis = service.recommend_products(db, viewer, limit=limit)
    items = [ProductPublic.model_validate(row).model_dump(mode="json") for row in products]
    # basis 供前端定标题：personal = 为你推荐；popular = 大家都在看（游客 / 新用户兜底）
    return ok({"items": items, "basis": basis})


# ---------- 购物车 ----------


@router.get("/cart", summary="我的购物车")
def get_cart(db: DbSession, current_user: CurrentUser) -> dict:
    return ok(_cart_payload(db, current_user))


@router.post("/cart/items", summary="加入购物车（同商品合并数量）")
def add_cart_item(payload: CartItemAddRequest, db: DbSession, current_user: CurrentUser) -> dict:
    service.add_cart_item(
        db, current_user, product_id=payload.product_id, quantity=payload.quantity
    )
    return ok(_cart_payload(db, current_user), msg="已加入购物车")


@router.put("/cart/items/{item_id}", summary="修改购物车数量")
def update_cart_item(
    item_id: int, payload: CartItemUpdateRequest, db: DbSession, current_user: CurrentUser
) -> dict:
    service.update_cart_item(db, current_user, item_id=item_id, quantity=payload.quantity)
    return ok(_cart_payload(db, current_user), msg="已更新")


@router.delete("/cart/items/{item_id}", summary="移除购物车条目")
def remove_cart_item(item_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    service.remove_cart_item(db, current_user, item_id=item_id)
    return ok(_cart_payload(db, current_user), msg="已移除")


@router.post(
    "/cart/checkout",
    summary="购物车结算（同一商户，幂等）",
    dependencies=[Depends(rate_limit("order", by="user"))],
)
def checkout_cart(payload: CheckoutRequest, db: DbSession, current_user: CurrentUser) -> dict:
    order = service.checkout_cart(
        db,
        current_user,
        idem_key=payload.idem_key,
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        receiver_address=payload.receiver_address,
    )
    return ok(_order_detail_payload(db, order.id, current_user), msg="下单成功")


# ---------- 订单 ----------


@router.post(
    "/orders",
    summary="直接下单（单商品，幂等）",
    dependencies=[Depends(rate_limit("order", by="user"))],
)
def create_order(payload: OrderCreateRequest, db: DbSession, current_user: CurrentUser) -> dict:
    order = service.create_order(
        db,
        current_user,
        product_id=payload.product_id,
        quantity=payload.quantity,
        idem_key=payload.idem_key,
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        receiver_address=payload.receiver_address,
    )
    return ok(_order_detail_payload(db, order.id, current_user), msg="下单成功")


@router.get("/orders", summary="我的订单（分页）")
def list_my_orders(db: DbSession, page: PageParams, current_user: CurrentUser) -> dict:
    rows, total = service.list_my_orders(db, current_user, page)
    items = [OrderPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get(
    "/merchant/orders/export",
    summary="导出订单 CSV（商户 / 企业看自己；管理员看全部）",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": (
                "订单 CSV（UTF-8 带 BOM）；X-Export-Rows / X-Export-Truncated 标明行数与是否截断"
            ),
            "headers": {
                "X-Export-Rows": {
                    "description": "本次导出的数据行数（不含表头）",
                    "schema": {"type": "integer"},
                },
                "X-Export-Truncated": {
                    "description": "是否因超过 5 万行上限而截断（true/false）",
                    "schema": {"type": "string"},
                },
            },
        },
        400: {"description": "开始时间晚于结束时间，或时间超出支持范围（2000–2100）"},
    },
)
def export_orders(
    db: DbSession,
    operator: OperatorUser,
    status: Annotated[
        Literal["created", "paid", "shipped", "completed", "cancelled"] | None,
        Query(description="按状态过滤"),
    ] = None,
    start: Annotated[
        datetime | None,
        Query(description="创建时间起（ISO，含端点；naive 按 Asia/Shanghai 解释）"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(
            description=(
                "创建时间止（ISO，含端点；naive 按 Asia/Shanghai 解释）。"
                "纯日期等价于当天 00:00，要覆盖全天请传 23:59:59"
            )
        ),
    ] = None,
) -> StreamingResponse:
    rows, exported, truncated = service.export_orders(
        db, operator, status=status, start=start, end=end
    )
    filename = f"orders-{service.business_now().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        _csv_chunks(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Rows": str(exported),
            "X-Export-Truncated": "true" if truncated else "false",
        },
    )


def _csv_chunks(rows: Iterator[list[str]]) -> Iterator[str]:
    """逐块编码 CSV（BOM 仅首个块），避免把整表拼进内存。"""
    buffer = io.StringIO()
    # UTF-8 BOM：Excel 直接双击打开不乱码
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
        if buffer.tell() >= 8192:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
    if buffer.tell():
        yield buffer.getvalue()


@router.get("/merchant/sales-overview", summary="销量看板（近 N 天日趋势 + 热销 Top 5）")
def sales_overview(
    db: DbSession,
    operator: OperatorUser,
    days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = 14,
) -> dict:
    return ok(service.sales_overview(db, operator, days=days))


@router.get("/merchant/orders", summary="商家订单（商户 / 企业看自己；管理员看全部）")
def list_merchant_orders(db: DbSession, page: PageParams, viewer: OperatorUser) -> dict:
    rows, total = service.list_merchant_orders(db, viewer, page)
    items = [OrderPublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/orders/{order_id}", summary="订单详情（买家 / 商户 / 管理员）")
def get_order(order_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    return ok(_order_detail_payload(db, order_id, current_user))


@router.post("/orders/{order_id}/cancel", summary="取消订单（仅待支付，买家本人）")
def cancel_order(order_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    order = service.cancel_order(db, current_user, order_id)
    return ok(_order_detail_payload(db, order.id, current_user), msg="订单已取消，库存已回补")


# ---------- 履约：发货 / 签收 / 确认收货（N3） ----------


@router.post("/orders/{order_id}/ship", summary="发货（订单归属商户 / 管理员，运单号必填）")
def ship_order(order_id: int, payload: ShipRequest, db: DbSession, operator: OperatorUser) -> dict:
    order = service.ship_order(
        db, operator, order_id, carrier=payload.carrier, tracking_no=payload.tracking_no
    )
    return ok(_order_detail_payload(db, order.id, operator), msg="已发货")


@router.post(
    "/orders/{order_id}/deliver",
    summary="标记已签收（商户 / 管理员；签收后超期未确认将自动确认收货）",
)
def mark_delivered(order_id: int, db: DbSession, operator: OperatorUser) -> dict:
    order = service.mark_order_delivered(db, operator, order_id)
    return ok(_order_detail_payload(db, order.id, operator), msg="已标记签收")


@router.post("/orders/{order_id}/receive", summary="确认收货（买家本人，仅已发货）")
def receive_order(order_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    order = service.receive_order(db, current_user, order_id)
    return ok(_order_detail_payload(db, order.id, current_user), msg="已确认收货，交易完成")


# ---------- 支付（占位：平台不做资金池，接第三方） ----------


@router.post("/orders/{order_id}/pay", summary="创建支付单（占位）")
def create_payment(order_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    payment, pay_url = service.create_payment(db, current_user, order_id=order_id)
    payload = _payment_payload(payment)
    # 支付链接由网关决定：mock 为 None（仍走管理员模拟回调）；真实网关返回收银台链接 / 二维码
    payload["pay_url"] = pay_url
    return ok(payload, msg="支付单已创建")


@router.post("/payments/{payment_id}/callback", summary="模拟支付回调（仅管理员）")
def payment_callback(
    payment_id: int, payload: PaymentCallbackRequest, db: DbSession, admin: AdminUser
) -> dict:
    payment = service.handle_payment_callback(
        db,
        payment_id=payment_id,
        success=payload.success,
        trade_no=payload.trade_no,
        actor=admin,
    )
    return ok(_payment_payload(payment), msg="回调已处理")


@router.post("/payments/{payment_id}/refund", summary="登记异常支付已退款（仅管理员）")
def refund_payment(
    payment_id: int, payload: PaymentRefundRequest, db: DbSession, admin: AdminUser
) -> dict:
    """异常支付（订单取消 / 重复支付）线下退款完成后登记关闭，并通知买卖双方。"""
    payment = service.refund_payment(db, admin, payment_id, note=payload.note)
    return ok(_payment_payload(payment), msg="退款已登记")


# ---------- 售后（N4）：买家申请 → 商户受理 / 完成 / 拒绝；双方留言 ----------


@router.post(
    "/orders/{order_id}/after-sales",
    summary="申请售后（买家本人；已支付起，已完成订单须在有效期内）",
)
def apply_after_sale(
    order_id: int, payload: AfterSaleCreateRequest, db: DbSession, current_user: CurrentUser
) -> dict:
    sale = service.apply_after_sale(
        db,
        current_user,
        order_id=order_id,
        reason=payload.reason,
        description=payload.description,
    )
    return ok(AfterSalePublic.model_validate(sale).model_dump(mode="json"), msg="售后申请已提交")


@router.get("/after-sales", summary="售后列表（买家看自己 / 商户看参与的 / 管理员看全部）")
def list_after_sales(
    db: DbSession,
    page: PageParams,
    current_user: CurrentUser,
    status: Annotated[str | None, Query(description="按状态过滤")] = None,
) -> dict:
    rows, total = service.list_after_sales(db, current_user, page, status=status)
    items = [AfterSalePublic.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(page_data(items, total, page))


@router.get("/after-sales/{sale_id}", summary="售后详情（含留言流与订单摘要）")
def get_after_sale(sale_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    sale, messages, order = service.get_after_sale_detail(db, current_user, sale_id)
    data = AfterSaleDetail(
        **AfterSalePublic.model_validate(sale).model_dump(),
        messages=[AfterSaleMessagePublic.model_validate(item) for item in messages],
        order_amount=float(order.amount) if order is not None else None,
        order_status=order.status if order is not None else None,
    ).model_dump(mode="json")
    return ok(data)


@router.post("/after-sales/{sale_id}/messages", summary="售后留言（买家 / 商户 / 管理员）")
def post_after_sale_message(
    sale_id: int, payload: AfterSaleMessageRequest, db: DbSession, current_user: CurrentUser
) -> dict:
    message = service.post_after_sale_message(db, current_user, sale_id, content=payload.content)
    return ok(
        AfterSaleMessagePublic.model_validate(message).model_dump(mode="json"), msg="留言已发送"
    )


@router.post("/after-sales/{sale_id}/accept", summary="受理售后（商户 / 管理员）")
def accept_after_sale(sale_id: int, db: DbSession, operator: OperatorUser) -> dict:
    sale = service.accept_after_sale(db, operator, sale_id)
    return ok(
        AfterSalePublic.model_validate(sale).model_dump(mode="json"), msg="已受理，进入处理中"
    )


@router.post("/after-sales/{sale_id}/resolve", summary="完成售后（商户 / 管理员，可附说明）")
def resolve_after_sale(
    sale_id: int, payload: AfterSaleResolveRequest, db: DbSession, operator: OperatorUser
) -> dict:
    sale = service.resolve_after_sale(db, operator, sale_id, note=payload.note)
    return ok(AfterSalePublic.model_validate(sale).model_dump(mode="json"), msg="售后已完成")


@router.post("/after-sales/{sale_id}/reject", summary="拒绝售后（商户 / 管理员，理由必填）")
def reject_after_sale(
    sale_id: int, payload: AfterSaleRejectRequest, db: DbSession, operator: OperatorUser
) -> dict:
    sale = service.reject_after_sale(db, operator, sale_id, reason=payload.reason)
    return ok(AfterSalePublic.model_validate(sale).model_dump(mode="json"), msg="已拒绝")


@router.post("/after-sales/{sale_id}/withdraw", summary="撤销售后申请（买家本人，仅待处理）")
def withdraw_after_sale(sale_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    sale = service.withdraw_after_sale(db, current_user, sale_id)
    return ok(AfterSalePublic.model_validate(sale).model_dump(mode="json"), msg="申请已撤销")

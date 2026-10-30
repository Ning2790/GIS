"""shop 请求 / 响应模型（Pydantic）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreateRequest(BaseModel):
    """上架商品（商户 / 企业）。价格与库存设上界，避免写入时溢出成 500。"""

    name: str = Field(min_length=1, max_length=128, description="商品名称")
    description: str = Field(default="", max_length=2000, description="商品介绍")
    price: float = Field(gt=0, le=99_999_999.99, description="单价（元）")
    stock: int = Field(default=0, ge=0, le=1_000_000, description="库存")
    image_file_id: int | None = Field(
        default=None, gt=0, description="商品主图（先经 /files 上传为公开图片，取返回的 id）"
    )


class ProductUpdateRequest(BaseModel):
    """编辑商品（商户 / 企业，仅本人）。

    部分更新：只提交要改的字段（未提交的保持不变）；
    `image_file_id: null` 表示移除主图。上 / 下架走独立接口，不在这里改状态。
    """

    name: str | None = Field(default=None, min_length=1, max_length=128, description="商品名称")
    description: str | None = Field(default=None, max_length=2000, description="商品介绍")
    price: float | None = Field(default=None, gt=0, le=99_999_999.99, description="单价（元）")
    stock: int | None = Field(default=None, ge=0, le=1_000_000, description="库存")
    image_file_id: int | None = Field(
        default=None, gt=0, description="新的商品主图（null 表示移除主图）"
    )


class ProductPublic(BaseModel):
    """商品。image_url / image_thumbnail_url 由模型的 image_file_id 推导
    （平台受控图片地址；列表页用缩略图，详情页用原图）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: int
    name: str
    description: str
    price: float
    stock: int
    status: str
    image_url: str | None = None
    image_thumbnail_url: str | None = None
    created_at: datetime


class ProductDetailPublic(ProductPublic):
    """商品详情：额外带收藏态（登录用户）与全站收藏数（公开）。"""

    is_favorited: bool = False
    favorite_count: int = 0


class MerchantProductPublic(ProductPublic):
    """商户视角的商品：额外带收藏数（关注度，商户侧展示）。"""

    favorite_count: int = 0


class ReceiverInfo(BaseModel):
    """收货信息（下单必填；落库为订单快照，之后改个人中心地址不影响历史订单）。"""

    receiver_name: str = Field(min_length=1, max_length=32, description="收货人")
    receiver_phone: str = Field(pattern=r"^1[3-9]\d{9}$", description="收货手机号（11 位）")
    receiver_address: str = Field(
        min_length=5, max_length=255, description="收货地址（省 / 市 / 区 + 详细地址）"
    )


class OrderCreateRequest(ReceiverInfo):
    """直接下单（单商品）。"""

    product_id: int
    quantity: int = Field(ge=1, le=999, description="购买数量")
    idem_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=64,
        description="幂等键：重试 / 双击时传同一个值，只会生成一笔订单",
    )


class CheckoutRequest(ReceiverInfo):
    """购物车结算。"""

    idem_key: str | None = Field(
        default=None, min_length=8, max_length=64, description="幂等键（重试时传同一个值）"
    )


class ShipRequest(BaseModel):
    """发货（商户 / 管理员）：承运商 + 运单号必填（买家可据此查物流）。"""

    carrier: str = Field(min_length=1, max_length=32, description="承运商，如「顺丰」")
    tracking_no: str = Field(min_length=4, max_length=64, description="运单号")


class CartItemAddRequest(BaseModel):
    """加入购物车（同商品自动合并数量）。"""

    product_id: int
    quantity: int = Field(ge=1, le=999, description="数量")


class CartItemUpdateRequest(BaseModel):
    """修改购物车条目数量。"""

    quantity: int = Field(ge=1, le=999, description="数量")


class CartItemPublic(BaseModel):
    """购物车条目（含商品当前信息）。"""

    id: int
    product_id: int
    name: str
    price: float
    quantity: int
    amount: float
    stock: int
    available: bool


class CartPublic(BaseModel):
    """购物车。"""

    items: list[CartItemPublic] = []
    total_amount: float = 0.0


class OrderItemPublic(BaseModel):
    """订单项（下单时的商品快照）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    amount: float


class OrderPublic(BaseModel):
    """订单（列表项）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    merchant_id: int
    amount: float
    status: str
    # 支付截止时间（超时未支付由定时任务自动取消；历史订单可为空）
    expire_at: datetime | None = None
    # 取消原因：buyer（买家主动）/ expired（超时未支付自动取消）
    cancel_reason: str | None = None
    # 收货信息快照（历史订单可为空）
    receiver_name: str | None = None
    receiver_phone: str | None = None
    receiver_address: str | None = None
    # 履约信息（N3）：发货 / 签收 / 完成
    shipped_at: datetime | None = None
    carrier: str | None = None
    tracking_no: str | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    paid_at: datetime | None = None
    # 最新支付单的退款状态（none / pending / refunded）；列表用于“待退款”提示
    payment_refund_status: str | None = None
    # 最新支付单 id（列表页管理员登记退款用；详情页已有同名字段）
    payment_id: int | None = None


class OrderDetail(OrderPublic):
    """订单详情（含明细与最新支付单状态；payment_id 供管理员模拟回调）。"""

    items: list[OrderItemPublic] = []
    payment_status: str | None = None
    # 最近一条售后（N4）：前端据此展示入口 / 进度，避免额外请求
    after_sale_id: int | None = None
    after_sale_status: str | None = None


class ProductStatusRequest(BaseModel):
    """上架 / 下架商品。"""

    status: str = Field(description="on_sale（上架）或 off_shelf（下架）")


class PaymentPublic(BaseModel):
    """支付单。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    amount: float
    channel: str
    status: str
    trade_no: str | None = None
    created_at: datetime
    paid_at: datetime | None = None
    refund_status: str = "none"
    refund_note: str | None = None
    refunded_at: datetime | None = None


class PaymentCallbackRequest(BaseModel):
    """模拟支付回调（当前仅管理员可触发；接真实网关后改为网关验签回调）。"""

    success: bool
    trade_no: str | None = Field(default=None, max_length=64)


class PaymentRefundRequest(BaseModel):
    """异常支付退款登记（管理员线下退款后标记）。"""

    note: str | None = Field(default=None, max_length=255, description="退款说明 / 凭证号")


# ---------- 售后（N4） ----------


class AfterSaleCreateRequest(BaseModel):
    """买家申请售后：原因（预设类别）+ 问题说明（可选）。"""

    reason: str = Field(
        description="预设原因：quality（质量问题）/ missing（少发漏发）/ mismatch（与描述不符）"
        " / damaged（破损）/ other（其他）"
    )
    description: str | None = Field(default=None, max_length=300, description="问题说明（可选）")


class AfterSaleResolveRequest(BaseModel):
    """商户完成售后：可选的处理说明（会进留言流）。"""

    # 列宽 300；入库时前面会加「【已解决】」前缀，这里留出空间，避免长文本在 PG 上溢出
    note: str | None = Field(default=None, max_length=280, description="处理说明（可选，≤280 字）")


class AfterSaleRejectRequest(BaseModel):
    """商户拒绝售后：理由必填（会进留言流留痕）。"""

    # 同上：入库带「【拒绝】」前缀，留出空间
    reason: str = Field(min_length=1, max_length=280, description="拒绝理由（必填，≤280 字）")


class AfterSaleMessageRequest(BaseModel):
    """售后留言（买卖双方 / 管理员）。"""

    content: str = Field(min_length=1, max_length=300, description="留言内容（≤300 字）")


class AfterSaleMessagePublic(BaseModel):
    """售后留言条目。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    author_role: str  # buyer / merchant / admin
    content: str
    created_at: datetime


class AfterSalePublic(BaseModel):
    """售后单（列表项）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    user_id: int
    merchant_id: int
    reason: str
    description: str | None = None
    status: str  # pending / processing / resolved / rejected / withdrawn
    handler_id: int | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class AfterSaleDetail(AfterSalePublic):
    """售后详情：单据 + 留言流 + 关联订单摘要（金额 / 状态，供界面展示上下文）。"""

    messages: list[AfterSaleMessagePublic] = []
    order_amount: float | None = None
    order_status: str | None = None

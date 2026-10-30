/** shop 模块接口：商品浏览、购物车、下单与支付占位（登录用户）。 */

import { apiDelete, apiGet, apiPost, apiPut, downloadFileWithMeta } from './http';
import type {
  Cart,
  SalesOverview,
  HotKeyword,
  OrderDetail,
  OrderPublic,
  PageData,
  PaymentPublic,
  ProductDetail,
  ProductPublic,
  ReceiverPayload,
  RecommendationPage,
} from './types';

export type { HotKeyword };

export interface ProductListParams {
  keyword?: string;
  merchant_id?: number;
  /** 排序：newest（默认）/ price_asc / price_desc。 */
  sort?: 'newest' | 'price_asc' | 'price_desc';
  /** 价格区间（含端点）。 */
  min_price?: number;
  max_price?: number;
  page?: number;
  page_size?: number;
}

/** 生成幂等键（下单 / 结算用；重复提交同一键只会产生一个订单）。 */
export function newIdemKey(): string {
  return crypto.randomUUID();
}

/** 商品列表（公开，仅在售）。 */
export function listProducts(params: ProductListParams = {}): Promise<PageData<ProductPublic>> {
  const query = new URLSearchParams();
  if (params.keyword) {
    query.set('keyword', params.keyword);
  }
  if (params.merchant_id !== undefined) {
    query.set('merchant_id', String(params.merchant_id));
  }
  if (params.sort) {
    query.set('sort', params.sort);
  }
  if (params.min_price !== undefined) {
    query.set('min_price', String(params.min_price));
  }
  if (params.max_price !== undefined) {
    query.set('max_price', String(params.max_price));
  }
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.page_size ?? 12));
  return apiGet<PageData<ProductPublic>>(`/api/v1/shop/products?${query.toString()}`);
}

/** 商品详情（公开；登录用户额外带收藏态，并记一次浏览历史）。 */
export function getProductDetail(productId: number): Promise<ProductDetail> {
  return apiGet<ProductDetail>(`/api/v1/shop/products/${productId}`);
}

/** 收藏结果（favorite_count 为服务端权威计数，前端直接赋值）。 */
export interface FavoriteResult {
  product_id: number;
  is_favorited: boolean;
  favorite_count: number;
}

/** 收藏商品（登录用户，幂等）。 */
export function addFavorite(productId: number): Promise<FavoriteResult> {
  return apiPost<FavoriteResult>(`/api/v1/shop/favorites/${productId}`);
}

/** 取消收藏（登录用户，幂等）。 */
export function removeFavorite(productId: number): Promise<FavoriteResult> {
  return apiDelete<FavoriteResult>(`/api/v1/shop/favorites/${productId}`);
}

/** 我的收藏（登录用户，最近收藏在前）。 */
export function listFavorites(page = 1, pageSize = 12): Promise<PageData<ProductPublic>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiGet<PageData<ProductPublic>>(`/api/v1/shop/favorites?${query.toString()}`);
}

/** 我的浏览历史（登录用户，最近浏览在前；同一商品只出现一次）。 */
export function listHistory(page = 1, pageSize = 12): Promise<PageData<ProductPublic>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiGet<PageData<ProductPublic>>(`/api/v1/shop/history?${query.toString()}`);
}

/** 清空浏览历史（登录用户）。 */
export function clearHistory(): Promise<{ deleted: number }> {
  return apiDelete<{ deleted: number }>('/api/v1/shop/history');
}

/** 首页推荐（公开；登录用户按兴趣打分，游客 / 新用户按全站热度）。 */
export function listRecommendations(limit = 8): Promise<RecommendationPage> {
  return apiGet<RecommendationPage>(`/api/v1/shop/recommendations?limit=${limit}`);
}

/** 上架商品（商户 / 企业）。 */
export function createProduct(payload: {
  name: string;
  price: number;
  stock: number;
  description?: string;
  image_file_id?: number | null;
}): Promise<ProductPublic> {
  return apiPost<ProductPublic>('/api/v1/shop/products', payload);
}

/** 编辑商品（仅归属商户；部分更新，未提交的字段保持不变；image_file_id=null 移除主图）。 */
export function updateProduct(
  productId: number,
  payload: {
    name?: string;
    description?: string;
    price?: number;
    stock?: number;
    image_file_id?: number | null;
  },
): Promise<ProductPublic> {
  return apiPut<ProductPublic>(`/api/v1/shop/products/${productId}`, payload);
}

/** 我的商品列表（商户 / 企业，含已下架；管理端用；可按状态筛选）。 */
export function listMyProducts(
  page = 1,
  pageSize = 10,
  status?: 'on_sale' | 'off_shelf',
): Promise<PageData<ProductPublic>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) {
    query.set('status', status);
  }
  return apiGet<PageData<ProductPublic>>(`/api/v1/shop/merchant/products?${query.toString()}`);
}

/** 上架 / 下架商品（归属商户本人；下架后公开列表不可见）。 */
export function setProductStatus(
  productId: number,
  status: 'on_sale' | 'off_shelf',
): Promise<ProductPublic> {
  return apiPost<ProductPublic>(`/api/v1/shop/products/${productId}/status`, { status });
}

/** 我的购物车。 */
export function getCart(): Promise<Cart> {
  return apiGet<Cart>('/api/v1/shop/cart');
}

/** 加入购物车（同商品合并数量），返回最新购物车。 */
export function addCartItem(productId: number, quantity: number): Promise<Cart> {
  return apiPost<Cart>('/api/v1/shop/cart/items', { product_id: productId, quantity });
}

/** 修改购物车条目数量，返回最新购物车。 */
export function updateCartItem(itemId: number, quantity: number): Promise<Cart> {
  return apiPut<Cart>(`/api/v1/shop/cart/items/${itemId}`, { quantity });
}

/** 移除购物车条目，返回最新购物车。 */
export function removeCartItem(itemId: number): Promise<Cart> {
  return apiDelete<Cart>(`/api/v1/shop/cart/items/${itemId}`);
}

/** 购物车结算（同一商户；幂等键防重复下单；收货信息随订单快照落库）。 */
export function checkoutCart(idemKey: string, receiver: ReceiverPayload): Promise<OrderDetail> {
  return apiPost<OrderDetail>('/api/v1/shop/cart/checkout', {
    idem_key: idemKey,
    ...receiver,
  });
}

/** 直接购买（单商品；幂等键防重复下单；收货信息随订单快照落库）。 */
export function createOrder(
  productId: number,
  quantity: number,
  idemKey: string,
  receiver: ReceiverPayload,
): Promise<OrderDetail> {
  return apiPost<OrderDetail>('/api/v1/shop/orders', {
    product_id: productId,
    quantity,
    idem_key: idemKey,
    ...receiver,
  });
}

/** 发货（订单归属商户 / 管理员；承运商与运单号必填）。 */
export function shipOrder(
  orderId: number,
  carrier: string,
  trackingNo: string,
): Promise<OrderDetail> {
  return apiPost<OrderDetail>(`/api/v1/shop/orders/${orderId}/ship`, {
    carrier,
    tracking_no: trackingNo,
  });
}

/** 标记已签收（商户 / 管理员）：签收后超期未确认将自动确认收货。 */
export function deliverOrder(orderId: number): Promise<OrderDetail> {
  return apiPost<OrderDetail>(`/api/v1/shop/orders/${orderId}/deliver`);
}

/** 确认收货（买家本人，仅已发货）。 */
export function receiveOrder(orderId: number): Promise<OrderDetail> {
  return apiPost<OrderDetail>(`/api/v1/shop/orders/${orderId}/receive`);
}

/** 我的订单（分页）。 */
export function listMyOrders(page = 1, pageSize = 10): Promise<PageData<OrderPublic>> {
  return apiGet<PageData<OrderPublic>>(
    `/api/v1/shop/orders?page=${page}&page_size=${pageSize}`,
  );
}

/** 商家订单列表（商户 / 企业，分页）。 */
export function listMerchantOrders(page = 1, pageSize = 10): Promise<PageData<OrderPublic>> {
  return apiGet<PageData<OrderPublic>>(
    `/api/v1/shop/merchant/orders?page=${page}&page_size=${pageSize}`,
  );
}

/** 订单详情。 */
export function getOrderDetail(orderId: number): Promise<OrderDetail> {
  return apiGet<OrderDetail>(`/api/v1/shop/orders/${orderId}`);
}

/** 取消订单（仅待支付，买家本人；库存随取消回补）。 */
export function cancelOrder(orderId: number): Promise<OrderDetail> {
  return apiPost<OrderDetail>(`/api/v1/shop/orders/${orderId}/cancel`);
}

/** 创建支付单（占位；同一订单已有未处理支付单时复用）。 */
export function createPayment(orderId: number): Promise<PaymentPublic> {
  return apiPost<PaymentPublic>(`/api/v1/shop/orders/${orderId}/pay`);
}

/** 模拟支付回调（仅管理员；接真实网关后改为网关验签回调）。 */
export function paymentCallback(
  paymentId: number,
  success: boolean,
  tradeNo?: string,
): Promise<PaymentPublic> {
  return apiPost<PaymentPublic>(`/api/v1/shop/payments/${paymentId}/callback`, {
    success,
    trade_no: tradeNo ?? null,
  });
}

/** 登记异常支付已退款（仅管理员；线下退款完成后调用）。 */
export function refundPayment(paymentId: number, note?: string): Promise<PaymentPublic> {
  return apiPost<PaymentPublic>(`/api/v1/shop/payments/${paymentId}/refund`, {
    note: note ?? null,
  });
}

/** 搜索热词（公开；Redis 累计，未配置时返回空表）。 */
export function listHotKeywords(limit = 10): Promise<HotKeyword[]> {
  return apiGet<{ items: HotKeyword[] }>(`/api/v1/shop/hot-keywords?limit=${limit}`).then(
    (data) => data.items,
  );
}

/** 导出订单 CSV（商户看自己 / 管理员看全平台）：按状态与时间范围过滤。 */
/** 订单 CSV 导出结果：文件本体 + 服务端行数 / 截断标记（X-Export-*）。 */
export interface ExportedOrdersCsv {
  blob: Blob;
  /** 本次导出的数据行数（不含表头）；服务端未返回时为 null。 */
  rows: number | null;
  /** 是否因超过 5 万行上限被截断（导出的是最新订单）。 */
  truncated: boolean;
}

export async function exportOrdersCsv(params: {
  status?: string;
  start?: string;
  end?: string;
} = {}): Promise<ExportedOrdersCsv> {
  const query = new URLSearchParams();
  if (params.status) {
    query.set('status', params.status);
  }
  if (params.start) {
    query.set('start', params.start);
  }
  if (params.end) {
    query.set('end', params.end);
  }
  const suffix = query.toString();
  const { blob, headers } = await downloadFileWithMeta(
    `/api/v1/shop/merchant/orders/export${suffix ? `?${suffix}` : ''}`,
  );
  const rows = Number(headers.get('X-Export-Rows'));
  return {
    blob,
    rows: Number.isFinite(rows) ? rows : null,
    truncated: headers.get('X-Export-Truncated') === 'true',
  };
}

/** 销量看板（近 N 天日趋势 + 热销 Top 5）。 */
export function getSalesOverview(days = 14): Promise<SalesOverview> {
  return apiGet<SalesOverview>(`/api/v1/shop/merchant/sales-overview?days=${days}`);
}

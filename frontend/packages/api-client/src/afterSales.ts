/** 售后单（需求 2.3 售后 / 4.4 客服并行入口）。
 *
 * 平台不做资金池：售后单只跟踪原因、状态与双方留言，退款 / 换货由商户线下或经第三方处理。
 */

import { apiGet, apiPost } from './http';
import type { AfterSaleDetail, AfterSaleMessagePublic, AfterSalePublic, PageData } from './types';

/** 申请售后（买家本人；已支付起可申请，已完成订单须在有效期内）。 */
export function applyAfterSale(
  orderId: number,
  reason: string,
  description?: string,
): Promise<AfterSalePublic> {
  return apiPost<AfterSalePublic>(`/api/v1/shop/orders/${orderId}/after-sales`, {
    reason,
    description,
  });
}

/** 售后列表（买家看自己 / 商户看参与的 / 管理员看全部）。 */
export function listAfterSales(
  page = 1,
  pageSize = 10,
  status?: string,
): Promise<PageData<AfterSalePublic>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) {
    query.set('status', status);
  }
  return apiGet<PageData<AfterSalePublic>>(`/api/v1/shop/after-sales?${query.toString()}`);
}

/** 售后详情（含留言流与订单摘要）。 */
export function getAfterSale(saleId: number): Promise<AfterSaleDetail> {
  return apiGet<AfterSaleDetail>(`/api/v1/shop/after-sales/${saleId}`);
}

/** 售后留言。 */
export function postAfterSaleMessage(
  saleId: number,
  content: string,
): Promise<AfterSaleMessagePublic> {
  return apiPost<AfterSaleMessagePublic>(`/api/v1/shop/after-sales/${saleId}/messages`, {
    content,
  });
}

/** 受理售后（商户 / 管理员）：待处理 → 处理中。 */
export function acceptAfterSale(saleId: number): Promise<AfterSalePublic> {
  return apiPost<AfterSalePublic>(`/api/v1/shop/after-sales/${saleId}/accept`);
}

/** 完成售后（商户 / 管理员）：处理中 → 已解决；可附处理说明（进留言流）。 */
export function resolveAfterSale(saleId: number, note?: string): Promise<AfterSalePublic> {
  return apiPost<AfterSalePublic>(`/api/v1/shop/after-sales/${saleId}/resolve`, { note });
}

/** 拒绝售后（商户 / 管理员）：理由必填（进留言流）。 */
export function rejectAfterSale(saleId: number, reason: string): Promise<AfterSalePublic> {
  return apiPost<AfterSalePublic>(`/api/v1/shop/after-sales/${saleId}/reject`, { reason });
}

/** 撤销售后申请（买家本人，仅受理前）。 */
export function withdrawAfterSale(saleId: number): Promise<AfterSalePublic> {
  return apiPost<AfterSalePublic>(`/api/v1/shop/after-sales/${saleId}/withdraw`);
}

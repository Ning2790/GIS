/** b2b 模块接口：供需信息（公开浏览 + 商户发布 / 匹配）。 */

import { apiGet, apiPost } from './http';
import type { B2bMatchResult, B2bPostPublic, PageData } from './types';

export interface B2bListParams {
  category?: string;
  region?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface B2bCreatePayload {
  title: string;
  category: string;
  region: string;
  quantity: number;
  unit?: string;
  price_expect?: number | null;
  description?: string;
}

function buildQuery(params: B2bListParams): string {
  const query = new URLSearchParams();
  if (params.category) {
    query.set('category', params.category);
  }
  if (params.region) {
    query.set('region', params.region);
  }
  if (params.keyword) {
    query.set('keyword', params.keyword);
  }
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.page_size ?? 10));
  return query.toString();
}

/** 供给列表（公开，仅开放中）。 */
export function listSupplies(params: B2bListParams = {}): Promise<PageData<B2bPostPublic>> {
  return apiGet<PageData<B2bPostPublic>>(`/api/v1/b2b/supplies?${buildQuery(params)}`);
}

/** 需求列表（公开，仅开放中）。 */
export function listDemands(params: B2bListParams = {}): Promise<PageData<B2bPostPublic>> {
  return apiGet<PageData<B2bPostPublic>>(`/api/v1/b2b/demands?${buildQuery(params)}`);
}

/** 发布供给信息（商户 / 企业）。 */
export function createSupply(payload: B2bCreatePayload): Promise<B2bPostPublic> {
  return apiPost<B2bPostPublic>('/api/v1/b2b/supplies', payload);
}

/** 发布需求信息（商户 / 企业）。 */
export function createDemand(payload: B2bCreatePayload): Promise<B2bPostPublic> {
  return apiPost<B2bPostPublic>('/api/v1/b2b/demands', payload);
}

/** 关闭供给信息（发布者）。 */
export function closeSupply(supplyId: number): Promise<B2bPostPublic> {
  return apiPost<B2bPostPublic>(`/api/v1/b2b/supplies/${supplyId}/close`);
}

/** 关闭需求信息（发布者）。 */
export function closeDemand(demandId: number): Promise<B2bPostPublic> {
  return apiPost<B2bPostPublic>(`/api/v1/b2b/demands/${demandId}/close`);
}

/** 对需求发起规则匹配（全量替换并返回匹配结果）。 */
export function matchDemand(demandId: number): Promise<B2bMatchResult> {
  return apiPost<B2bMatchResult>(`/api/v1/b2b/demands/${demandId}/match`);
}

/** 查看某需求已有的匹配记录。 */
export function listDemandMatches(demandId: number): Promise<B2bMatchResult> {
  return apiGet<B2bMatchResult>(`/api/v1/b2b/demands/${demandId}/matches`);
}

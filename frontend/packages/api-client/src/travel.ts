/** travel 模块接口：景点列表与详情（公开）、行程规划（登录用户）。 */

import { apiDelete, apiGet, apiPost, apiPut } from './http';
import type {
  AttractionDetail,
  AttractionPublic,
  ItineraryDetail,
  ItineraryPublic,
  PageData,
  RouteDetail,
  RoutePublic,
} from './types';

export interface AttractionListParams {
  /** 按城市过滤（如「西宁市」） */
  city?: string;
  /** 名称 / 城市关键词 */
  keyword?: string;
  /** 距离排序：lng,lat（给出坐标时返回 distance_km 并按距离升序） */
  near?: string;
  page?: number;
  page_size?: number;
}

/** 景点列表（分页；支持城市 / 关键词筛选与 near 距离排序）。 */
export function listAttractions(params: AttractionListParams = {}): Promise<PageData<AttractionPublic>> {
  const query = new URLSearchParams();
  if (params.city) query.set('city', params.city);
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.near) query.set('near', params.near);
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.page_size ?? 12));
  return apiGet<PageData<AttractionPublic>>(`/api/v1/travel/attractions?${query.toString()}`);
}

/** 景点详情（含票种）。 */
export function getAttractionDetail(id: number): Promise<AttractionDetail> {
  return apiGet<AttractionDetail>(`/api/v1/travel/attractions/${id}`);
}

/** 预设路线列表（公开，分页；可按主题过滤）。 */
export function listRoutes(
  params: { theme?: string; page?: number; page_size?: number } = {},
): Promise<PageData<RoutePublic>> {
  const query = new URLSearchParams();
  if (params.theme) query.set('theme', params.theme);
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.page_size ?? 10));
  return apiGet<PageData<RoutePublic>>(`/api/v1/travel/routes?${query.toString()}`);
}

/** 预设路线详情（含停靠点；公开）。 */
export function getRouteDetail(id: number): Promise<RouteDetail> {
  return apiGet<RouteDetail>(`/api/v1/travel/routes/${id}`);
}

/** 路线维护载荷（运营后台；stops 数组顺序决定同日内的先后）。 */
export interface RouteSavePayload {
  name: string;
  theme?: string;
  days: number;
  budget?: number | null;
  description?: string;
  stops: { attraction_id: number; day: number; note?: string | null }[];
}

/** 新建预设路线（管理员 / 运营）。 */
export function createRoute(payload: RouteSavePayload): Promise<RouteDetail> {
  return apiPost<RouteDetail>('/api/v1/travel/routes', payload);
}

/** 更新预设路线（全量，含停靠点；管理员）。 */
export function updateRoute(routeId: number, payload: RouteSavePayload): Promise<RouteDetail> {
  return apiPut<RouteDetail>(`/api/v1/travel/routes/${routeId}`, payload);
}

/** 删除预设路线（管理员）。 */
export function deleteRoute(routeId: number): Promise<null> {
  return apiDelete<null>(`/api/v1/travel/routes/${routeId}`);
}

/** 套用预设路线为我的行程（登录用户；返回新行程详情）。 */
export function applyRoute(id: number): Promise<ItineraryDetail> {
  return apiPost<ItineraryDetail>(`/api/v1/travel/routes/${id}/apply`);
}

/** 生成个性化行程（AI；返回含停靠点的详情）。 */
export function generateItinerary(payload: {
  days: number;
  budget?: number | null;
  preferences?: string;
  fitness?: string;
}): Promise<ItineraryDetail> {
  return apiPost<ItineraryDetail>('/api/v1/travel/itineraries', payload);
}

/** 我的行程列表（分页）。 */
export function listMyItineraries(page = 1, pageSize = 10): Promise<PageData<ItineraryPublic>> {
  return apiGet<PageData<ItineraryPublic>>(
    `/api/v1/travel/itineraries?page=${page}&page_size=${pageSize}`,
  );
}

/** 行程详情（含停靠点与景点名）。 */
export function getItineraryDetail(id: number): Promise<ItineraryDetail> {
  return apiGet<ItineraryDetail>(`/api/v1/travel/itineraries/${id}`);
}

/** 全量替换停靠点（一次完成增 / 删 / 排序）。 */
export function replaceItineraryStops(
  id: number,
  stops: { attraction_id: number; day: number; note?: string | null }[],
): Promise<ItineraryDetail> {
  return apiPut<ItineraryDetail>(`/api/v1/travel/itineraries/${id}/stops`, { stops });
}

/** 删除行程。 */
export function deleteItinerary(id: number): Promise<null> {
  return apiDelete<null>(`/api/v1/travel/itineraries/${id}`);
}

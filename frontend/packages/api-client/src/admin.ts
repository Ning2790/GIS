/** admin 模块接口：资质审核 / 用户管理 / 审计日志 / 用户列表（管理员）。 */

import { apiGet, apiPost } from './http';
import type { AuditLogPublic, PageData, UserAdminPublic } from './types';

/** 待审核商户 / 企业列表（分页）。 */
export function listPendingReviews(page = 1, pageSize = 10): Promise<PageData<UserAdminPublic>> {
  return apiGet<PageData<UserAdminPublic>>(
    `/api/v1/admin/reviews?page=${page}&page_size=${pageSize}`,
  );
}

/** 审核通过（通过后即可登录）。 */
export function approveReview(userId: number): Promise<UserAdminPublic> {
  return apiPost<UserAdminPublic>(`/api/v1/admin/reviews/${userId}/approve`);
}

/** 审核驳回（驳回后不可登录）。 */
export function rejectReview(userId: number): Promise<UserAdminPublic> {
  return apiPost<UserAdminPublic>(`/api/v1/admin/reviews/${userId}/reject`);
}

/** 用户列表（分页，可按角色 / 状态 / 关键词过滤）。 */
export function listUsers(params: {
  role?: string;
  status?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<PageData<UserAdminPublic>> {
  const query = new URLSearchParams();
  if (params.role) {
    query.set('role', params.role);
  }
  if (params.status) {
    query.set('status', params.status);
  }
  if (params.keyword) {
    query.set('keyword', params.keyword);
  }
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.page_size ?? 10));
  return apiGet<PageData<UserAdminPublic>>(`/api/v1/users?${query.toString()}`);
}

/** 禁用账号。 */
export function disableUser(userId: number): Promise<UserAdminPublic> {
  return apiPost<UserAdminPublic>(`/api/v1/admin/users/${userId}/disable`);
}

/** 解除禁用。 */
export function enableUser(userId: number): Promise<UserAdminPublic> {
  return apiPost<UserAdminPublic>(`/api/v1/admin/users/${userId}/enable`);
}

/** 审计日志（分页，可按动作 / 目标类型 / 目标 id 过滤）。 */
export function listAuditLogs(params: {
  action?: string;
  target_type?: string;
  target_id?: number;
  page?: number;
  page_size?: number;
} = {}): Promise<PageData<AuditLogPublic>> {
  const query = new URLSearchParams();
  if (params.action) {
    query.set('action', params.action);
  }
  if (params.target_type) {
    query.set('target_type', params.target_type);
  }
  if (params.target_id !== undefined) {
    query.set('target_id', String(params.target_id));
  }
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.page_size ?? 20));
  return apiGet<PageData<AuditLogPublic>>(`/api/v1/admin/audit-logs?${query.toString()}`);
}

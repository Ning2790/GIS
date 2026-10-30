/** notifications 模块接口：站内通知列表、未读数与已读标记（登录用户）。 */

import { apiGet, apiPost } from './http';
import type { NotificationPublic, PageData } from './types';

/** 我的通知（最新在前）。 */
export function listNotifications(
  page = 1,
  pageSize = 20,
): Promise<PageData<NotificationPublic>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiGet<PageData<NotificationPublic>>(`/api/v1/notifications?${query.toString()}`);
}

/** 未读通知数（顶栏铃铛角标）。 */
export function getUnreadNotificationCount(): Promise<{ unread: number }> {
  return apiGet<{ unread: number }>('/api/v1/notifications/unread-count');
}

/** 标记单条已读（幂等；仅本人，他人的按不存在处理）。 */
export function markNotificationRead(notificationId: number): Promise<NotificationPublic> {
  return apiPost<NotificationPublic>(`/api/v1/notifications/${notificationId}/read`);
}

/** 全部标记已读，返回本次更新条数。 */
export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return apiPost<{ updated: number }>('/api/v1/notifications/read-all');
}

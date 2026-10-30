/** cs 模块接口：在线客服（AI 接待 / 转人工）。 */

import { apiGet, apiPost } from './http';
import type { CsMessagePublic, CsSendResult, CsSessionPublic, PageData } from './types';

/** 发起客服会话（AI 接待）。 */
export function createCsSession(): Promise<CsSessionPublic> {
  return apiPost<CsSessionPublic>('/api/v1/cs/sessions');
}

/** 我的客服会话列表（分页）。 */
export function listMyCsSessions(page = 1, pageSize = 20): Promise<PageData<CsSessionPublic>> {
  return apiGet<PageData<CsSessionPublic>>(`/api/v1/cs/sessions?page=${page}&page_size=${pageSize}`);
}

/** 会话消息（按时间正序）。 */
export function listCsMessages(
  sessionId: number,
  page = 1,
  pageSize = 100,
): Promise<PageData<CsMessagePublic>> {
  return apiGet<PageData<CsMessagePublic>>(
    `/api/v1/cs/sessions/${sessionId}/messages?page=${page}&page_size=${pageSize}`,
  );
}

/** 人工客服队列（商户 / 企业）。 */
export function listCsQueue(page = 1, pageSize = 20): Promise<PageData<CsSessionPublic>> {
  return apiGet<PageData<CsSessionPublic>>(`/api/v1/cs/queue?page=${page}&page_size=${pageSize}`);
}

/** 人工客服接入会话（claim）。 */
export function claimCsSession(sessionId: number): Promise<CsSessionPublic> {
  return apiPost<CsSessionPublic>(`/api/v1/cs/sessions/${sessionId}/claim`);
}

/** 客服释放会话（回到人工队列）。 */
export function releaseCsSession(sessionId: number): Promise<CsSessionPublic> {
  return apiPost<CsSessionPublic>(`/api/v1/cs/sessions/${sessionId}/release`);
}

/** 发送消息（AI 接待时返回同步应答 reply）。 */
export function sendCsMessage(sessionId: number, content: string): Promise<CsSendResult> {
  return apiPost<CsSendResult>(`/api/v1/cs/sessions/${sessionId}/messages`, { content });
}

/** 转人工客服（进入人工队列）。 */
export function transferCsSession(sessionId: number): Promise<CsSessionPublic> {
  return apiPost<CsSessionPublic>(`/api/v1/cs/sessions/${sessionId}/transfer`);
}

/** 结束会话。 */
export function closeCsSession(sessionId: number): Promise<CsSessionPublic> {
  return apiPost<CsSessionPublic>(`/api/v1/cs/sessions/${sessionId}/close`);
}

/** ai 模块接口：会话列表 / 详情 + SSE 流式提问。 */

import { ApiError, apiDelete, apiGet, apiPatch, getBaseUrl, getToken, tryRefresh } from './http';
import type {
  AiConversationDetail,
  AiConversationPublic,
  KnowledgeSource,
  PageData,
} from './types';

/** 我的会话列表（分页，按最近更新排序）。 */
export function listConversations(page = 1, pageSize = 20): Promise<PageData<AiConversationPublic>> {
  return apiGet<PageData<AiConversationPublic>>(
    `/api/v1/ai/conversations?page=${page}&page_size=${pageSize}`,
  );
}

/** 会话详情（含全部消息）。 */
export function getConversationDetail(conversationId: number): Promise<AiConversationDetail> {
  return apiGet<AiConversationDetail>(`/api/v1/ai/conversations/${conversationId}`);
}

export interface AskStreamHandlers {
  /** 服务端分配会话 id（新会话首问时下发）。 */
  onConversation?: (conversationId: number) => void;
  /** 流式增量文本。 */
  onDelta: (text: string) => void;
  /** 参考来源（联网搜索触发时下发）。 */
  onSources?: (sources: string[]) => void;
  /** 知识库命中来源（N12 向量检索；前端「参考来源」卡片用）。 */
  onKnowledgeSources?: (sources: KnowledgeSource[]) => void;
}

/**
 * SSE 流式提问（POST + fetch 读流，EventSource 不支持带体/带鉴权的 POST）。
 * 401 时尝试刷新令牌并重放一次；非流式错误（401/429/422）按统一信封抛 ApiError。
 */
export async function askStream(
  question: string,
  conversationId: number | null,
  handlers: AskStreamHandlers,
  retried = false,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const resp = await fetch(`${getBaseUrl()}/api/v1/ai/ask/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ question, conversation_id: conversationId }),
  });

  if (!resp.ok || !resp.body) {
    let code: number | undefined;
    let msg: string | undefined;
    try {
      const payload = (await resp.json()) as { code?: number; msg?: string };
      code = payload.code;
      msg = payload.msg;
    } catch {
      /* 非 JSON 响应：走通用错误 */
    }
    if (code === 40100 && !retried && (await tryRefresh())) {
      return askStream(question, conversationId, handlers, true);
    }
    throw new ApiError(code ?? -1, msg ?? `服务异常（HTTP ${resp.status}）`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf('\n\n');
    while (index >= 0) {
      const block = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      for (const line of block.split('\n')) {
        if (!line.startsWith('data: ')) {
          continue;
        }
        const data = line.slice(6);
        if (data === '[DONE]') {
          continue;
        }
        try {
          const event = JSON.parse(data) as {
            conversation_id?: number;
            delta?: string;
            sources?: string[];
            knowledge_sources?: KnowledgeSource[];
          };
          if (event.conversation_id !== undefined) {
            handlers.onConversation?.(event.conversation_id);
          }
          if (event.delta !== undefined) {
            handlers.onDelta(event.delta);
          }
          if (event.sources !== undefined) {
            handlers.onSources?.(event.sources);
          }
          if (event.knowledge_sources !== undefined) {
            handlers.onKnowledgeSources?.(event.knowledge_sources);
          }
        } catch {
          /* 忽略无法解析的事件块 */
        }
      }
      index = buffer.indexOf('\n\n');
    }
  }
}

/** 重命名会话（仅本人）。 */
export function renameConversation(
  conversationId: number,
  title: string,
): Promise<AiConversationPublic> {
  return apiPatch<AiConversationPublic>(`/api/v1/ai/conversations/${conversationId}`, { title });
}

/** 删除会话（仅本人，连同消息）。 */
export function deleteConversation(conversationId: number): Promise<{ deleted_messages: number }> {
  return apiDelete<{ deleted_messages: number }>(`/api/v1/ai/conversations/${conversationId}`);
}

/** http 层单元测试：响应信封、错误映射、401 自动刷新重放（并发单飞）、FormData 上传。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  apiGet,
  apiPost,
  clearTokens,
  downloadFile,
  getRefreshToken,
  getToken,
  hasSession,
  requestForm,
  setTokens,
} from './http';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: JSON_HEADERS,
  });
}

describe('http 基础行为', () => {
  beforeEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    clearTokens();
  });

  it('成功响应：解包 data 并附带 Authorization 头', async () => {
    setTokens('access-1', 'refresh-1');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ code: 0, msg: 'ok', data: { id: 7 } }));

    const data = await apiGet<{ id: number }>('/api/v1/demo');

    expect(data).toEqual({ id: 7 });
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer access-1');
  });

  it('无令牌时不带 Authorization 头', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ code: 0, msg: 'ok', data: null }));

    await apiGet('/api/v1/demo');

    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('非 0 code 抛 ApiError（携带 code 与可展示 message）', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ code: 40900, msg: '库存不足', data: null }, 409),
    );

    await expect(apiPost('/api/v1/shop/orders', {})).rejects.toMatchObject({
      code: 40900,
      message: '库存不足',
    });
  });

  it('非 JSON 响应抛 ApiError(-1)（不把 500 当成功）', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>bad gateway</html>', { status: 502 }),
    );

    const error = await apiGet('/api/v1/demo').catch((err: unknown) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe(-1);
  });
});

describe('401 自动刷新重放', () => {
  beforeEach(() => {
    clearTokens();
    vi.restoreAllMocks();
    setTokens('expired-access', 'refresh-1');
  });

  afterEach(() => {
    clearTokens();
  });

  it('401 → 刷新成功后重放原请求并返回数据', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        return jsonResponse({
          code: 0,
          msg: 'ok',
          data: { access_token: 'access-2', refresh_token: 'refresh-2', refresh_expires_in: 100 },
        });
      }
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
      if (auth === 'Bearer access-2') {
        return jsonResponse({ code: 0, msg: 'ok', data: { ok: true } });
      }
      return jsonResponse({ code: 40100, msg: '登录已过期', data: null }, 401);
    });

    const data = await apiGet<{ ok: boolean }>('/api/v1/shop/cart');

    expect(data).toEqual({ ok: true });
    expect(getToken()).toBe('access-2');
    expect(getRefreshToken()).toBe('refresh-2');
    // 三次调用：原请求（401）→ 刷新 → 重放（200）
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('刷新请求携带设备标识，普通请求带 X-Device-Id 头（需求 4.2 设备绑定）', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        const body = JSON.parse(String(init?.body ?? '{}')) as {
          refresh_token?: string;
          device_id?: string;
        };
        // 后端要求：会话绑定过设备时，刷新必须带同一设备标识，否则 401
        expect(body.refresh_token).toBe('refresh-1');
        expect(body.device_id).toBeTruthy();
        return jsonResponse({
          code: 0,
          msg: 'ok',
          data: { access_token: 'access-2', refresh_token: 'refresh-2', refresh_expires_in: 100 },
        });
      }
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
      return auth === 'Bearer access-2'
        ? jsonResponse({ code: 0, msg: 'ok', data: { ok: true } })
        : jsonResponse({ code: 40100, msg: '登录已过期', data: null }, 401);
    });

    await apiGet<{ ok: boolean }>('/api/v1/shop/cart');

    const firstHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(firstHeaders['X-Device-Id']).toBeTruthy();
  });

  it('并发 401 只触发一次刷新（单飞）', async () => {
    let refreshCalls = 0;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        refreshCalls += 1;
        return jsonResponse({
          code: 0,
          msg: 'ok',
          data: { access_token: 'access-2', refresh_token: 'refresh-2', refresh_expires_in: 100 },
        });
      }
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
      if (auth === 'Bearer access-2') {
        return jsonResponse({ code: 0, msg: 'ok', data: { ok: true } });
      }
      return jsonResponse({ code: 40100, msg: '登录已过期', data: null }, 401);
    });

    const [a, b] = await Promise.all([
      apiGet<{ ok: boolean }>('/api/v1/a'),
      apiGet<{ ok: boolean }>('/api/v1/b'),
    ]);

    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
    expect(refreshCalls).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(5); // 2 原请求 + 1 刷新 + 2 重放
  });

  it('刷新失败：清空令牌并抛出原错误', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        return jsonResponse({ code: 40100, msg: '登录已失效，请重新登录', data: null }, 401);
      }
      return jsonResponse({ code: 40100, msg: '登录已过期', data: null }, 401);
    });

    await expect(apiGet('/api/v1/shop/cart')).rejects.toMatchObject({ code: 40100 });
    expect(hasSession()).toBe(false);
  });

  it('/auth/* 路径的 401 不触发刷新（避免刷新-重放循环）', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ code: 40100, msg: '原密码不正确', data: null }, 401));

    await expect(
      apiPost('/api/v1/auth/password', { old_password: 'x', new_password: 'yyyyyy' }),
    ).rejects.toMatchObject({ message: '原密码不正确' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('multipart 上传', () => {
  beforeEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('requestForm 提交 FormData 且不设置 Content-Type（交给浏览器带 boundary）', async () => {
    setTokens('access-1', 'refresh-1');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ code: 0, msg: 'ok', data: { id: 9 } }));

    const form = new FormData();
    form.append('file', new Blob(['x'], { type: 'image/png' }), 'a.png');
    form.append('public', 'true');
    const data = await requestForm<{ id: number }>('POST', '/api/v1/files', form);

    expect(data).toEqual({ id: 9 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v1/files');
    expect(init?.body).toBeInstanceOf(FormData);
    const headers = init?.headers as Record<string, string>;
    expect(headers['Content-Type']).toBeUndefined();
    expect(headers.Authorization).toBe('Bearer access-1');
  });
});

describe('downloadFile（CSV 导出）', () => {
  beforeEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    clearTokens();
  });

  it('成功：返回 Blob 且带鉴权头', async () => {
    setTokens('access-1', 'refresh-1');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('a,b\n1,2', { status: 200 }));

    const blob = await downloadFile('/api/v1/shop/merchant/orders/export');

    expect(await blob.text()).toContain('a,b');
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer access-1');
  });

  it('401 且刷新失败：清空会话并抛 401（不只是干瞪眼）', async () => {
    setTokens('access-1', 'refresh-1');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('/auth/refresh')) {
        return jsonResponse({ code: 40100, msg: '刷新失效', data: null }, 401);
      }
      return new Response('', { status: 401 });
    });

    await expect(downloadFile('/api/v1/shop/merchant/orders/export')).rejects.toMatchObject({
      code: 401,
    });
    expect(hasSession()).toBe(false);
  });

  it('非 2xx 且响应体是信封：透出后端错误文案', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ code: 40300, msg: '仅商户可导出', data: null }, 403),
    );

    await expect(downloadFile('/api/v1/shop/merchant/orders/export')).rejects.toMatchObject({
      message: '仅商户可导出',
    });
  });
});

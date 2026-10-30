/** 请求核心：统一信封解析、令牌注入、**401 自动刷新重试**。
 *
 * 刷新流（与后端 auth 模块的轮换语义配套）：
 * - 请求收到 40100（登录已过期）→ 用 refresh_token 换新令牌（并发请求共享同一次
 *   刷新，单飞）→ 重放原请求一次；
 * - refresh_token 缺失或刷新失败 → 清空本地令牌并抛出原错误（调用方提示重新登录）；
 * - 刷新接口自身与登录接口不参与重试，避免死循环。
 */

import type { ApiEnvelope } from './types';

/** 业务错误：携带后端返回的业务码与可直接展示的提示。 */
export class ApiError extends Error {
  constructor(
    readonly code: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const ACCESS_KEY = 'qh_access_token';
const REFRESH_KEY = 'qh_refresh_token';
const DEVICE_KEY = 'qh_device_id';
/** 业务码：未认证 / 登录已过期（后端 app/core/errors.py ErrorCode.UNAUTHORIZED）。 */
const CODE_UNAUTHORIZED = 40100;

/** 接口基地址。默认同源（开发期由 Vite 代理 /api 到后端）。 */
let baseUrl = '';

/** 接口基地址（供 SSE 等非信封请求拼接）。 */
export function getBaseUrl(): string {
  return baseUrl;
}

export function setBaseUrl(url: string): void {
  baseUrl = url.replace(/\/$/, '');
}

/** 本机设备标识（需求量 4.2 的设备绑定）：首次访问生成随机 ID 并持久化。
 *
 * 不是硬件指纹——只作「这台设备被授权过」的标识与风控信号；
 * 真正的凭据仍是刷新令牌（刷新时会话与设备必须匹配）。清缓存 = 新设备，需重新登录。
 */
export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = randomId();
    localStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

/** 写入设备标识（跨端口登录态交接时沿用源端设备，刷新校验才能通过）。 */
export function setDeviceId(deviceId: string): void {
  if (deviceId) {
    localStorage.setItem(DEVICE_KEY, deviceId);
  }
}

function randomId(): string {
  const webCrypto = globalThis.crypto as Crypto | undefined;
  if (webCrypto?.randomUUID) {
    return webCrypto.randomUUID().replace(/-/g, '');
  }
  if (webCrypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    webCrypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  }
  // 兜底（极老环境，无 Web Crypto）：设备标识不是凭据，非加密随机可接受
  return `d${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`.slice(0, 32);
}

/** 可读的设备名（浏览器 · 系统），仅用于设备列表展示，不做唯一识别。 */
export function getDeviceLabel(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /Firefox\//.test(ua)
      ? 'Firefox'
      : /Chrome\//.test(ua)
        ? 'Chrome'
        : /Safari\//.test(ua)
          ? 'Safari'
          : '浏览器';
  const os = /Windows/.test(ua)
    ? 'Windows'
    : /Android/.test(ua)
      ? 'Android'
      : /iPhone|iPad|iPod/.test(ua)
        ? 'iOS'
        : /Mac OS X|Macintosh/.test(ua)
          ? 'macOS'
          : /Linux/.test(ua)
            ? 'Linux'
            : '未知系统';
  return `${browser} · ${os}`;
}

/** 当前令牌所在存储：记住我 = localStorage；未勾选 = sessionStorage（关掉浏览器即失效）。 */
function tokensStore(): Storage {
  if (sessionStorage.getItem(REFRESH_KEY) || sessionStorage.getItem(ACCESS_KEY)) {
    return sessionStorage;
  }
  return localStorage;
}

export function getToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY) ?? localStorage.getItem(ACCESS_KEY);
}

export function setToken(token: string): void {
  tokensStore().setItem(ACCESS_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY) ?? localStorage.getItem(REFRESH_KEY);
}

/** 保存令牌对（登录 / 刷新成功后调用；刷新时 refresh_token 会轮换）。
 *
 * remember 仅在登录时传入：true → localStorage（30 天免密续期）；
 * false → sessionStorage（短期会话，关浏览器即失效）。刷新时省略，沿用当前存储。
 */
export function setTokens(accessToken: string, refreshToken?: string | null, remember?: boolean): void {
  const store = remember === undefined ? tokensStore() : remember ? localStorage : sessionStorage;
  const other = store === localStorage ? sessionStorage : localStorage;
  store.setItem(ACCESS_KEY, accessToken);
  if (refreshToken) {
    store.setItem(REFRESH_KEY, refreshToken);
  }
  other.removeItem(ACCESS_KEY);
  other.removeItem(REFRESH_KEY);
}

export function clearTokens(): void {
  for (const store of [localStorage, sessionStorage]) {
    store.removeItem(ACCESS_KEY);
    store.removeItem(REFRESH_KEY);
  }
}

/** 当前令牌是否存放在 localStorage（即登录时勾选了「记住我」）。
 *
 * 供修改密码等「当前端续期」场景复用同一 remember 语义，
 * 避免不勾选记住我的短期会话被悄悄拉长（服务端按该值决定新会话有效期）。
 */
export function isRemembered(): boolean {
  return !!(localStorage.getItem(REFRESH_KEY) || localStorage.getItem(ACCESS_KEY));
}

/** 是否存在会话（有任一令牌即视为可能登录——用于路由守卫的同步判断）。 */
export function hasSession(): boolean {
  return !!(getToken() || getRefreshToken());
}

let refreshPromise: Promise<boolean> | null = null;

/** 供 SSE 等非信封请求复用：尝试刷新令牌（并发单飞），返回是否成功。 */
export function tryRefresh(): Promise<boolean> {
  return refreshTokens();
}

/** 用 refresh_token 换新令牌对；并发调用共享同一次刷新（单飞）。 */
function refreshTokens(): Promise<boolean> {
  refreshPromise ??= (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      return false;
    }
    try {
      const resp = await fetch(`${baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken, device_id: getDeviceId() }),
      });
      const payload = (await resp.json()) as ApiEnvelope<{
        access_token: string;
        refresh_token: string;
      }>;
      if (payload.code !== 0) {
        return false;
      }
      setTokens(payload.data.access_token, payload.data.refresh_token);
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

/** 请求头：带设备标识（登录设备校验 / 设备列表的「当前设备」标记用）。 */
function baseHeaders(): Record<string, string> {
  return { 'X-Device-Id': getDeviceId() };
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  retried = false,
): Promise<T> {
  const headers: Record<string, string> = baseHeaders();
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`${baseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  return handleResponse<T>(resp, () => request<T>(method, path, body, true), path, retried);
}

/** 下载结果：文件本体 + 响应头（导出接口用 X-Export-* 告知行数 / 截断）。 */
export interface DownloadedFile {
  blob: Blob;
  headers: Headers;
}

/** 下载二进制文件（CSV 导出等）：带鉴权头，401 时刷新令牌并重放一次。 */
export async function downloadFileWithMeta(
  path: string,
  retried = false,
): Promise<DownloadedFile> {
  const headers: Record<string, string> = baseHeaders();
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const resp = await fetch(`${baseUrl}${path}`, { headers });
  if (resp.status === 401) {
    if (!retried && (await tryRefresh())) {
      return downloadFileWithMeta(path, true);
    }
    // 与普通请求一致：刷新失败即清理会话，避免角标与实际登录态不一致
    clearTokens();
    throw new ApiError(401, '登录已过期，请重新登录');
  }
  if (!resp.ok) {
    let message = `下载失败（HTTP ${resp.status}）`;
    try {
      const payload = (await resp.json()) as ApiEnvelope<unknown>;
      if (payload.msg) {
        message = payload.msg;
      }
    } catch {
      // 非 JSON 错误体：保留 HTTP 状态提示
    }
    throw new ApiError(resp.status, message);
  }
  return { blob: await resp.blob(), headers: resp.headers };
}

/** 只要文件本体时使用（导出接口的元数据请用 downloadFileWithMeta）。 */
export async function downloadFile(path: string, retried = false): Promise<Blob> {
  const { blob } = await downloadFileWithMeta(path, retried);
  return blob;
}

/** multipart 上传（如文件 / 图片）：不设置 Content-Type，交给浏览器带 boundary。 */
export async function requestForm<T>(
  method: string,
  path: string,
  form: FormData,
  retried = false,
): Promise<T> {
  const headers: Record<string, string> = baseHeaders();
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`${baseUrl}${path}`, { method, headers, body: form });
  return handleResponse<T>(resp, () => requestForm<T>(method, path, form, true), path, retried);
}

/** 统一解析响应信封：401 时刷新令牌并重放一次，其余非 0 code 抛错。 */
async function handleResponse<T>(
  resp: Response,
  retry: () => Promise<T>,
  path: string,
  retried: boolean,
): Promise<T> {
  let payload: ApiEnvelope<T>;
  try {
    payload = (await resp.json()) as ApiEnvelope<T>;
  } catch {
    throw new ApiError(-1, `服务异常（HTTP ${resp.status}）`);
  }

  if (payload.code === CODE_UNAUTHORIZED && !retried && !path.includes('/auth/')) {
    if (await refreshTokens()) {
      return retry();
    }
    clearTokens();
  }
  if (payload.code !== 0) {
    throw new ApiError(payload.code, payload.msg);
  }
  return payload.data;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>('GET', path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body);
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('PUT', path, body);
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('PATCH', path, body);
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>('DELETE', path);
}

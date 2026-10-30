/** 开发环境跨端口登录态交接。
 *
 * 生产环境三端同源（/portal/、/、/console/），令牌本来就在同一份 localStorage；
 * 只有开发期（5175 / 5173 / 5174 三个端口）需要把登录后的令牌带到目标端。
 *
 * 令牌放在 URL hash（不会发给服务端），目标端启动时立即写入存储并用
 * replaceState 清掉 hash。两个应用都以 import.meta.env.DEV 为开关调用，
 * 生产构建既不会生成也不会消费这类链接。
 */

import { getDeviceId, getRefreshToken, getToken, isRemembered, setDeviceId, setTokens } from './http';

export interface TokenHandoff {
  accessToken: string;
  refreshToken: string;
  remember: boolean;
  /** 登录时上报的设备标识；目标端沿用后才能正常刷新令牌。 */
  deviceId: string;
}

/** 解析 hash（可带或不带开头的 #）；没有 access_token 视为无效。 */
export function parseTokenHandoff(hash: string): TokenHandoff | null {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const params = new URLSearchParams(raw);
  const accessToken = params.get('access_token');
  if (!accessToken) {
    return null;
  }
  return {
    accessToken,
    refreshToken: params.get('refresh_token') ?? '',
    remember: params.get('remember') === '1',
    deviceId: params.get('device_id') ?? '',
  };
}

/** 把当前端登录态拼到目标地址的 hash 上；没有令牌则原样返回。 */
export function buildTokenHandoffUrl(target: string): string {
  const accessToken = getToken();
  if (!accessToken) {
    return target;
  }
  const params = new URLSearchParams();
  params.set('access_token', accessToken);
  const refreshToken = getRefreshToken();
  if (refreshToken) {
    params.set('refresh_token', refreshToken);
  }
  params.set('remember', isRemembered() ? '1' : '0');
  params.set('device_id', getDeviceId());
  return `${target.replace(/#.*$/, '')}#${params.toString()}`;
}

interface HandoffLocation {
  hash: string;
  pathname: string;
  search: string;
}

interface HandoffHistory {
  replaceState(data: unknown, unused: string, url?: string | URL | null): void;
}

/** 目标端启动时消费 hash 中的令牌，成功返回 true。
 *
 * 必须在路由守卫 / 登录态恢复之前调用，否则首屏会被当成未登录。
 */
export function consumeTokenHandoff(
  loc: HandoffLocation = window.location,
  hist: HandoffHistory = window.history,
): boolean {
  const handoff = parseTokenHandoff(loc.hash);
  if (!handoff) {
    return false;
  }
  if (handoff.deviceId) {
    setDeviceId(handoff.deviceId);
  }
  setTokens(handoff.accessToken, handoff.refreshToken || undefined, handoff.remember);
  hist.replaceState(null, '', `${loc.pathname}${loc.search}`);
  return true;
}

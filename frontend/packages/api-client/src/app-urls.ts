/** 三端地址与站内跳转校验。
 *
 * 开发 / E2E 时门户、游客端、控制台分属不同端口；生产三端同源，按路径区分。
 * 端口映射集中在这里，避免门户和各应用的登录跳转页各自硬编码。
 */

type AppName = 'portal' | 'tourist' | 'console';

const DEV_PORTS: Record<AppName, number> = { portal: 5175, tourist: 5173, console: 5174 };
const E2E_PORTS: Record<AppName, number> = { portal: 5275, tourist: 5273, console: 5274 };
const DEV_PORT_SET = new Set(Object.values(DEV_PORTS).map(String));
const E2E_PORT_SET = new Set(Object.values(E2E_PORTS).map(String));

function localBase(name: AppName): string | null {
  const { protocol, hostname, port } = window.location;
  if (DEV_PORT_SET.has(port)) {
    return `${protocol}//${hostname}:${DEV_PORTS[name]}/`;
  }
  if (E2E_PORT_SET.has(port)) {
    return `${protocol}//${hostname}:${E2E_PORTS[name]}/`;
  }
  return null;
}

/** 当前是否在本地开发 / E2E 端口（只有这些环境需要消费跨端口登录态交接）。 */
export function isLocalAppPort(): boolean {
  const port = window.location.port;
  return DEV_PORT_SET.has(port) || E2E_PORT_SET.has(port);
}

/** 统一登录门户地址：开发 5175，E2E 5275，生产 /portal/。 */
export function portalUrl(): string {
  return localBase('portal') ?? `${window.location.origin}/portal/`;
}

/** 游客端地址：开发 5173，E2E 5273，生产 /。 */
export function touristUrl(): string {
  return localBase('tourist') ?? `${window.location.origin}/`;
}

/** 控制台地址：开发 5174，E2E 5274，生产 /console/。 */
export function consoleUrl(): string {
  return localBase('console') ?? `${window.location.origin}/console/`;
}

/** 只接受站内绝对路径，拒绝 //host、反斜杠和带协议的跳转。 */
export function safeRedirectPath(raw: unknown): string {
  if (typeof raw !== 'string') {
    return '';
  }
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\')) {
    return '';
  }
  return raw;
}

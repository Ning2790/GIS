/* 游客端 PWA 离线壳（增强项）。
 *
 * 目标：弱网 / 断网时**页面本身还能打开**（静态资源与首页壳来自缓存），页面顶部有
 * 「当前离线」提示；数据接口一律不缓存——避免把过期的库存 / 价格当成实时数据。
 *
 * 策略：
 * - 安装：逐个预缓存首页壳（manifest / 图标任一缺失只记警告，不让整个 SW 装不上）；
 * - 导航请求：网络优先，失败回退缓存的首页壳（仅限本应用的路由，见 OFFLINE_ROUTES）；
 * - 运行时缓存**白名单**：只缓存同源 `/assets/` 下的 hash 产物与壳清单里的文件——
 *   控制台（同源 `/console/`）等其它前端不进游客端的缓存，也不会被本 SW 接管；
 * - /api/ 与跨域请求：完全不拦截（不缓存、不伪造响应）；
 * - activate 只清理**本应用前缀**的旧缓存（Cache Storage 是 origin 级，不能误删他方缓存）。
 *
 * 更新：改这个文件里的 CACHE 版本号即触发新缓存；本文件本身在 nginx 侧配了 no-cache，
 * 保证浏览器总能拿到最新版本（见 deploy/nginx/nginx.conf）。
 */

const CACHE = 'qh-tourist-shell-v1';
const SHELL = ['/', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];

// 游客端自身的路由前缀（离线导航只在这些路径上回退首页壳；
// /console/ 是控制台，离线时应该给出浏览器错误页而不是游客端首页）
const OFFLINE_ROUTES = [
  '/',
  '/login',
  '/attractions',
  '/map',
  '/gear',
  '/products',
  '/plan',
  '/routes',
  '/ai',
  '/cs',
  '/cart',
  '/orders',
  '/profile',
  '/addresses',
  '/after-sales',
  '/favorites',
  '/history',
];

/** 运行时缓存白名单：只缓存自己的静态产物与壳文件。 */
function cacheable(url) {
  if (url.origin !== self.location.origin) {
    return false;
  }
  if (url.pathname.startsWith('/api/')) {
    return false;
  }
  return (
    url.pathname.startsWith('/assets/') ||
    SHELL.includes(url.pathname) ||
    url.pathname.startsWith('/icon-') ||
    url.pathname === '/favicon.ico'
  );
}

function isOwnRoute(pathname) {
  return OFFLINE_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      // 逐个 add：单个文件缺失（改名 / 部署不完整）不会让整个 SW 装不上
      .then((cache) =>
        Promise.allSettled(SHELL.map((path) => cache.add(path))).then((results) => {
          results
            .filter((result) => result.status === 'rejected')
            .forEach((result) => console.warn('[sw] 预缓存失败：', result.reason));
        }),
      )
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      // 只清理自己的旧版本（Cache Storage 是 origin 级：不能删同源其它应用的缓存）
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key.startsWith('qh-tourist-') && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return; // 接口与跨域：交给网络，不缓存
  }

  // 导航请求：网络优先；离线且是本应用路由时回退首页壳（控制台等路径不接管）
  if (request.mode === 'navigate') {
    if (!isOwnRoute(url.pathname)) {
      return;
    }
    event.respondWith(
      fetch(request).catch(() => caches.match('/').then((cached) => cached ?? Response.error())),
    );
    return;
  }

  if (!cacheable(url)) {
    return; // 白名单之外（如 /console/ 的产物）：不缓存也不接管
  }

  // 白名单内的静态资源：缓存优先，后台刷新（下次更快）
  event.respondWith(
    caches.match(request).then((cached) => {
      const fetched = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached ?? fetched;
    }),
  );
});

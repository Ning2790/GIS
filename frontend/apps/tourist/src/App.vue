<script setup lang="ts">
import { portalUrl } from '@qh/api-client';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router';

import StarDust from './components/StarDust.vue';
import { useAuthStore } from './stores/auth';
import { useCartStore } from './stores/cart';
import { useNotificationsStore } from './stores/notifications';

const auth = useAuthStore();
const cart = useCartStore();
const notifications = useNotificationsStore();
const router = useRouter();
const route = useRoute();
const currentYear = new Date().getFullYear();

/** 旅游板块的二级导航：三个模块分别复用原有页面。 */
const travelTabs = [
  { to: '/attractions', label: '景点概览' },
  { to: '/routes', label: '精选路线' },
  { to: '/plan', label: '智能规划' },
];
const inTravel = computed(() => /^\/(attractions|routes|plan)(\/|$)/.test(route.path));

// 星尘只作为地图、旅游、商城、AI、客服等公开模块的环境装饰，不进入首页和个人中心。
const showStarDust = computed(() =>
  /^\/(map|gear|products|attractions|routes|plan|ai|cs)(\/|$)/.test(route.path),
);

// 统一登录门户（apps/portal）；游客端顶栏的登录入口直接过去
const portalHref = portalUrl();

// 路由切换期间锁定内容区高度：旧页面移除后文档高度会瞬间塌陷，
// 滚动条消失/出现会让整页宽度和顶栏位置抖动。
const pageMain = ref<HTMLElement | null>(null);
let pageHeightLock = 0;

function holdPageHeight() {
  const el = pageMain.value;
  if (!el) {
    return;
  }
  pageHeightLock += 1;
  el.style.minHeight = `${el.offsetHeight}px`;
}

function releasePageHeight() {
  const el = pageMain.value;
  if (!el) {
    return;
  }
  const lock = pageHeightLock;
  requestAnimationFrame(() => {
    if (lock === pageHeightLock) {
      el.style.minHeight = '';
    }
  });
}

// 离线提示（PWA 离线壳）：断网时页面来自缓存，接口数据不缓存——
// 明确告诉用户"看到的是壳、数据是旧的"，避免把过期价格当实时数据
const offline = ref(!navigator.onLine);

function markOffline() {
  offline.value = true;
}

function markOnline() {
  offline.value = false;
}

onMounted(() => {
  window.addEventListener('offline', markOffline);
  window.addEventListener('online', markOnline);
});

onBeforeUnmount(() => {
  window.removeEventListener('offline', markOffline);
  window.removeEventListener('online', markOnline);
});

async function handleLogout() {
  await auth.logout();
  void router.push('/');
}

// 登录 / 退出时同步购物车与未读通知角标
watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      void cart.refresh();
      void notifications.refresh();
    } else {
      cart.clear();
      notifications.clear();
    }
  },
);
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell--starhome': route.name === 'home' }">
    <StarDust v-if="showStarDust" />

    <p v-if="offline" class="offline-bar">
      当前处于离线状态：页面来自本地缓存，商品与订单数据需要联网后才会更新
    </p>

    <header class="topbar">
      <div class="topbar__inner">
        <RouterLink to="/" class="brand">
          <img class="brand__logo" src="/logo-tianjing-mark.png?v=20261023" alt="天境源康" />
          <span class="brand__text">
            <strong>天境源康</strong>
            <small>JWFZ</small>
          </span>
        </RouterLink>

        <nav class="topbar__nav" aria-label="主导航">
          <RouterLink to="/">首页</RouterLink>
          <RouterLink to="/map">地图</RouterLink>
          <RouterLink to="/attractions" :class="{ 'router-link-active': inTravel }">旅游</RouterLink>
          <RouterLink to="/gear">装备与气象</RouterLink>
          <RouterLink to="/products">特产商城</RouterLink>
          <RouterLink to="/ai">AI 助手</RouterLink>
          <RouterLink to="/cs">在线客服</RouterLink>
        </nav>

        <div class="account">
          <template v-if="auth.isLoggedIn">
            <RouterLink to="/notifications" class="account__action">
              通知<template v-if="notifications.unread > 0">（{{ notifications.unread }}）</template>
            </RouterLink>
            <RouterLink to="/cart" class="account__action">
              购物车<template v-if="cart.count > 0">（{{ cart.count }}）</template>
            </RouterLink>
            <RouterLink to="/orders" class="account__action">我的订单</RouterLink>
            <RouterLink to="/profile" class="account__action">个人中心</RouterLink>
            <span class="account__name">{{ auth.displayName }}</span>
            <a class="account__action account__action--muted" href="#" @click.prevent="handleLogout">
              退出
            </a>
          </template>
          <a v-else class="account__cta" :href="portalHref">登录 / 注册</a>
        </div>
      </div>
    </header>

    <nav v-if="inTravel" class="travel-nav" aria-label="旅游导航">
      <div class="travel-nav__inner">
        <RouterLink v-for="item in travelTabs" :key="item.to" :to="item.to">
          {{ item.label }}
        </RouterLink>
      </div>
    </nav>

    <main ref="pageMain">
      <RouterView v-slot="{ Component, route }">
        <Transition
          name="page"
          mode="out-in"
          @before-leave="holdPageHeight"
          @after-enter="releasePageHeight"
        >
          <div :key="route.path" class="page-view">
            <component :is="Component" />
          </div>
        </Transition>
      </RouterView>
    </main>

    <footer class="site-footer">
      <span class="site-footer__rule" aria-hidden="true"></span>
      <p class="site-footer__credit">© {{ currentYear }} 天境源康 · 经纬方舟团队</p>
      <p class="site-footer__org">青海师范大学 地理科学学院</p>
    </footer>
  </div>
</template>

<style scoped>
/* 游客端品牌壳：深色顶栏 / 页脚 + 暖白内容区，与门户的深蓝青色系呼应 */
.app-shell {
  --tourist-bg: #eaf3ff;
  --tourist-surface: rgba(255, 255, 255, 0.82);
  --tourist-ink: #0b1b3a;
  --tourist-ink-2: #334a6b;
  --tourist-muted: #667a99;
  --tourist-line: rgba(37, 99, 235, 0.14);
  --tourist-cyan: #0284c7;
  --tourist-cyan-light: #7dd3fc;
  --tourist-sand: #38bdf8;
  --tourist-serif: 'Songti SC', SimSun, 'STSong', serif;
  --tourist-container: 1120px;

  --qh-bg: #eef5ff;
  --qh-surface: rgba(255, 255, 255, 0.84);
  --qh-surface-soft: #eaf2ff;
  --qh-ink: #0b1b3a;
  --qh-ink-2: #334a6b;
  --qh-muted: #667a99;
  --qh-faint: #8396b0;
  --qh-border: rgba(37, 99, 235, 0.14);
  --qh-border-strong: rgba(37, 99, 235, 0.26);
  --qh-primary: #1d4ed8;
  --qh-primary-hover: #1e40af;
  --qh-primary-active: #1e3a8a;
  --qh-primary-weak: #e8f1ff;
  --qh-primary-border: #bfdbfe;
  --qh-accent: #0891b2;
  --qh-accent-weak: #e0f2fe;

  position: relative;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #eaf3ff;
  color: var(--tourist-ink);
}
.topbar,
.travel-nav,
main,
.site-footer,
.offline-bar {
  position: relative;
  z-index: 1;
}
.topbar,
.travel-nav,
main,
.site-footer,
.offline-bar {
  position: relative;
  z-index: 1;
}

.offline-bar {
  margin: 0;
  padding: 6px var(--qh-space-4);
  background: #fef3c7;
  color: #92400e;
  font-size: var(--qh-fs-sm);
  text-align: center;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 50;
  border-bottom: 1px solid rgba(125, 211, 252, 0.16);
  background: rgba(8, 17, 31, 0.94);
  backdrop-filter: blur(16px);
}
.topbar::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  background: linear-gradient(90deg, rgba(29, 78, 216, 0), #1d4ed8 18%, #38bdf8 50%, #818cf8 78%, rgba(129, 140, 248, 0));
  opacity: 0.9;
}
.topbar a,
.travel-nav a {
  text-decoration: none;
}
.topbar__inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--qh-space-4);
  max-width: var(--tourist-container);
  height: 68px;
  margin: 0 auto;
  padding: 0 var(--qh-space-5);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
  color: #fff;
}
.brand:hover {
  text-decoration: none;
}
.brand__logo {
  width: 46px;
  height: 46px;
  flex: none;
  object-fit: contain;
  filter: drop-shadow(0 2px 5px rgba(0, 0, 0, 0.28));
}
.brand__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.brand__text strong {
  font-family: var(--tourist-serif);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 1;
}
.brand__text small {
  color: var(--tourist-cyan-light);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.28em;
  line-height: 1;
}
.topbar__nav {
  display: flex;
  flex: 1;
  justify-content: center;
  gap: 18px;
}
.topbar__nav a {
  position: relative;
  padding: 6px 0;
  color: #cbd5e1;
  font-size: 13px;
  white-space: nowrap;
  transition: color 0.15s ease;
}
.topbar__nav a:hover {
  color: #fff;
  text-decoration: none;
}
.topbar__nav a.router-link-active {
  color: var(--tourist-cyan-light);
}
.account {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
  font-size: 12px;
  white-space: nowrap;
}
.account__name {
  color: #e2e8f0;
  font-weight: 600;
}
.account__action {
  color: #cbd5e1;
}
.account__action:hover {
  color: #fff;
  text-decoration: none;
}
.account__action--muted {
  color: #94a3b8;
}
.account__cta {
  padding: 8px 16px;
  border: 1px solid rgba(103, 232, 249, 0.55);
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}
.account__cta:hover {
  border-color: var(--tourist-cyan-light);
  background: rgba(8, 145, 178, 0.22);
  text-decoration: none;
}

.travel-nav {
  border-bottom: 1px solid var(--tourist-line);
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(16px);
  box-shadow: 0 8px 22px -18px rgba(37, 99, 235, 0.22);
}
.travel-nav__inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  max-width: var(--tourist-container);
  height: 58px;
  margin: 0 auto;
  padding: 0 var(--qh-space-5);
  overflow-x: auto;
}
.travel-nav a {
  flex: none;
  padding: 8px 20px;
  border-radius: 999px;
  color: var(--tourist-ink-2);
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}
.travel-nav a:hover {
  background: rgba(8, 145, 178, 0.08);
  color: var(--tourist-cyan);
  text-decoration: none;
}
.travel-nav a.router-link-active {
  background: var(--tourist-cyan);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 10px -2px rgba(8, 145, 178, 0.35);
}

.site-footer {
  padding: 8px var(--qh-space-5) 72px;
  text-align: center;
}
.site-footer__rule {
  display: block;
  width: 28px;
  height: 1px;
  margin: 0 auto 16px;
  background: var(--tourist-sand);
  opacity: 0.55;
}
.site-footer__credit,
.site-footer__org {
  margin: 0;
  color: var(--tourist-muted);
  font-size: 12px;
  font-weight: 400;
  letter-spacing: 0.06em;
}
.site-footer__org {
  margin-top: 7px;
}
.app-shell--starhome {
  background: #fbf8f1;
}
.app-shell--starhome .site-footer__credit,
.app-shell--starhome .site-footer__org {
  color: var(--tourist-muted, #6b7280);
}
.app-shell--starhome .site-footer__rule {
  width: 36px;
  background: linear-gradient(90deg, transparent, rgba(201, 154, 66, 0.55), rgba(120, 154, 189, 0.45), transparent);
}

main {
  flex: 1;
  width: 100%;
  max-width: var(--tourist-container);
  margin: 0 auto;
  padding: var(--qh-space-6) var(--qh-space-5) 72px;
}

/* 路由切换：只做淡入淡出，避免位移触发滚动条/高度变化造成抖动 */
.page-view {
  min-width: 0;
}
.page-enter-active {
  transition: opacity 180ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: opacity;
}
.page-leave-active {
  transition: opacity 40ms ease-in;
  will-change: opacity;
}
.page-enter-from {
  /* 从 20% 起淡入，避免新页面第一帧完全空白 */
  opacity: 0.2;
}
.page-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active {
    transition-duration: 0.01ms;
  }
  .page-enter-from,
  .page-leave-to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 1100px) {
  .topbar__inner {
    flex-wrap: wrap;
    height: auto;
    padding: var(--qh-space-2) var(--qh-space-4);
    gap: 6px var(--qh-space-3);
  }
  .topbar__nav {
    order: 3;
    flex-basis: 100%;
    justify-content: flex-start;
    overflow-x: auto;
    padding-bottom: 2px;
  }
  .account {
    margin-left: auto;
  }
}

@media (max-width: 720px) {
  .brand__text strong {
    font-size: 18px;
  }
  .topbar__nav {
    gap: 16px;
  }
  .travel-nav__inner {
    justify-content: flex-start;
    gap: 4px;
    padding: 0 var(--qh-space-4);
  }
  .travel-nav a {
    padding: 8px 14px;
  }
  main {
    padding: var(--qh-space-4) var(--qh-space-4) 56px;
  }
}
</style>

<style>
body {
  background: #eaf3ff;
}

</style>

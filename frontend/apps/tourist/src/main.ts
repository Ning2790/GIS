import { consumeTokenHandoff, hasSession, isLocalAppPort } from '@qh/api-client';
import { createPinia } from 'pinia';
import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';

import App from './App.vue';
import { useAuthStore } from './stores/auth';
import { useCartStore } from './stores/cart';
import { useNotificationsStore } from './stores/notifications';

// 独立登录门户（portal）在开发 / E2E 环境通过 hash 交接令牌；必须在路由守卫前消费
if (isLocalAppPort()) {
  consumeTokenHandoff();
}


// 页面按路由懒加载：首屏只加载当前页，避免一次拉入全部页面模块。
const Home = () => import('./pages/Home.vue');
const Login = () => import('./pages/Login.vue');
const Attractions = () => import('./pages/Attractions.vue');
const AttractionDetail = () => import('./pages/AttractionDetail.vue');
const Map = () => import('./pages/Map.vue');
const Gear = () => import('./pages/Gear.vue');
const Products = () => import('./pages/Products.vue');
const ProductDetail = () => import('./pages/ProductDetail.vue');
const Plan = () => import('./pages/Plan.vue');
const PlanDetail = () => import('./pages/PlanDetail.vue');
const Routes = () => import('./pages/Routes.vue');
const RouteDetail = () => import('./pages/RouteDetail.vue');
const Ai = () => import('./pages/Ai.vue');
const Cs = () => import('./pages/Cs.vue');
const Cart = () => import('./pages/Cart.vue');
const Orders = () => import('./pages/Orders.vue');
const Notifications = () => import('./pages/Notifications.vue');
const Profile = () => import('./pages/Profile.vue');
const Favorites = () => import('./pages/Favorites.vue');
const History = () => import('./pages/History.vue');
const Addresses = () => import('./pages/Addresses.vue');
const AfterSales = () => import('./pages/AfterSales.vue');
const AfterSaleDetail = () => import('./pages/AfterSaleDetail.vue');
const OrderDetail = () => import('./pages/OrderDetail.vue');

let scrollRequest = 0;

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/login', name: 'login', component: Login },
    { path: '/attractions', name: 'attractions', component: Attractions },
    { path: '/attractions/:id', name: 'attraction-detail', component: AttractionDetail },
    { path: '/map', name: 'map', component: Map },
    { path: '/gear', name: 'gear', component: Gear },
    // B2B 供需仅面向商户 / 企业，游客端不再提供页面；旧链接回首页
    { path: '/b2b', redirect: '/' },
    { path: '/products', name: 'products', component: Products },
    { path: '/products/:id', name: 'product-detail', component: ProductDetail },
    { path: '/plan', name: 'plan', component: Plan, meta: { requiresAuth: true } },
    { path: '/plan/:id', name: 'plan-detail', component: PlanDetail, meta: { requiresAuth: true } },
    { path: '/routes', name: 'routes', component: Routes },
    { path: '/routes/:id', name: 'route-detail', component: RouteDetail },
    { path: '/ai', name: 'ai', component: Ai, meta: { requiresAuth: true } },
    { path: '/cs', name: 'cs', component: Cs, meta: { requiresAuth: true } },
    { path: '/cart', name: 'cart', component: Cart, meta: { requiresAuth: true } },
    { path: '/orders', name: 'orders', component: Orders, meta: { requiresAuth: true } },
    {
      path: '/notifications',
      name: 'notifications',
      component: Notifications,
      meta: { requiresAuth: true },
    },
    { path: '/profile', name: 'profile', component: Profile, meta: { requiresAuth: true } },
    { path: '/favorites', name: 'favorites', component: Favorites, meta: { requiresAuth: true } },
    { path: '/history', name: 'history', component: History, meta: { requiresAuth: true } },
    { path: '/addresses', name: 'addresses', component: Addresses, meta: { requiresAuth: true } },
    { path: '/after-sales', name: 'after-sales', component: AfterSales, meta: { requiresAuth: true } },
    {
      path: '/after-sales/:id',
      name: 'after-sale-detail',
      component: AfterSaleDetail,
      meta: { requiresAuth: true },
    },
    { path: '/orders/:id', name: 'order-detail', component: OrderDetail, meta: { requiresAuth: true } },
  ],
  scrollBehavior(_to, _from, savedPosition) {
    // 等离场动画结束、新页面挂载后再恢复位置：
    // 页面切换瞬间高度会短暂塌陷，立即滚动会被截断。
    const requestId = ++scrollRequest;
    const target = savedPosition ?? { top: 0 };
    const startedAt = Date.now();

    return new Promise((resolve) => {
      const restore = () => {
        if (requestId !== scrollRequest) {
          resolve(false);
          return;
        }
        const maxTop = Math.max(
          0,
          document.documentElement.scrollHeight - window.innerHeight,
        );
        if ((target.top ?? 0) <= maxTop || Date.now() - startedAt > 1200) {
          resolve(target);
          return;
        }
        window.setTimeout(restore, 50);
      };
      window.setTimeout(restore, 120);
    });
  },
});

const pinia = createPinia();

// 路由守卫：需要登录的页面（meta.requiresAuth）在无会话时引导登录
router.beforeEach((to) => {
  if (to.meta.requiresAuth && !hasSession()) {
    return { name: 'login', query: { redirect: to.fullPath } };
  }
  return true;
});

const app = createApp(App).use(pinia).use(router);

// 启动时恢复登录态，并同步购物车与未读通知角标（有令牌才会请求，失败静默）
void useAuthStore(pinia)
  .restore()
  .then(() => {
    void useCartStore(pinia).refresh();
    void useNotificationsStore(pinia).refresh();
  });

app.mount('#app');

// PWA 离线壳：仅生产构建注册（开发期 Service Worker 会拦截 HMR 请求）。
// 失败静默——离线能力是增强，不影响正常使用。
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}

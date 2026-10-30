import { consumeTokenHandoff, hasSession, isLocalAppPort } from '@qh/api-client';
import ElementPlus from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/dist/index.css';
import { createPinia } from 'pinia';
import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';

import App from './App.vue';
import ConsoleLayout from './layouts/ConsoleLayout.vue';
import AdminAuditLogs from './pages/admin/AuditLogs.vue';
import AdminReviews from './pages/admin/Reviews.vue';
import AdminUsers from './pages/admin/Users.vue';
import AfterSales from './pages/AfterSales.vue';
import B2bManage from './pages/B2bManage.vue';
import CsWorkbench from './pages/CsWorkbench.vue';
import Dashboard from './pages/Dashboard.vue';
import Devices from './pages/Devices.vue';
import Login from './pages/Login.vue';
import Notifications from './pages/Notifications.vue';
import Orders from './pages/Orders.vue';
import Products from './pages/Products.vue';
import RoutesManage from './pages/RoutesManage.vue';
import { useAuthStore } from './stores/auth';
import './styles/theme.css';

const CONSOLE_ROLES = ['merchant', 'enterprise', 'admin'];

// 独立登录门户（portal）在开发 / E2E 环境通过 hash 交接令牌；必须在路由守卫前消费
if (isLocalAppPort()) {
  consumeTokenHandoff();
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login },
    {
      path: '/',
      component: ConsoleLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'dashboard', component: Dashboard, meta: { roles: CONSOLE_ROLES } },
        {
          path: 'notifications',
          name: 'notifications',
          component: Notifications,
          meta: { roles: CONSOLE_ROLES },
        },
        { path: 'products', name: 'products', component: Products, meta: { roles: CONSOLE_ROLES } },
        { path: 'orders', name: 'orders', component: Orders, meta: { roles: CONSOLE_ROLES } },
        { path: 'b2b', name: 'b2b', component: B2bManage, meta: { roles: CONSOLE_ROLES } },
        { path: 'cs', name: 'cs', component: CsWorkbench, meta: { roles: CONSOLE_ROLES } },
        { path: 'devices', name: 'devices', component: Devices, meta: { roles: CONSOLE_ROLES } },
        { path: 'after-sales', name: 'after-sales', component: AfterSales, meta: { roles: CONSOLE_ROLES } },
        { path: 'admin/routes', name: 'admin-routes', component: RoutesManage, meta: { roles: ['admin'] } },
        { path: 'admin/reviews', name: 'admin-reviews', component: AdminReviews, meta: { roles: ['admin'] } },
        { path: 'admin/users', name: 'admin-users', component: AdminUsers, meta: { roles: ['admin'] } },
        {
          path: 'admin/audit-logs',
          name: 'admin-audit-logs',
          component: AdminAuditLogs,
          meta: { roles: ['admin'] },
        },
      ],
    },
  ],
});

const pinia = createPinia();

// 路由守卫：登录（token 兜底）+ 角色
router.beforeEach((to) => {
  if (to.meta.requiresAuth && !hasSession()) {
    return { name: 'login', query: { redirect: to.fullPath } };
  }
  const roles = to.meta.roles as string[] | undefined;
  const auth = useAuthStore(pinia);
  if (roles && auth.user && !roles.includes(auth.user.role)) {
    return { name: 'products' };
  }
  return true;
});

const app = createApp(App).use(pinia).use(router);
app.use(ElementPlus, { locale: zhCn });

void useAuthStore(pinia).restore();

app.mount('#app');

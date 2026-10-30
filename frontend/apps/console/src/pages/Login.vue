<script setup lang="ts">
/** 旧登录页已收敛到统一门户：保留路由做跳转，旧链接 / 书签不失效。 */

import { clearTokens, hasSession, portalUrl, safeRedirectPath, touristUrl } from '@qh/api-client';
import '@qh/ui';
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const CONSOLE_ROLES = ['merchant', 'enterprise', 'admin'];

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const redirect = safeRedirectPath(route.query.redirect);

onMounted(async () => {
  if (hasSession()) {
    await auth.restore();
    if (auth.user && CONSOLE_ROLES.includes(auth.user.role)) {
      void router.replace(redirect || '/');
      return;
    }
    if (auth.user) {
      // 生产三端同源：游客会话应回游客端，而不是留在控制台
      window.location.replace(touristUrl());
      return;
    }
    clearTokens();
  }

  const params = new URLSearchParams({ from: 'console' });
  if (redirect) {
    params.set('redirect', redirect);
  }
  window.location.replace(`${portalUrl()}?${params.toString()}`);
});
</script>

<template>
  <div class="redirect-page">
    <p>正在前往统一登录…</p>
  </div>
</template>

<style scoped>
.redirect-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--qh-ink);
}
.redirect-page p {
  margin: 0;
  color: rgba(255, 255, 255, 0.7);
  font-size: var(--qh-fs-md);
}
</style>

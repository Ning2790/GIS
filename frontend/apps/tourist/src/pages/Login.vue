<script setup lang="ts">
/** 旧登录页已收敛到统一门户：保留路由做跳转，旧链接 / 书签不失效。 */

import { clearTokens, consoleUrl, hasSession, portalUrl, safeRedirectPath } from '@qh/api-client';
import '@qh/ui';
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const redirect = safeRedirectPath(route.query.redirect);

onMounted(async () => {
  if (hasSession()) {
    await auth.restore();
    if (auth.user?.role === 'tourist') {
      void router.replace(redirect || '/');
      return;
    }
    if (auth.user) {
      // 生产三端同源：商户 / 管理员会话应去控制台，而不是回门户重新登录
      window.location.replace(consoleUrl());
      return;
    }
    clearTokens();
  }

  const params = new URLSearchParams({ from: 'tourist' });
  if (redirect) {
    params.set('redirect', redirect);
  }
  window.location.replace(`${portalUrl()}?${params.toString()}`);
});
</script>

<template>
  <p class="redirect-hint">正在前往统一登录…</p>
</template>

<style scoped>
.redirect-hint {
  margin: var(--qh-space-5) 0;
  color: var(--qh-muted);
  text-align: center;
}
</style>

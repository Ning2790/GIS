<script setup lang="ts">
/** 页面标题 · C 风格基线组件（游客端与控制台共用）。 */
defineProps<{
  title: string;
  subtitle?: string;
  /** large：商城 / AI / 客服页使用的放大版页头。 */
  size?: 'default' | 'large';
}>();
</script>

<template>
  <header class="page-title" :class="{ 'page-title--large': size === 'large' }">
    <h1>{{ title }}</h1>
    <p v-if="subtitle">{{ subtitle }}</p>
  </header>
</template>

<style scoped>
.page-title h1 {
  margin: 0 0 var(--qh-space-1);
  font-size: var(--qh-fs-2xl);
  letter-spacing: -0.01em;
}
.page-title p {
  margin: 0 0 var(--qh-space-4);
  color: var(--qh-muted);
  font-size: var(--qh-fs-md);
}
.page-title--large h1 {
  margin-bottom: var(--qh-space-2);
  font-size: 30px;
  letter-spacing: 0;
}
.page-title--large p {
  margin-bottom: var(--qh-space-5);
  color: var(--qh-ink-2);
  font-size: var(--qh-fs-lg);
  line-height: 1.7;
}

@media (max-width: 720px) {
  .page-title h1 {
    font-size: var(--qh-fs-xl);
  }
  .page-title--large h1 {
    font-size: 26px;
  }
  .page-title--large p {
    font-size: var(--qh-fs-md);
  }
}
</style>

<script setup lang="ts">
/** 卡片容器 · C 风格基线组件（描边 + 圆角 + 轻阴影；可选 header 插槽）。 */
withDefaults(defineProps<{ padding?: 'md' | 'lg' | 'none' }>(), { padding: 'md' });
</script>

<template>
  <section class="qh-card" :class="`qh-card--pad-${padding}`">
    <header v-if="$slots.header" class="qh-card__header">
      <slot name="header" />
    </header>
    <slot />
  </section>
</template>

<style scoped>
.qh-card {
  background: var(--qh-surface);
  border: 1px solid var(--qh-border);
  border-radius: var(--qh-radius-lg);
  box-shadow: var(--qh-shadow-sm);
}
.qh-card--pad-md {
  padding: var(--qh-space-4) var(--qh-space-5);
}
.qh-card--pad-lg {
  padding: var(--qh-space-6);
}
.qh-card--pad-none {
  padding: 0;
}
.qh-card__header {
  margin-bottom: var(--qh-space-3);
  font-weight: 600;
  font-size: var(--qh-fs-lg);
}
</style>

<script setup lang="ts">
/** 空状态占位 · C 风格基线组件。 */
defineProps<{ text?: string }>();
</script>

<template>
  <div class="qh-empty">
    <span class="qh-empty__dot"></span>
    <p>{{ text ?? '暂无数据' }}</p>
    <slot />
  </div>
</template>

<style scoped>
.qh-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--qh-space-3);
  padding: var(--qh-space-6) var(--qh-space-4);
  color: var(--qh-muted);
  text-align: center;
}
.qh-empty__dot {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--qh-primary-weak), var(--qh-accent-weak));
  border: 1px solid var(--qh-primary-border);
}
.qh-empty p {
  margin: 0;
  font-size: var(--qh-fs-sm);
}
</style>

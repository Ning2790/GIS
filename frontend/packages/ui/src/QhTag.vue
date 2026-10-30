<script setup lang="ts">
/** 标签 / 徽标 · C 风格基线组件。 */
withDefaults(defineProps<{ tone?: 'default' | 'primary' | 'success' | 'warning' | 'danger' }>(), {
  tone: 'primary',
});
</script>

<template>
  <span class="qh-tag" :class="`qh-tag--${tone}`"><slot /></span>
</template>

<style scoped>
.qh-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--qh-radius-pill);
  font-size: var(--qh-fs-xs);
  font-weight: 600;
  line-height: 1.6;
}
.qh-tag--default {
  background: var(--qh-bg);
  color: var(--qh-ink-2);
  border: 1px solid var(--qh-border);
}
.qh-tag--primary {
  background: var(--qh-accent-weak);
  color: #0369a1;
}
.qh-tag--success {
  background: var(--qh-success-bg);
  color: var(--qh-success);
}
.qh-tag--warning {
  background: var(--qh-warning-bg);
  color: var(--qh-warning);
}
.qh-tag--danger {
  background: var(--qh-danger-bg);
  color: var(--qh-danger);
}
</style>

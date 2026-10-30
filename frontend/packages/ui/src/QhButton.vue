<script setup lang="ts">
/** 按钮 · C 风格基线组件（主色 / 描边 / 危险 三种外观）。 */
withDefaults(
  defineProps<{
    variant?: 'primary' | 'ghost' | 'danger';
    size?: 'md' | 'sm';
    type?: 'button' | 'submit';
    disabled?: boolean;
  }>(),
  { variant: 'primary', size: 'md', type: 'button', disabled: false },
);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="qh-btn"
    :class="[`qh-btn--${variant}`, `qh-btn--${size}`]"
  >
    <slot />
  </button>
</template>

<style scoped>
.qh-btn {
  border: 1px solid transparent;
  border-radius: var(--qh-radius-sm);
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}
.qh-btn--md {
  padding: 9px 18px;
  font-size: var(--qh-fs-md);
}
.qh-btn--sm {
  padding: 5px 12px;
  font-size: var(--qh-fs-sm);
}
.qh-btn--primary {
  background: var(--qh-primary);
  color: #fff;
}
.qh-btn--primary:hover {
  background: var(--qh-primary-hover);
}
.qh-btn--ghost {
  background: transparent;
  color: var(--qh-primary);
  border-color: var(--qh-primary-border);
}
.qh-btn--ghost:hover {
  background: var(--qh-primary-weak);
}
.qh-btn--danger {
  background: var(--qh-danger);
  color: #fff;
}
.qh-btn--danger:hover {
  filter: brightness(0.93);
}
.qh-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>

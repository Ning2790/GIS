<script setup lang="ts">
/** 输入框 · C 风格基线组件（v-model 双向绑定）。 */
const model = defineModel<string>({ default: '' });
withDefaults(
  defineProps<{
    type?: string;
    placeholder?: string;
    disabled?: boolean;
    autocomplete?: string;
    maxlength?: number;
  }>(),
  { type: 'text', placeholder: '', disabled: false, autocomplete: 'off', maxlength: undefined },
);
</script>

<template>
  <input
    v-model="model"
    class="qh-input"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    :autocomplete="autocomplete"
    :maxlength="maxlength"
  />
</template>

<style scoped>
.qh-input {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
  outline: none;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.qh-input:focus {
  border-color: var(--qh-primary);
  box-shadow: 0 0 0 3px var(--qh-primary-weak);
}
.qh-input:disabled {
  background: var(--qh-bg);
  color: var(--qh-muted);
}
</style>

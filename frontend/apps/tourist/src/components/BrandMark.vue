<script setup lang="ts">
/** 游客端品牌标记：山脊 + 高原日光。 */
</script>

<template>
  <svg class="brand-mark" viewBox="0 0 36 36" aria-hidden="true">
    <circle class="brand-mark__sun" cx="26" cy="9.5" r="4.2" />
    <path class="brand-mark__ridge" d="M2.5 26 12 11.5l6.2 8.6L23 13l10.5 13" />
    <path class="brand-mark__base" d="M2.5 30.5h31" />
  </svg>
</template>

<style scoped>
.brand-mark {
  width: 30px;
  height: 30px;
  flex: none;
  color: var(--tourist-cyan-light, #67e8f9);
}
.brand-mark__sun {
  fill: var(--tourist-sand, #d6b27a);
}
.brand-mark__ridge {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.brand-mark__base {
  stroke: currentColor;
  stroke-width: 1;
  opacity: 0.35;
}
</style>

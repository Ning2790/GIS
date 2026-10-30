<script setup lang="ts">
/** 核心列表页的深色页头：与首页首屏同一套品牌壳。 */
defineProps<{
  eyebrow: string;
  title: string;
  subtitle?: string;
  index?: string;
}>();
</script>

<template>
  <header class="page-hero">
    <div class="page-hero__rings" aria-hidden="true"></div>
    <div class="page-hero__body">
      <p class="page-hero__eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="page-hero__sub">{{ subtitle }}</p>
    </div>
    <span v-if="index" class="page-hero__index" aria-hidden="true">{{ index }}</span>
  </header>
</template>

<style scoped>
.page-hero {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: flex-end;
  min-height: 200px;
  margin-bottom: var(--qh-space-5);
  padding: 36px 40px 32px;
  border-radius: 24px;
  background:
    linear-gradient(120deg, rgba(8, 17, 31, 0.98), rgba(14, 42, 77, 0.92) 62%, rgba(8, 105, 128, 0.8)),
    #08111f;
  color: #f8fafc;
}
.page-hero__rings {
  position: absolute;
  top: -240px;
  right: -170px;
  width: 620px;
  height: 620px;
  border-radius: 50%;
  background: repeating-radial-gradient(
    circle,
    rgba(103, 232, 249, 0.14) 0 1px,
    transparent 1px 28px
  );
  opacity: 0.8;
}
.page-hero__rings::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tourist-sand, #d6b27a);
  box-shadow: 0 0 0 8px rgba(214, 178, 122, 0.12);
  transform: translate(-50%, -50%);
}
.page-hero__body {
  position: relative;
  z-index: 1;
  max-width: 720px;
}
.page-hero__eyebrow {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 14px;
  color: var(--tourist-cyan-light, #67e8f9);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
}
.page-hero__eyebrow::before {
  content: '';
  width: 30px;
  height: 1px;
  background: var(--tourist-sand, #d6b27a);
}
.page-hero h1 {
  margin: 0;
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: clamp(34px, 4vw, 46px);
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.15;
}
.page-hero__sub {
  max-width: 580px;
  margin: 14px 0 0;
  color: rgba(226, 232, 240, 0.68);
  font-size: var(--qh-fs-md);
  line-height: 1.7;
}
.page-hero__index {
  position: absolute;
  right: 34px;
  bottom: 4px;
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 112px;
  font-weight: 700;
  line-height: 1;
  color: rgba(248, 250, 252, 0.08);
  letter-spacing: -0.04em;
  user-select: none;
}

@media (max-width: 720px) {
  .page-hero {
    min-height: 180px;
    padding: 28px 24px 26px;
    border-radius: 18px;
  }
  .page-hero__rings {
    top: -280px;
    right: -260px;
  }
  .page-hero__index {
    right: 18px;
    font-size: 80px;
  }
}
</style>

<script setup lang="ts">
import { getGearAdvice, type GearAdvice } from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhEmpty, QhTag } from '@qh/ui';
import { computed, onMounted, ref } from 'vue';

const CITIES = ['西宁市', '海东市', '海南州', '海西州', '海北州', '黄南州', '果洛州', '玉树州'];

// 快照来源标识 → 展示名（openmeteo = 真实源；mock = 断网回退的模拟源）
const SOURCE_LABELS: Record<string, string> = {
  openmeteo: 'Open-Meteo 实时',
  mock: '模拟数据',
};

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

function todayStr(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function maxDateStr(): string {
  const future = new Date();
  future.setDate(future.getDate() + 7);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}`;
}

const city = ref('西宁市');
const day = ref(todayStr());
const advice = ref<GearAdvice | null>(null);
const loading = ref(false);
const error = ref('');

const metrics = computed(() => {
  const snapshot = advice.value?.snapshot;
  if (!snapshot) {
    return [];
  }
  return [
    { label: '气温', value: snapshot.temperature_c.toFixed(1), unit: '℃' },
    { label: '海拔', value: String(snapshot.altitude_m), unit: '米' },
    { label: '气压', value: snapshot.pressure_hpa.toFixed(1), unit: 'hPa' },
    { label: '土壤湿度', value: snapshot.soil_moisture_pct.toFixed(1), unit: '%' },
  ];
});

async function load() {
  loading.value = true;
  error.value = '';
  advice.value = null;
  try {
    advice.value = await getGearAdvice(city.value, day.value);
  } catch (err) {
    error.value =
      err instanceof Error ? err.message : '加载失败，请确认后端服务与采集任务已运行';
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageTitle
    title="行前装备建议"
    subtitle="结合实时气象、海拔与气压给出装备清单；环境数据每日定时采集"
  />

  <div class="filters">
    <select v-model="city" class="filters__city">
      <option v-for="item in CITIES" :key="item" :value="item">{{ item }}</option>
    </select>
    <input v-model="day" class="filters__date" type="date" :min="todayStr()" :max="maxDateStr()" />
    <QhButton @click="load">查看建议</QhButton>
  </div>

  <p v-if="error" class="state state--error">{{ error }}</p>
  <p v-else-if="loading" class="state">加载中…</p>

  <template v-else-if="advice">
    <div class="env-grid">
      <QhCard v-for="metric in metrics" :key="metric.label" class="env-card">
        <p class="env-card__label">{{ metric.label }}</p>
        <p class="env-card__value">
          {{ metric.value }}<span class="env-card__unit">{{ metric.unit }}</span>
        </p>
      </QhCard>
    </div>

    <div class="advice-layout">
      <QhCard class="advice-layout__list">
        <template #header>建议携带（{{ advice.city }} · {{ advice.date }}）</template>
        <QhEmpty v-if="advice.items.length === 0" text="暂无建议项" />
        <ul v-else class="items">
          <li v-for="item in advice.items" :key="item" class="items__item">{{ item }}</li>
        </ul>
      </QhCard>

      <QhCard class="advice-layout__notes">
        <template #header>注意事项</template>
        <p>{{ advice.notes || '暂无额外提示' }}</p>
        <div class="advice-layout__tags">
          <QhTag tone="default">数据源：{{ sourceLabel(advice.snapshot.source) }}</QhTag>
        </div>
      </QhCard>
    </div>
  </template>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--qh-space-3);
  margin-bottom: var(--qh-space-5);
}
.filters__city,
.filters__date {
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
  outline: none;
}
.filters__city:focus,
.filters__date:focus {
  border-color: var(--qh-primary);
}
.env-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--qh-space-4);
  margin-bottom: var(--qh-space-5);
}
.env-card__label {
  margin: 0 0 var(--qh-space-2);
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.env-card__value {
  margin: 0;
  font-size: 30px;
  font-weight: 700;
  color: var(--qh-ink);
  letter-spacing: -0.02em;
}
.env-card:first-child .env-card__value {
  color: var(--qh-primary);
}
.env-card__unit {
  font-size: var(--qh-fs-sm);
  font-weight: 500;
  color: var(--qh-muted);
  margin-left: 6px;
}
.advice-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--qh-space-4);
}
.advice-layout__notes {
  height: 100%;
}
.advice-layout__notes p {
  margin: 0 0 var(--qh-space-4);
  color: var(--qh-ink-2);
  line-height: 1.8;
}
.advice-layout__tags {
  display: flex;
  gap: var(--qh-space-2);
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--qh-space-3) var(--qh-space-4);
}
.items__item {
  position: relative;
  padding-left: var(--qh-space-4);
  color: var(--qh-ink-2);
  line-height: 1.6;
}
.items__item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 9px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--qh-accent);
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 900px) {
  .advice-layout {
    grid-template-columns: 1fr;
  }
}
</style>

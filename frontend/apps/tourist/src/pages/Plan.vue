<script setup lang="ts">
import { generateItinerary, listMyItineraries, type ItineraryPublic } from '@qh/api-client';
import { QhButton, QhCard, QhEmpty, QhInput, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';

import PageHero from '../components/PageHero.vue';

const router = useRouter();

const days = ref(3);
const budget = ref<string>('');
const preferences = ref('');
const fitness = ref('一般');
const generating = ref(false);
const error = ref('');

const itineraries = ref<ItineraryPublic[]>([]);
const loading = ref(true);

async function loadList() {
  loading.value = true;
  try {
    const data = await listMyItineraries();
    itineraries.value = data.items;
  } catch {
    /* 列表失败不打断生成表单 */
  } finally {
    loading.value = false;
  }
}

async function handleGenerate() {
  if (generating.value) {
    return;
  }
  error.value = '';
  generating.value = true;
  try {
    const detail = await generateItinerary({
      days: days.value,
      budget: budget.value ? Number(budget.value) : null,
      preferences: preferences.value,
      fitness: fitness.value,
    });
    void router.push(`/plan/${detail.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '生成失败';
  } finally {
    generating.value = false;
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

onMounted(loadList);
</script>

<template>
  <PageHero
    eyebrow="SMART PLANNING · 03"
    title="智能规划"
    subtitle="按天数、预算与偏好生成青海行程，生成后可继续调整停靠点"
    index="03"
  />

  <div class="layout">
    <div class="layout__main">
      <QhCard class="layout__card">
        <template #header>生成新行程</template>
        <div class="form">
          <label class="field">
            <span>行程天数（1–15 天）</span>
            <div class="days">
              <QhButton
                v-for="option in [2, 3, 5, 7]"
                :key="option"
                size="sm"
                :variant="days === option ? 'primary' : 'ghost'"
                @click="days = option"
              >
                {{ option }} 天
              </QhButton>
              <input v-model.number="days" class="days__input" type="number" min="1" max="15" />
            </div>
          </label>
          <label class="field">
            <span>预算（元，选填）</span>
            <QhInput v-model="budget" type="number" placeholder="如 3000" />
          </label>
          <label class="field">
            <span>偏好（选填）</span>
            <QhInput v-model="preferences" placeholder="如：想看湖、少爬山、喜欢人文" />
          </label>
          <label class="field">
            <span>体力情况</span>
            <select v-model="fitness" class="select">
              <option>较好</option>
              <option>一般</option>
              <option>较弱</option>
            </select>
          </label>
          <QhButton :disabled="generating" @click="handleGenerate">
            {{ generating ? '生成中…' : '生成行程' }}
          </QhButton>
          <p v-if="error" class="state state--error">{{ error }}</p>
        </div>
      </QhCard>

      <QhCard class="layout__card routes-tip">
        <template #header>没有头绪？</template>
        <p class="routes-tip__text">
          可以先看平台整理好的经典线路，看中哪条直接套用成自己的行程，再回到这里微调。
        </p>
        <RouterLink class="routes-tip__link" to="/routes">浏览精选路线 →</RouterLink>
      </QhCard>
    </div>

    <aside class="layout__side">
      <QhCard class="layout__fill">
        <template #header>我的行程</template>
        <QhEmpty v-if="!loading && itineraries.length === 0" text="还没有行程，先生成一个吧" />
        <ul v-else class="list">
          <li v-for="item in itineraries" :key="item.id">
            <RouterLink class="list__link" :to="`/plan/${item.id}`">
              <strong>{{ item.title }}</strong>
              <span class="list__meta">{{ formatTime(item.created_at) }}</span>
            </RouterLink>
          </li>
        </ul>
      </QhCard>
    </aside>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--qh-space-4);
}
.layout__card {
  height: 100%;
}
.routes-tip {
  height: auto;
  margin-top: var(--qh-space-4);
}
.routes-tip__text {
  margin: 0 0 var(--qh-space-3);
  color: var(--qh-ink-2);
  font-size: var(--qh-fs-sm);
  line-height: 1.7;
}
.routes-tip__link {
  color: var(--qh-primary);
  font-size: var(--qh-fs-sm);
  font-weight: 600;
}
.layout__fill {
  height: 100%;
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-4);
  max-width: 520px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-1);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
.days {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--qh-space-2);
}
.days__input {
  width: 72px;
  padding: 6px 10px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  font-family: inherit;
  font-size: var(--qh-fs-md);
}
.select {
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
  outline: none;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.list__link {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--qh-space-3) 0;
  border-bottom: 1px solid var(--qh-border);
  color: var(--qh-ink);
}
.list li:last-child .list__link {
  border-bottom: none;
}
.list__link:hover {
  text-decoration: none;
}
.list__link:hover strong {
  color: var(--qh-primary);
}
.list__meta {
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.state {
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

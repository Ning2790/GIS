<script setup lang="ts">
import { applyRoute, getRouteDetail, type RouteDetail } from '@qh/api-client';
import { QhButton, QhCard, QhTag } from '@qh/ui';
import { computed, onMounted, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const detail = ref<RouteDetail | null>(null);
const loading = ref(true);
const error = ref('');
const applying = ref(false);

/** 按天分组：[[{停靠点…}], [{…}]]，索引即第几天。 */
const days = computed(() => {
  if (!detail.value) {
    return [];
  }
  const grouped: RouteDetail['stops'][] = [];
  for (const stop of detail.value.stops) {
    (grouped[stop.day - 1] ??= []).push(stop);
  }
  return grouped;
});

async function load() {
  loading.value = true;
  error.value = '';
  try {
    detail.value = await getRouteDetail(Number(route.params.id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function handleApply() {
  if (!detail.value || applying.value) {
    return;
  }
  if (!auth.isLoggedIn) {
    void router.push({ name: 'login', query: { redirect: route.fullPath } });
    return;
  }
  error.value = '';
  applying.value = true;
  try {
    const itinerary = await applyRoute(detail.value.id);
    void router.push(`/plan/${itinerary.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '套用失败';
  } finally {
    applying.value = false;
  }
}

onMounted(load);
</script>

<template>
  <p class="back">
    <RouterLink to="/routes">← 返回精选路线</RouterLink>
  </p>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error && !detail" class="state state--error">{{ error }}</p>

  <template v-else-if="detail">
    <QhCard class="summary">
      <div class="summary__head">
        <h1 class="summary__name">{{ detail.name }}</h1>
        <QhTag tone="primary">{{ detail.theme || '主题' }}</QhTag>
      </div>
      <p class="summary__meta">
        <span>{{ detail.days }} 天行程</span>
        <span>{{ detail.stops.length }} 个停靠点</span>
        <span v-if="detail.total_distance_km != null">
          全程约 {{ detail.total_distance_km.toFixed(1) }} 公里
        </span>
        <span v-if="detail.budget">人均预估 ￥{{ detail.budget }}</span>
      </p>
      <p class="summary__desc">{{ detail.description }}</p>
      <div class="summary__actions">
        <QhButton :disabled="applying" @click="handleApply">
          {{ applying ? '套用中…' : '套用为我的行程' }}
        </QhButton>
        <span class="summary__hint">套用后可在「行程规划」里自由增删、调整顺序</span>
      </div>
      <p v-if="error" class="state state--error">{{ error }}</p>
    </QhCard>

    <QhCard v-for="(stops, index) in days" :key="index" class="day-card">
      <template #header>第 {{ index + 1 }} 天</template>
      <ol class="stops">
        <li v-for="stop in stops" :key="stop.id" class="stops__row">
          <span class="stops__dot" aria-hidden="true"></span>
          <div class="stops__body">
            <RouterLink
              v-if="stop.attraction_id"
              class="stops__name"
              :to="`/attractions/${stop.attraction_id}`"
            >
              {{ stop.attraction_name ?? `景点 #${stop.attraction_id}` }}
            </RouterLink>
            <span v-if="stop.city" class="stops__city">{{ stop.city }}</span>
            <p v-if="stop.note" class="stops__note">{{ stop.note }}</p>
          </div>
        </li>
      </ol>
    </QhCard>
  </template>
</template>

<style scoped>
.back {
  margin: 0 0 var(--qh-space-4);
  font-size: var(--qh-fs-sm);
}
.summary {
  margin-bottom: var(--qh-space-4);
}
.summary__head {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin-bottom: var(--qh-space-2);
}
.summary__name {
  margin: 0;
  font-size: var(--qh-fs-xl);
}
.summary__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--qh-space-3);
  margin: 0 0 var(--qh-space-3);
  color: var(--qh-primary);
  font-size: var(--qh-fs-sm);
  font-weight: 600;
}
.summary__desc {
  margin: 0 0 var(--qh-space-4);
  color: var(--qh-ink-2);
  line-height: 1.8;
  white-space: pre-line;
}
.summary__actions {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  flex-wrap: wrap;
}
.summary__hint {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.day-card {
  margin-bottom: var(--qh-space-4);
}
.stops {
  list-style: none;
  margin: 0;
  padding: 0;
}
.stops__row {
  display: flex;
  gap: var(--qh-space-3);
  padding: var(--qh-space-3) 0;
  border-bottom: 1px solid var(--qh-border);
}
.stops__row:last-child {
  border-bottom: none;
}
.stops__dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 8px;
  border-radius: 50%;
  background: var(--qh-primary);
}
.stops__body {
  min-width: 0;
}
.stops__name {
  font-weight: 600;
  color: var(--qh-ink);
}
.stops__name:hover {
  color: var(--qh-primary);
}
.stops__city {
  margin-left: var(--qh-space-2);
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.stops__note {
  margin: 2px 0 0;
  color: var(--qh-ink-2);
  font-size: var(--qh-fs-sm);
  line-height: 1.7;
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
</style>

<script setup lang="ts">
import { listRoutes, type RoutePublic } from '@qh/api-client';
import { QhCard, QhEmpty, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import PageHero from '../components/PageHero.vue';

const PAGE_SIZE = 12;

const routes = ref<RoutePublic[]>([]);
const total = ref(0);
const page = ref(1);
const theme = ref('');
const loading = ref(true);
const error = ref('');
// 主题列表取自「不带过滤」的一次加载，切换筛选时保持导航稳定
const allThemes = ref<string[]>([]);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listRoutes({
      theme: theme.value || undefined,
      page: page.value,
      page_size: PAGE_SIZE,
    });
    routes.value = data.items;
    total.value = data.total;
    if (!theme.value && page.value === 1) {
      allThemes.value = [...new Set(data.items.map((item) => item.theme).filter(Boolean))];
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

function switchTheme(next: string) {
  theme.value = theme.value === next ? '' : next;
  page.value = 1;
  void load();
}

onMounted(load);
</script>

<template>
  <PageHero
    eyebrow="ITINERARIES · 02"
    title="精选路线"
    subtitle="平台整理好的经典线路，看中哪条可以直接套用成自己的行程再自由调整"
    index="02"
  />

  <div class="filters">
    <button
      v-for="item in allThemes"
      :key="item"
      class="filters__chip"
      :class="{ 'filters__chip--on': theme === item }"
      @click="switchTheme(item)"
    >
      {{ item }}
    </button>
  </div>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>
  <QhEmpty v-else-if="routes.length === 0" text="暂无预设路线" />

  <div v-else class="grid">
    <RouterLink
      v-for="item in routes"
      :key="item.id"
      class="grid__link"
      :to="`/routes/${item.id}`"
    >
      <QhCard class="route-card">
        <div class="route-card__head">
          <h3 class="route-card__name">{{ item.name }}</h3>
          <QhTag tone="primary">{{ item.theme || '主题' }}</QhTag>
        </div>
        <p class="route-card__meta">
          <span>{{ item.days }} 天</span>
          <span>{{ item.stop_count }} 个停靠点</span>
          <span v-if="item.budget">人均约 ￥{{ item.budget }}</span>
        </p>
        <p class="route-card__desc">{{ item.description }}</p>
        <span class="route-card__more">查看每日安排 →</span>
      </QhCard>
    </RouterLink>
  </div>

  <QhPagination
    v-if="total > PAGE_SIZE"
    :page="page"
    :page-size="PAGE_SIZE"
    :total="total"
    @change="(next: number) => { page = next; void load(); }"
  />
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
}
.filters__chip {
  padding: 6px 16px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 999px;
  background: transparent;
  color: var(--tourist-ink-2, #334155);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    color 0.15s ease,
    background 0.15s ease;
}
.filters__chip:hover {
  border-color: var(--tourist-cyan, #0891b2);
  color: var(--tourist-cyan, #0891b2);
}
.filters__chip--on {
  border-color: var(--tourist-ink, #0b1220);
  background: var(--tourist-ink, #0b1220);
  color: #fff;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 20px;
}
.grid__link {
  color: inherit;
}
.grid__link:hover {
  text-decoration: none;
}
.route-card.qh-card {
  position: relative;
  height: 100%;
  overflow: hidden;
  padding: 24px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 18px;
  background: var(--tourist-surface, #fffdfa);
  box-shadow: none;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}
.route-card::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--tourist-cyan, #0891b2), var(--tourist-sand, #d6b27a));
}
.grid__link:hover .route-card.qh-card {
  transform: translateY(-4px);
  border-color: rgba(8, 145, 178, 0.3);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
}
.route-card__head {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--qh-space-3);
  margin-bottom: 10px;
}
.route-card__name {
  margin: 0;
  padding-right: 40px;
  color: var(--tourist-ink, #0b1220);
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 21px;
  font-weight: 700;
  letter-spacing: 0.03em;
  line-height: 1.4;
}
.route-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--qh-space-1) var(--qh-space-3);
  margin: 0 0 14px;
  color: var(--tourist-cyan, #0891b2);
  font-size: 12px;
  font-weight: 600;
}
.route-card__meta span + span::before {
  content: '·';
  margin-right: var(--qh-space-3);
  color: var(--tourist-muted, #6b7280);
}
.route-card__desc {
  display: -webkit-box;
  overflow: hidden;
  margin: 0 0 18px;
  color: var(--tourist-muted, #6b7280);
  font-size: 13px;
  line-height: 1.75;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.route-card__more {
  color: var(--tourist-cyan, #0891b2);
  font-size: 12px;
  font-weight: 600;
}
.state {
  color: var(--tourist-muted, #6b7280);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .route-card {
    padding: 20px;
  }
}
</style>

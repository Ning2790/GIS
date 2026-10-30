<script setup lang="ts">
import { listAttractions, type AttractionPublic } from '@qh/api-client';
import { QhButton, QhCard, QhEmpty, QhInput, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink, useRoute } from 'vue-router';

import PageHero from '../components/PageHero.vue';
import { ATTRACTION_COVERS } from '../data/attractionMedia';

const CITIES = ['西宁市', '海东市', '海南州', '海西州', '海北州', '黄南州', '果洛州', '玉树州'];
const PAGE_SIZE = 12;

const route = useRoute();
const items = ref<AttractionPublic[]>([]);
const total = ref(0);
const page = ref(1);
const city = ref(typeof route.query.city === 'string' ? route.query.city : '');
const keyword = ref(typeof route.query.keyword === 'string' ? route.query.keyword : '');
const loading = ref(false);
const error = ref('');

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listAttractions({
      city: city.value || undefined,
      keyword: keyword.value || undefined,
      page: page.value,
      page_size: PAGE_SIZE,
    });
    items.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  void load();
}

function changePage(next: number) {
  page.value = next;
  void load();
}

/** 景点实景封面（按名称映射；后端未来上传 cover_image 时优先用后端的）。 */
function coverOf(item: AttractionPublic): string {
  return ATTRACTION_COVERS[item.name] ?? item.cover_image ?? '';
}

/** 没有实景图时的兜底封面（按 id 分布青/蓝色相）。 */
function coverStyle(id: number) {
  const hue = 188 + ((id * 31) % 38);
  return {
    background: `linear-gradient(150deg, hsl(${hue} 42% 22%), hsl(${(hue + 26) % 360} 52% 40%))`,
  };
}

onMounted(load);
</script>

<template>
  <PageHero
    eyebrow="DESTINATIONS · 01"
    title="景点概览"
    subtitle="按城市与关键词浏览，点击卡片查看详情与门票"
    index="01"
  />

  <div class="filters">
    <select v-model="city" class="filters__city" aria-label="筛选城市" @change="search">
      <option value="">全部城市</option>
      <option v-for="item in CITIES" :key="item" :value="item">{{ item }}</option>
    </select>
    <QhInput
      v-model="keyword"
      class="filters__search"
      placeholder="搜索景点名称"
      @keyup.enter="search"
    />
    <QhButton @click="search">搜索</QhButton>
  </div>

  <p v-if="error" class="state state--error">{{ error }}</p>
  <div v-else-if="loading" class="grid" role="status" aria-busy="true" aria-label="正在加载景点">
    <div v-for="n in PAGE_SIZE" :key="n" class="skeleton" aria-hidden="true">
      <div class="skeleton__cover"></div>
      <div class="skeleton__body">
        <span class="skeleton__line skeleton__line--title"></span>
        <span class="skeleton__line"></span>
        <span class="skeleton__line skeleton__line--short"></span>
        <span class="skeleton__line skeleton__line--more"></span>
      </div>
    </div>
  </div>
  <QhEmpty v-else-if="items.length === 0" text="没有找到符合条件的景点" />
  <div v-else class="grid">
    <RouterLink
      v-for="(item, index) in items"
      :key="item.id"
      class="grid__link"
      :to="`/attractions/${item.id}`"
    >
      <QhCard class="attraction" padding="none">
        <div class="attraction__cover" :style="coverStyle(item.id)">
          <img
            v-if="coverOf(item)"
            :src="coverOf(item)"
            :alt="item.name"
            class="attraction__img"
            loading="lazy"
          />
          <span v-else class="attraction__glyph" aria-hidden="true">
            {{ item.name.slice(0, 1) }}
          </span>
          <span class="attraction__num">
            {{ String((page - 1) * PAGE_SIZE + index + 1).padStart(2, '0') }}
          </span>
          <QhTag class="attraction__city" tone="default">{{ item.city }}</QhTag>
        </div>
        <div class="attraction__body">
          <h3>{{ item.name }}</h3>
          <p>{{ item.description || '暂无简介' }}</p>
          <span class="attraction__more">查看详情 →</span>
        </div>
      </QhCard>
    </RouterLink>
  </div>

  <QhPagination
    v-if="!loading && total > PAGE_SIZE"
    :page="page"
    :page-size="PAGE_SIZE"
    :total="total"
    @change="changePage"
  />
  <div v-else-if="loading" class="pagination-placeholder" aria-hidden="true"></div>

  <p class="credits">
    景点图片来自 Wikimedia Commons 与公开网络，
    <a href="/attraction-credits.html" target="_blank" rel="noreferrer">查看来源与授权</a>
  </p>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  padding: 14px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 16px;
  background: var(--tourist-surface, #fffdfa);
}
.filters__city {
  width: 144px;
  padding: 9px 12px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 10px;
  background: #fff;
  color: var(--tourist-ink, #0b1220);
  font-family: inherit;
  font-size: var(--qh-fs-md);
  outline: none;
}
.filters__city:focus {
  border-color: var(--tourist-cyan, #0891b2);
}
.filters__search {
  flex: 1;
  min-width: 180px;
  max-width: 320px;
}
.state {
  color: var(--tourist-muted, #6b7280);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
.credits {
  margin: 28px 0 0;
  color: var(--tourist-muted, #6b7280);
  font-size: 11px;
  text-align: center;
}
.credits a {
  color: var(--tourist-cyan, #0891b2);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
}
.grid__link:hover {
  text-decoration: none;
}
/* 加载骨架与卡片同高，避免切页时列表撑开造成页面抖动 */
.skeleton {
  box-sizing: border-box;
  height: 329px;
  overflow: hidden;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 18px;
  background: var(--tourist-surface, #fffdfa);
}
.skeleton__cover {
  height: 170px;
  background: linear-gradient(100deg, #eee7dc 25%, #f8f3eb 50%, #eee7dc 75%);
  background-size: 220% 100%;
  animation: skeleton-shimmer 1.6s ease-in-out infinite;
}
.skeleton__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
}
.skeleton__line {
  display: block;
  height: 12px;
  border-radius: 6px;
  background: #eee7dc;
}
.skeleton__line--title {
  width: 62%;
  height: 20px;
}
.skeleton__line--short {
  width: 72%;
}
.skeleton__line--more {
  width: 32%;
  margin-top: 8px;
}
.pagination-placeholder {
  height: 28px;
  margin-top: 24px;
}
@keyframes skeleton-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}
.attraction.qh-card {
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 18px;
  background: var(--tourist-surface, #fffdfa);
  box-shadow: none;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}
.attraction.qh-card:hover {
  transform: translateY(-4px);
  border-color: rgba(8, 145, 178, 0.3);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
}
.attraction__cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 170px;
  overflow: hidden;
}
.attraction__cover::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(0deg, rgba(4, 12, 24, 0.62), transparent 65%);
  pointer-events: none;
}
.attraction__img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s ease;
}
.attraction:hover .attraction__img {
  transform: scale(1.05);
}
.attraction__glyph {
  position: absolute;
  right: 8px;
  bottom: -18px;
  color: rgba(248, 250, 252, 0.16);
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 128px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}
.attraction__num {
  position: absolute;
  top: 14px;
  left: 18px;
  z-index: 1;
  color: rgba(255, 255, 255, 0.82);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
}
.attraction__city {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 1;
}
.attraction__body {
  padding: 18px 20px 20px;
}
.attraction__body h3 {
  margin: 0 0 8px;
  color: var(--tourist-ink, #0b1220);
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.attraction__body p {
  display: -webkit-box;
  overflow: hidden;
  margin: 0 0 14px;
  color: var(--tourist-muted, #6b7280);
  font-size: 13px;
  line-height: 1.7;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.attraction__more {
  color: var(--tourist-cyan, #0891b2);
  font-size: 12px;
  font-weight: 600;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: 12px;
  }
  .skeleton {
    height: 274px;
  }
  .skeleton__cover {
    height: 130px;
  }
  .skeleton__body {
    gap: 8px;
    padding: 16px 14px;
  }
  .skeleton__line--title {
    height: 18px;
  }
  .attraction__cover {
    height: 130px;
  }
  .attraction__glyph {
    font-size: 96px;
  }
  .attraction__cover-name {
    font-size: 18px;
  }
  .attraction__body {
    padding: 14px;
  }
  .attraction__body h3 {
    font-size: 17px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton__cover {
    animation: none;
  }
}
</style>

<script setup lang="ts">
import { listHotKeywords, listProducts, type HotKeyword, type ProductPublic } from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhEmpty, QhInput, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

const PAGE_SIZE = 12;

const items = ref<ProductPublic[]>([]);
const total = ref(0);
const page = ref(1);
const keyword = ref('');
// 排序与价格区间（后端下推 SQL；空值不传）
const sort = ref<'newest' | 'price_asc' | 'price_desc'>('newest');
const minPrice = ref<number | undefined>(undefined);
const maxPrice = ref<number | undefined>(undefined);
const loading = ref(false);
const error = ref('');
// 搜索热词（Redis 累计，未配置时为空表 → 不渲染这一行）
const hotKeywords = ref<HotKeyword[]>([]);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listProducts({
      keyword: keyword.value || undefined,
      sort: sort.value === 'newest' ? undefined : sort.value,
      min_price: minPrice.value,
      max_price: maxPrice.value,
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

/** 点热词：填入搜索框并立即搜索。 */
function useHotKeyword(word: string) {
  keyword.value = word;
  search();
}

/** 排序 / 价格区间变化：回到第一页重新拉取（与搜索同一入口）。 */
function applyFilters() {
  search();
}

function resetFilters() {
  sort.value = 'newest';
  minPrice.value = undefined;
  maxPrice.value = undefined;
  keyword.value = '';
  search();
}

function changePage(next: number) {
  page.value = next;
  void load();
}

/** 无商品图时的风格化封面（按 id 分布青/蓝色相）。 */
function coverStyle(id: number) {
  const hue = 185 + ((id * 47) % 45);
  return {
    background: `linear-gradient(150deg, hsl(${hue} 45% 26%), hsl(${(hue + 26) % 360} 52% 42%))`,
  };
}

onMounted(async () => {
  await load();
  try {
    hotKeywords.value = await listHotKeywords(8);
  } catch {
    hotKeywords.value = []; // 热词是增强项：拿不到就不显示
  }
});
</script>

<template>
  <PageTitle
    size="large"
    title="特产商城"
    subtitle="青海特产直购：牦牛肉干、青稞、黑枸杞与高原菜籽油"
  />

  <div class="filters">
    <div class="filters__search-row">
      <QhInput
        v-model="keyword"
        class="filters__search"
        placeholder="搜索商品名称"
        @keyup.enter="search"
      />
      <QhButton @click="search">搜索</QhButton>
    </div>
    <div class="filters__row">
      <select v-model="sort" class="filters__select" aria-label="排序方式" @change="applyFilters">
        <option value="newest">最新上架</option>
        <option value="price_asc">价格从低到高</option>
        <option value="price_desc">价格从高到低</option>
      </select>
      <input
        v-model.number="minPrice"
        class="filters__price"
        type="number"
        min="0"
        placeholder="最低价"
        aria-label="最低价"
        @keyup.enter="applyFilters"
      />
      <span class="filters__dash">–</span>
      <input
        v-model.number="maxPrice"
        class="filters__price"
        type="number"
        min="0"
        placeholder="最高价"
        aria-label="最高价"
        @keyup.enter="applyFilters"
      />
      <QhButton variant="ghost" @click="applyFilters">筛选</QhButton>
      <QhButton variant="ghost" @click="resetFilters">重置</QhButton>
    </div>
  </div>

  <p v-if="hotKeywords.length > 0" class="hot">
    <span class="hot__label">热门搜索</span>
    <button
      v-for="item in hotKeywords"
      :key="item.keyword"
      type="button"
      class="hot__item"
      @click="useHotKeyword(item.keyword)"
    >
      {{ item.keyword }}
    </button>
  </p>

  <p v-if="error" class="state state--error">{{ error }}</p>
  <p v-else-if="loading" class="state">加载中…</p>
  <QhEmpty v-else-if="items.length === 0" text="没有找到符合条件的商品" />
  <div v-else class="grid">
    <RouterLink
      v-for="(item, index) in items"
      :key="item.id"
      class="grid__link"
      :to="`/products/${item.id}`"
    >
      <QhCard class="product" padding="none">
        <div class="product__cover" :style="item.image_url ? undefined : coverStyle(item.id)">
          <img
            v-if="item.image_url"
            :src="item.image_thumbnail_url ?? item.image_url"
            :alt="item.name"
            class="product__img"
            loading="lazy"
          />
          <span v-else class="product__cover-name">{{ item.name }}</span>
          <span class="product__index">{{ String(index + 1).padStart(2, '0') }}</span>
        </div>
        <div class="product__body">
          <h3>{{ item.name }}</h3>
          <p class="product__desc">{{ item.description || '暂无简介' }}</p>
          <div class="product__foot">
            <span class="product__price">￥{{ item.price }}</span>
            <QhTag :tone="item.stock > 0 ? 'default' : 'danger'">库存 {{ item.stock }}</QhTag>
          </div>
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
</template>

<style scoped>
.filters {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 16px;
  background: var(--tourist-surface, #fffdfa);
}
.filters__search-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.filters__search {
  flex: 1;
  max-width: 420px;
}
.filters__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.filters__select,
.filters__price {
  padding: 8px 10px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 10px;
  background: #fff;
  color: var(--tourist-ink, #0b1220);
  font-size: 13px;
}
.filters__price {
  width: 96px;
}
.filters__dash {
  color: var(--tourist-muted, #6b7280);
}
.hot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 20px;
  font-size: var(--qh-fs-sm);
}
.hot__label {
  color: var(--tourist-muted, #6b7280);
}
.hot__item {
  padding: 4px 12px;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 999px;
  background: transparent;
  color: var(--tourist-cyan, #0891b2);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background 0.15s ease;
}
.hot__item:hover {
  border-color: var(--tourist-cyan, #0891b2);
  background: rgba(8, 145, 178, 0.06);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
}
.grid__link:hover {
  text-decoration: none;
}
.product.qh-card {
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
.product.qh-card:hover {
  transform: translateY(-4px);
  border-color: rgba(8, 145, 178, 0.3);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
}
.product__cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 190px;
  overflow: hidden;
  background: #e9e4da;
}
.product__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s ease;
}
.product:hover .product__img {
  transform: scale(1.05);
}
.product__cover-name {
  padding: 0 var(--qh-space-3);
  color: #fff;
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: var(--qh-fs-lg);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-align: center;
}
.product__index {
  position: absolute;
  top: 12px;
  left: 14px;
  color: rgba(255, 255, 255, 0.78);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.16em;
}
.product__body {
  padding: 16px 18px 20px;
}
.product__body h3 {
  display: -webkit-box;
  overflow: hidden;
  min-height: 44px;
  margin: 0 0 8px;
  color: var(--tourist-ink, #0b1220);
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.03em;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.product__desc {
  display: -webkit-box;
  overflow: hidden;
  margin: 0 0 14px;
  color: var(--tourist-muted, #6b7280);
  font-size: 12.5px;
  line-height: 1.7;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.product__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-2);
}
.product__price {
  color: var(--tourist-cyan, #0891b2);
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 22px;
  font-weight: 700;
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
    grid-template-columns: repeat(auto-fill, minmax(165px, 1fr));
    gap: 12px;
  }
  .product__cover {
    height: 140px;
  }
  .product__body {
    padding: 13px 14px 16px;
  }
  .product__body h3 {
    font-size: 16px;
  }
  .product__price {
    font-size: 19px;
  }
}
</style>

<script setup lang="ts">
import { listFavorites, type ProductPublic } from '@qh/api-client';
import { PageTitle, QhButton, QhEmpty, QhPagination } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import ProductCard from '../components/ProductCard.vue';

const PAGE_SIZE = 12;

const items = ref<ProductPublic[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(true);
const error = ref('');

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const result = await listFavorites(page.value, PAGE_SIZE);
    items.value = result.items;
    total.value = result.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

function changePage(next: number) {
  page.value = next;
  load();
}

onMounted(load);
</script>

<template>
  <PageTitle title="我的收藏" subtitle="点过心动的青海特产都在这里，可随时进入详情下单" />

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">
    {{ error }}
    <QhButton size="sm" variant="ghost" @click="load">重试</QhButton>
  </p>

  <QhEmpty v-else-if="items.length === 0" text="还没有收藏，去商城逛逛吧">
    <RouterLink to="/products"><QhButton size="sm">去商城 →</QhButton></RouterLink>
  </QhEmpty>

  <template v-else>
    <p class="count">共 {{ total }} 件</p>
    <div class="grid">
      <!-- 已下架商品不再给详情链接（详情接口对下架商品返回 404） -->
      <RouterLink
        v-for="item in items"
        :key="item.id"
        class="grid__link"
        :to="item.status === 'on_sale' ? `/products/${item.id}` : ''"
        :class="{ 'grid__link--disabled': item.status !== 'on_sale' }"
        @click="item.status !== 'on_sale' && $event.preventDefault()"
      >
        <ProductCard :product="item" show-status />
      </RouterLink>
    </div>
    <QhPagination
      v-if="total > PAGE_SIZE"
      :page="page"
      :page-size="PAGE_SIZE"
      :total="total"
      @change="changePage"
    />
  </template>
</template>

<style scoped>
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger, #dc2626);
}
.count {
  margin: 0 0 var(--qh-space-3);
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--qh-space-4);
}
.grid__link:hover {
  text-decoration: none;
}
.grid__link--disabled {
  cursor: default;
}
</style>

<script setup lang="ts">
import { clearHistory, listHistory, type ProductPublic } from '@qh/api-client';
import { PageTitle, QhButton, QhEmpty, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import ProductCard from '../components/ProductCard.vue';

const PAGE_SIZE = 12;

const items = ref<ProductPublic[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(true);
const error = ref('');
const message = ref('');
const clearing = ref(false);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const result = await listHistory(page.value, PAGE_SIZE);
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

async function clearAll() {
  clearing.value = true;
  message.value = '';
  try {
    const result = await clearHistory();
    items.value = [];
    total.value = 0;
    page.value = 1;
    message.value = `已清空 ${result.deleted} 条浏览记录`;
  } catch (err) {
    message.value = err instanceof Error ? err.message : '清空失败';
  } finally {
    clearing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageTitle title="浏览历史" subtitle="最近看过的商品（同一件只记一次，重复浏览会刷新时间）" />

  <p v-if="items.length > 0" class="actions">
    <QhButton size="sm" variant="ghost" :disabled="clearing" @click="clearAll">
      {{ clearing ? '清空中…' : '清空历史' }}
    </QhButton>
  </p>

  <p v-if="message" class="state"><QhTag tone="primary">{{ message }}</QhTag></p>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">
    {{ error }}
    <QhButton size="sm" variant="ghost" @click="load">重试</QhButton>
  </p>

  <QhEmpty v-else-if="items.length === 0" text="还没有浏览记录，看过的商品会自动出现在这里">
    <RouterLink to="/products"><QhButton size="sm">去商城 →</QhButton></RouterLink>
  </QhEmpty>

  <template v-else>
    <p class="count">共 {{ total }} 件</p>
    <div class="grid">
      <RouterLink
        v-for="item in items"
        :key="item.id"
        class="grid__link"
        :to="`/products/${item.id}`"
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
.actions {
  margin: 0 0 var(--qh-space-3);
}
.state {
  margin: 0 0 var(--qh-space-3);
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
</style>

<script setup lang="ts">
/** 我的售后（需求 2.3）：申请后在此跟踪商户处理进度。 */

import { ApiError, listAfterSales, type AfterSalePublic } from '@qh/api-client';
import { PageTitle, QhCard, QhEmpty, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

const PAGE_SIZE = 10;
const items = ref<AfterSalePublic[]>([]);
const total = ref(0);
const page = ref(1);
const status = ref('');
const loading = ref(true);
const error = ref('');

const REASON_LABEL: Record<string, string> = {
  quality: '质量问题',
  missing: '少发 / 漏发',
  mismatch: '与描述不符',
  damaged: '包装 / 商品破损',
  other: '其他',
};

type QhTone = 'default' | 'primary' | 'danger' | 'success' | 'warning';

const STATUS_INFO: Record<string, { text: string; tone: QhTone }> = {
  pending: { text: '待商户处理', tone: 'warning' },
  processing: { text: '处理中', tone: 'primary' },
  resolved: { text: '已解决', tone: 'success' },
  rejected: { text: '已拒绝', tone: 'danger' },
  withdrawn: { text: '已撤销', tone: 'default' },
};

function statusInfo(value: string): { text: string; tone: QhTone } {
  return STATUS_INFO[value] ?? { text: value, tone: 'default' };
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listAfterSales(page.value, PAGE_SIZE, status.value || undefined);
    items.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

function changePage(next: number) {
  page.value = next;
  void load();
}

onMounted(load);
</script>

<template>
  <PageTitle title="我的售后" subtitle="申请后在此跟踪商户处理进度；需要即时沟通可用在线客服" />

  <div class="filters">
    <select v-model="status" class="filters__select" @change="page = 1; load()">
      <option value="">全部状态</option>
      <option value="pending">待商户处理</option>
      <option value="processing">处理中</option>
      <option value="resolved">已解决</option>
      <option value="rejected">已拒绝</option>
      <option value="withdrawn">已撤销</option>
    </select>
  </div>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>
  <QhEmpty v-else-if="items.length === 0" text="还没有售后记录（可在订单详情里申请售后）" />
  <div v-else class="list">
    <RouterLink v-for="item in items" :key="item.id" class="list__link" :to="`/after-sales/${item.id}`">
      <QhCard class="list__row">
        <div class="list__main">
          <strong>售后 #{{ item.id }}</strong>
          <span class="list__order">订单 #{{ item.order_id }}</span>
          <span class="list__reason">{{ REASON_LABEL[item.reason] ?? item.reason }}</span>
          <span class="list__time">{{ formatTime(item.created_at) }}</span>
        </div>
        <QhTag :tone="statusInfo(item.status).tone">{{ statusInfo(item.status).text }}</QhTag>
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
  justify-content: flex-end;
  margin-bottom: var(--qh-space-4);
}
.filters__select {
  padding: 8px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-sm);
}
.list {
  display: grid;
  gap: var(--qh-space-3);
}
.list__link:hover {
  text-decoration: none;
}
.list__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-4);
}
.list__main {
  display: flex;
  align-items: baseline;
  gap: var(--qh-space-3);
  flex-wrap: wrap;
}
.list__order,
.list__reason,
.list__time {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
</style>

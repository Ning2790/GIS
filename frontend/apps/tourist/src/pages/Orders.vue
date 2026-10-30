<script setup lang="ts">
import { listMyOrders, type OrderPublic } from '@qh/api-client';
import { PageTitle, QhCard, QhEmpty, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

const PAGE_SIZE = 10;

const items = ref<OrderPublic[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(true);
const error = ref('');

const STATUS_MAP: Record<string, { text: string; tone: 'warning' | 'success' | 'default' }> = {
  created: { text: '待支付', tone: 'warning' },
  paid: { text: '已支付', tone: 'success' },
  shipped: { text: '已发货', tone: 'success' },
  completed: { text: '已完成', tone: 'default' },
  cancelled: { text: '已取消', tone: 'default' },
};

function statusOf(order: { status: string; cancel_reason: string | null }) {
  if (order.status === 'cancelled' && order.cancel_reason === 'expired') {
    return { text: '已取消（超时未支付）', tone: 'default' as const };
  }
  return STATUS_MAP[order.status] ?? { text: order.status, tone: 'default' as const };
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listMyOrders(page.value, PAGE_SIZE);
    items.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
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
  <PageTitle title="我的订单" subtitle="下单与支付记录（支付为占位流程，由管理员模拟回调）" />

  <p v-if="error" class="state state--error">{{ error }}</p>
  <p v-else-if="loading" class="state">加载中…</p>
  <QhEmpty v-else-if="items.length === 0" text="还没有订单" />
  <div v-else class="orders">
    <RouterLink v-for="order in items" :key="order.id" class="orders__link" :to="`/orders/${order.id}`">
      <QhCard class="orders__row">
        <div class="orders__main">
          <strong>订单 #{{ order.id }}</strong>
          <span class="orders__time">{{ formatTime(order.created_at) }}</span>
          <span v-if="order.status === 'created' && order.expire_at" class="orders__deadline">
            {{ formatTime(order.expire_at) }} 前未支付将自动取消
          </span>
        </div>
        <span class="orders__amount">￥{{ order.amount }}</span>
        <QhTag :tone="statusOf(order).tone">{{ statusOf(order).text }}</QhTag>
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
.orders {
  display: grid;
  gap: var(--qh-space-3);
}
.orders__link:hover {
  text-decoration: none;
}
.orders__row {
  display: flex;
  align-items: center;
  gap: var(--qh-space-5);
  transition: box-shadow 0.15s ease;
}
.orders__row:hover {
  box-shadow: var(--qh-shadow);
}
.orders__main {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: var(--qh-space-3);
}
.orders__time {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.orders__deadline {
  color: var(--qh-warning);
  font-size: var(--qh-fs-xs);
}
.orders__amount {
  font-weight: 700;
  color: var(--qh-primary);
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
</style>

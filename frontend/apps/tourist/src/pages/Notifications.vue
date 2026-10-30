<script setup lang="ts">
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationPublic,
} from '@qh/api-client';
import { PageTitle, QhButton, QhEmpty, QhPagination, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useNotificationsStore } from '../stores/notifications';

const PAGE_SIZE = 10;

const router = useRouter();
const store = useNotificationsStore();

const items = ref<NotificationPublic[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(true);
const error = ref('');
// 操作类错误（标已读 / 全部已读）单独维护：不能把列表整页替换成「加载失败」
const actionError = ref('');

const TYPE_LABEL: Record<string, string> = {
  'order.paid': '订单支付',
  'order.shipped': '订单发货',
  'after_sale.created': '售后申请',
  'after_sale.resolved': '售后完成',
  'after_sale.rejected': '售后拒绝',
  'payment.exception': '支付异常',
  'payment.refunded': '支付退款',
};

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listNotifications(page.value, PAGE_SIZE);
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

/** 通知指向的业务详情页（没有关联对象就只读）。 */
function targetOf(item: NotificationPublic): string | null {
  if (item.ref_type === 'order' && item.ref_id) {
    return `/orders/${item.ref_id}`;
  }
  if (item.ref_type === 'after_sale' && item.ref_id) {
    return `/after-sales/${item.ref_id}`;
  }
  return null;
}

async function open(item: NotificationPublic) {
  if (!item.is_read) {
    try {
      await markNotificationRead(item.id);
      item.is_read = true;
      // 以服务端为准刷新角标：本地减一在多标签 / 跨设备场景会算错
      void store.refresh();
    } catch {
      // 标已读失败不阻断查看详情
    }
  }
  const target = targetOf(item);
  if (target) {
    void router.push(target);
  }
}

async function readAll() {
  actionError.value = '';
  try {
    await markAllNotificationsRead();
    items.value.forEach((item) => {
      item.is_read = true;
    });
    store.setUnread(0);
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '操作失败';
  }
}

onMounted(() => {
  void load();
  void store.refresh();
});
</script>

<template>
  <PageTitle title="消息通知" subtitle="订单支付、发货与售后进展都会在这里提醒你" />

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">
    {{ error }}
    <QhButton size="sm" variant="ghost" @click="load">重试</QhButton>
  </p>

  <QhEmpty v-else-if="items.length === 0" text="还没有通知，有新进展时会在这里提醒你" />

  <template v-else>
    <div class="toolbar">
      <span class="toolbar__count">共 {{ total }} 条 · 未读 {{ store.unread }} 条</span>
      <QhButton v-if="store.unread > 0" size="sm" variant="ghost" @click="readAll">
        全部标为已读
      </QhButton>
    </div>
    <p v-if="actionError" class="state state--error">{{ actionError }}</p>

    <ul class="list">
      <li v-for="item in items" :key="item.id" class="item" :class="{ 'item--unread': !item.is_read }">
        <button type="button" class="item__button" @click="open(item)">
          <div class="item__head">
            <span v-if="!item.is_read" class="item__dot" aria-label="未读" />
            <strong class="item__title">{{ item.title }}</strong>
            <QhTag tone="default">{{ TYPE_LABEL[item.type] ?? item.type }}</QhTag>
          </div>
          <p class="item__content">{{ item.content }}</p>
          <span class="item__time">{{ formatTime(item.created_at) }}</span>
        </button>
      </li>
    </ul>

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
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--qh-space-3);
}
.toolbar__count {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.list {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.item {
  border: 1px solid var(--qh-border, #e5e7eb);
  border-radius: var(--qh-radius, 10px);
  background: #fff;
}
.item--unread {
  border-color: var(--qh-accent, #0891b2);
  background: #f0fdff;
}
.item__button {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: var(--qh-space-3) var(--qh-space-4);
  border: none;
  background: none;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.item__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.item__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--qh-accent, #0891b2);
  flex: none;
}
.item__title {
  font-size: var(--qh-fs-md);
}
.item__content {
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.item__time {
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs, 12px);
}
</style>

<script setup lang="ts">
import {
  ApiError,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationPublic,
} from '@qh/api-client';
import { ElMessage } from 'element-plus';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useNotificationsStore } from '../stores/notifications';

const PAGE_SIZE = 10;

const router = useRouter();
const store = useNotificationsStore();

const rows = ref<NotificationPublic[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(false);
const error = ref('');
const markingAll = ref(false);

const TYPE_LABEL: Record<string, string> = {
  'order.paid': '订单支付',
  'order.shipped': '订单发货',
  'after_sale.created': '售后申请',
  'after_sale.resolved': '售后完成',
  'after_sale.rejected': '售后拒绝',
  'payment.exception': '支付异常',
  'payment.refunded': '支付退款',
};

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listNotifications(page.value, PAGE_SIZE);
    rows.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

/** 通知指向的业务列表（控制台没有按 id 直达详情，文案如实说明去哪儿）。 */
function targetOf(row: NotificationPublic): string | null {
  if (row.ref_type === 'order' && row.ref_id) {
    return `/orders?focus=${row.ref_id}`;
  }
  if (row.ref_type === 'after_sale' && row.ref_id) {
    return `/after-sales?focus=${row.ref_id}`;
  }
  return null;
}

function actionLabel(row: NotificationPublic): string {
  if (row.ref_type === 'order') {
    return '去订单列表';
  }
  if (row.ref_type === 'after_sale') {
    return '去售后列表';
  }
  return '标为已读';
}

async function open(row: NotificationPublic) {
  if (!row.is_read) {
    try {
      await markNotificationRead(row.id);
      row.is_read = true;
      // 以服务端为准刷新角标：本地减一在多标签 / 跨设备场景会算错
      void store.refresh();
    } catch (err) {
      ElMessage.error(err instanceof ApiError ? err.message : '标记已读失败');
      return;
    }
  }
  const target = targetOf(row);
  if (target) {
    void router.push(target);
  }
}

async function readAll() {
  markingAll.value = true;
  try {
    const { updated } = await markAllNotificationsRead();
    rows.value.forEach((row) => {
      row.is_read = true;
    });
    store.setUnread(0);
    ElMessage.success(updated > 0 ? `已将 ${updated} 条通知标为已读` : '没有未读通知');
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  } finally {
    markingAll.value = false;
  }
}

onMounted(() => {
  void load();
  void store.refresh();
});
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>消息通知</span>
        <span class="head__right">
          <el-tag v-if="store.unread > 0" size="small" type="warning">未读 {{ store.unread }}</el-tag>
          <el-button
            link
            type="primary"
            :loading="markingAll"
            :disabled="store.unread === 0"
            @click="readAll"
          >
            全部标为已读
          </el-button>
        </span>
      </div>
    </template>
    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />
    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_read ? 'info' : 'warning'" size="small">
            {{ row.is_read ? '已读' : '未读' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ TYPE_LABEL[row.type] ?? row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="内容" min-width="320">
        <template #default="{ row }">
          <strong>{{ row.title }}</strong>
          <p class="content">{{ row.content }}</p>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130">
        <template #default="{ row }">
          <el-button link type="primary" @click="open(row)">
            {{ actionLabel(row) }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        layout="prev, pager, next, total"
        :total="total"
        :page-size="PAGE_SIZE"
        :current-page="page"
        @current-change="(next: number) => { page = next; load(); }"
      />
    </div>
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.head__right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.content {
  margin: 2px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>

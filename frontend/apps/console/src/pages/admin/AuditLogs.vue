<script setup lang="ts">
import { listAuditLogs, type AuditLogPublic } from '@qh/api-client';
import { onMounted, ref } from 'vue';

const rows = ref<AuditLogPublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const loading = ref(false);
const error = ref('');
const actionFilter = ref('');
const targetTypeFilter = ref('');
const targetFilter = ref<string>('');

const ACTION_LABEL: Record<string, string> = {
  'review.approve': '审核通过',
  'review.reject': '审核驳回',
  'user.disable': '禁用用户',
  'user.enable': '启用用户',
  'order.cancel': '取消订单',
  'order.expire': '订单超时取消',
  'order.ship': '订单发货',
  'order.deliver': '标记签收',
  'order.receive': '确认收货',
  'order.auto_confirm': '自动确认收货',
  'payment.callback': '支付回调',
  'route.create': '新建路线',
  'route.update': '更新路线',
  'route.delete': '删除路线',
  'cs.transfer': '用户转人工',
  'cs.claim': '客服接入',
  'cs.release': '客服释放',
  'cs.close': '结束会话',
  'device.revoke': '移除登录设备',
  'after_sale.create': '申请售后',
  'after_sale.accept': '受理售后',
  'after_sale.resolve': '完成售后',
  'after_sale.reject': '拒绝售后',
  'after_sale.withdraw': '撤销售后',
};

const ACTION_OPTIONS = Object.keys(ACTION_LABEL);

const TARGET_TYPE_OPTIONS = [
  { value: 'user', label: '用户' },
  { value: 'order', label: '订单' },
  { value: 'payment', label: '支付单' },
  { value: 'route', label: '预设路线' },
  { value: 'cs_session', label: '客服会话' },
  { value: 'device', label: '登录设备' },
  { value: 'after_sale', label: '售后单' },
];

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listAuditLogs({
      action: actionFilter.value || undefined,
      target_type: targetTypeFilter.value || undefined,
      target_id: targetFilter.value ? Number(targetFilter.value) : undefined,
      page: page.value,
      page_size: pageSize,
    });
    rows.value = data.items;
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

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

onMounted(load);
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>审计日志</span>
        <div class="filters">
          <el-select
            v-model="actionFilter"
            placeholder="按动作过滤"
            clearable
            style="width: 160px"
            @change="search"
          >
            <el-option
              v-for="action in ACTION_OPTIONS"
              :key="action"
              :label="ACTION_LABEL[action]"
              :value="action"
            />
          </el-select>
          <el-select
            v-model="targetTypeFilter"
            placeholder="全部目标类型"
            clearable
            style="width: 150px"
            @change="search"
          >
            <el-option
              v-for="item in TARGET_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-input
            v-model="targetFilter"
            placeholder="按目标 ID"
            clearable
            style="width: 140px"
            @keyup.enter="search"
          />
          <el-button type="primary" @click="search">查询</el-button>
        </div>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="actor_id" label="操作人" width="90" />
      <el-table-column label="动作" width="130">
        <template #default="{ row }">
          <el-tag size="small">{{ ACTION_LABEL[row.action] ?? row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="目标" width="140">
        <template #default="{ row }">{{ row.target_type }} #{{ row.target_id }}</template>
      </el-table-column>
      <el-table-column label="详情" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.detail ?? '—' }}</template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        layout="prev, pager, next, total"
        :total="total"
        :page-size="pageSize"
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
  gap: 12px;
  flex-wrap: wrap;
}
.filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>

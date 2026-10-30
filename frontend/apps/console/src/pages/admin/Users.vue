<script setup lang="ts">
import { ApiError, disableUser, enableUser, listUsers, type UserAdminPublic } from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, ref } from 'vue';

const rows = ref<UserAdminPublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const loading = ref(false);
const error = ref('');

const filters = ref({ role: '', status: '', keyword: '' });

const ROLE_LABEL: Record<string, string> = {
  tourist: '游客',
  merchant: '商户',
  enterprise: '企业',
  admin: '管理员',
};

const STATUS_LABEL: Record<string, { text: string; type: 'success' | 'warning' | 'danger' | 'info' }> = {
  active: { text: '正常', type: 'success' },
  pending_review: { text: '待审核', type: 'warning' },
  rejected: { text: '已驳回', type: 'danger' },
  disabled: { text: '已禁用', type: 'info' },
};

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listUsers({
      role: filters.value.role || undefined,
      status: filters.value.status || undefined,
      keyword: filters.value.keyword || undefined,
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

async function toggleStatus(row: UserAdminPublic) {
  const disabling = row.status !== 'disabled';
  await ElMessageBox.confirm(
    disabling
      ? `禁用「${row.nickname ?? row.phone}」？禁用后不可登录。`
      : `解除「${row.nickname ?? row.phone}」的禁用？`,
    '用户状态',
    { type: 'warning' },
  );
  try {
    if (disabling) {
      await disableUser(row.id);
    } else {
      await enableUser(row.id);
    }
    ElMessage.success(disabling ? '已禁用' : '已启用');
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  }
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
        <span>用户管理</span>
        <div class="filters">
          <el-select v-model="filters.role" placeholder="角色" clearable style="width: 120px" @change="search">
            <el-option label="游客" value="tourist" />
            <el-option label="商户" value="merchant" />
            <el-option label="企业" value="enterprise" />
            <el-option label="管理员" value="admin" />
          </el-select>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="search">
            <el-option label="正常" value="active" />
            <el-option label="待审核" value="pending_review" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="已禁用" value="disabled" />
          </el-select>
          <el-input
            v-model="filters.keyword"
            placeholder="手机号 / 昵称"
            clearable
            style="width: 180px"
            @keyup.enter="search"
          />
          <el-button type="primary" @click="search">查询</el-button>
        </div>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="phone" label="手机号" width="140" />
      <el-table-column label="昵称" min-width="140">
        <template #default="{ row }">{{ row.nickname ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="角色" width="100">
        <template #default="{ row }">{{ ROLE_LABEL[row.role] ?? row.role }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="STATUS_LABEL[row.status]?.type ?? 'info'" size="small">
            {{ STATUS_LABEL[row.status]?.text ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="注册时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button
            v-if="row.role !== 'admin' && row.status !== 'pending_review'"
            link
            :type="row.status === 'disabled' ? 'success' : 'danger'"
            @click="toggleStatus(row)"
          >
            {{ row.status === 'disabled' ? '启用' : '禁用' }}
          </el-button>
          <span v-else-if="row.role === 'admin'" class="muted">—</span>
          <span v-else class="muted">先审核</span>
        </template>
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
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>

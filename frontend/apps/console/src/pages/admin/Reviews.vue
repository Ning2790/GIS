<script setup lang="ts">
import { ApiError, approveReview, listPendingReviews, rejectReview, type UserAdminPublic } from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, ref } from 'vue';

const rows = ref<UserAdminPublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const loading = ref(false);
const error = ref('');

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listPendingReviews(page.value, pageSize);
    rows.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function approve(row: UserAdminPublic) {
  await ElMessageBox.confirm(`通过「${row.nickname ?? row.phone}」的资质审核？通过后即可登录。`, '审核', {
    type: 'info',
  });
  try {
    await approveReview(row.id);
    ElMessage.success('审核通过');
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  }
}

async function reject(row: UserAdminPublic) {
  await ElMessageBox.confirm(`驳回「${row.nickname ?? row.phone}」的资质审核？驳回后不可登录。`, '审核', {
    type: 'warning',
  });
  try {
    await rejectReview(row.id);
    ElMessage.success('已驳回');
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
    <template #header>资质审核（待审核商户 / 企业）</template>
    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />
    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="phone" label="手机号" width="140" />
      <el-table-column label="名称" min-width="160">
        <template #default="{ row }">{{ row.nickname ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.role === 'enterprise' ? 'primary' : 'info'">
            {{ row.role === 'enterprise' ? '企业' : '商户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="营业执照号" min-width="170">
        <template #default="{ row }">{{ row.license_no ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="资质文件" width="130">
        <template #default="{ row }">
          <a
            v-if="row.license_file"
            :href="row.license_file"
            target="_blank"
            rel="noopener"
          >
            查看
          </a>
          <span v-else class="muted">未上传</span>
        </template>
      </el-table-column>
      <el-table-column label="注册时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="success" @click="approve(row)">通过</el-button>
          <el-button link type="danger" @click="reject(row)">驳回</el-button>
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

<script setup lang="ts">
import { ApiError, listDevices, revokeDevice, type DevicePublic } from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, ref } from 'vue';

// 登录设备（需求量 4.2）：本设备二次访问免密登录；移除即撤销该设备名下全部会话
const rows = ref<DevicePublic[]>([]);
const loading = ref(false);
const error = ref('');
const revokingId = ref<number | null>(null);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    rows.value = await listDevices();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function remove(row: DevicePublic) {
  const name = row.device_label ?? `设备 ${row.id}`;
  try {
    await ElMessageBox.confirm(`移除「${name}」？该设备上的登录将失效，需要重新登录。`, '提示', {
      type: 'warning',
    });
  } catch {
    return; // 用户取消
  }
  revokingId.value = row.id;
  try {
    await revokeDevice(row.id);
    ElMessage.success(
      row.is_current ? '当前设备已移除，本机会在下次刷新时退出登录' : `已移除「${name}」`,
    );
    await load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '移除失败');
  } finally {
    revokingId.value = null;
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
        <span>登录设备</span>
        <span class="muted">
          在本设备上二次访问可免密登录（记住我 30 天）；移除后该设备需重新登录。
        </span>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="rows" empty-text="暂无已绑定设备">
      <el-table-column label="设备" min-width="220">
        <template #default="{ row }">
          <span>{{ row.device_label ?? '未知设备' }}</span>
          <el-tag v-if="row.is_current" size="small" type="primary" class="current">当前设备</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近活跃" min-width="170">
        <template #default="{ row }">{{ formatTime(row.last_seen_at) }}</template>
      </el-table-column>
      <el-table-column label="最近 IP" min-width="140">
        <template #default="{ row }">{{ row.last_ip ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="首次绑定" min-width="170">
        <template #default="{ row }">{{ formatTime(row.first_seen_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" :loading="revokingId === row.id" @click="remove(row)">
            移除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.current {
  margin-left: 8px;
}
</style>

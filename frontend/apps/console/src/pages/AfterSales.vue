<script setup lang="ts">
/** 售后管理（N4）：商户处理自己订单的售后；管理员看全平台。
 *
 * 状态机：待处理 →（受理）处理中 →（完成）已解决；可拒绝（理由必填）；
 * 买家可在受理前撤销。平台不做资金池，退款 / 换货线下或经第三方处理。
 */

import {
  acceptAfterSale,
  ApiError,
  getAfterSale,
  listAfterSales,
  postAfterSaleMessage,
  rejectAfterSale,
  resolveAfterSale,
  type AfterSaleDetail,
  type AfterSalePublic,
} from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const route = useRoute();
const isAdmin = computed(() => auth.user?.role === 'admin');

// 通知跳转定位：/after-sales?focus=<id> 时自动打开对应售后详情
const focusId = computed(() => {
  const raw = Array.isArray(route.query.focus) ? route.query.focus[0] : route.query.focus;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
});
const focusError = ref('');

/** 能否处理：订单归属本商户，或管理员（商户作为买家发起的售后不可在自己控制台处理）。 */
function canHandle(row: { merchant_id: number }): boolean {
  return isAdmin.value || row.merchant_id === auth.user?.id;
}

const rows = ref<AfterSalePublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const statusFilter = ref('');
const loading = ref(false);
const error = ref('');

const detail = ref<AfterSaleDetail | null>(null);
const detailVisible = ref(false);
const detailLoading = ref(false);
const reply = ref('');
const sending = ref(false);
const acting = ref(false);

const REASON_LABEL: Record<string, string> = {
  quality: '质量问题',
  missing: '少发 / 漏发',
  mismatch: '与描述不符',
  damaged: '包装 / 商品破损',
  other: '其他',
};

const STATUS_MAP: Record<string, { text: string; type: 'warning' | 'primary' | 'success' | 'danger' | 'info' }> = {
  pending: { text: '待处理', type: 'warning' },
  processing: { text: '处理中', type: 'primary' },
  resolved: { text: '已解决', type: 'success' },
  rejected: { text: '已拒绝', type: 'danger' },
  withdrawn: { text: '已撤销', type: 'info' },
};

function statusOf(status: string) {
  return STATUS_MAP[status] ?? { text: status, type: 'info' as const };
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listAfterSales(page.value, pageSize, statusFilter.value || undefined);
    rows.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function openDetail(row: AfterSalePublic) {
  detailVisible.value = true;
  detailLoading.value = true;
  detail.value = null;
  reply.value = '';
  try {
    detail.value = await getAfterSale(row.id);
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '加载售后详情失败');
  } finally {
    detailLoading.value = false;
  }
}

async function refresh() {
  if (detail.value) {
    detail.value = await getAfterSale(detail.value.id);
  }
  await load();
}

async function accept() {
  if (!detail.value || acting.value) return;
  acting.value = true;
  try {
    await acceptAfterSale(detail.value.id);
    ElMessage.success('已受理，进入处理中');
    await refresh();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '受理失败');
  } finally {
    acting.value = false;
  }
}

async function resolveOne() {
  if (!detail.value || acting.value) return;
  let note = '';
  try {
    const result = await ElMessageBox.prompt(
      '处理说明（可选，会记入处理记录）',
      '完成售后',
      { inputType: 'textarea', inputValue: '', inputValidator: () => true },
    );
    note = String(result.value ?? '').trim();
  } catch {
    return; // 取消
  }
  acting.value = true;
  try {
    await resolveAfterSale(detail.value.id, note || undefined);
    ElMessage.success('售后已完成');
    await refresh();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  } finally {
    acting.value = false;
  }
}

async function rejectOne() {
  if (!detail.value || acting.value) return;
  let reason = '';
  try {
    const result = await ElMessageBox.prompt('拒绝理由（必填，会记入处理记录）', '拒绝售后', {
      inputType: 'textarea',
      inputValue: '',
      inputValidator: (value: string) => (value && value.trim() ? true : '请填写拒绝理由'),
    });
    reason = String(result.value ?? '').trim();
  } catch {
    return; // 取消
  }
  acting.value = true;
  try {
    await rejectAfterSale(detail.value.id, reason);
    ElMessage.success('已拒绝');
    await refresh();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  } finally {
    acting.value = false;
  }
}

async function sendReply() {
  if (!detail.value || sending.value || !reply.value.trim()) return;
  sending.value = true;
  try {
    await postAfterSaleMessage(detail.value.id, reply.value.trim());
    reply.value = '';
    await refresh();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '留言失败');
  } finally {
    sending.value = false;
  }
}

onMounted(async () => {
  await load();
  const target = focusId.value;
  if (!target) return;
  const row = rows.value.find((item) => item.id === target);
  if (row) {
    await openDetail(row);
    return;
  }
  try {
    detail.value = await getAfterSale(target);
    detailVisible.value = true;
  } catch {
    focusError.value = `未找到售后 #${target}（可能已删除或无权限）`;
  }
});
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>售后管理</span>
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 150px" @change="page = 1; load()">
          <el-option label="待处理" value="pending" />
          <el-option label="处理中" value="processing" />
          <el-option label="已解决" value="resolved" />
          <el-option label="已拒绝" value="rejected" />
          <el-option label="已撤销" value="withdrawn" />
        </el-select>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="focusError" :title="focusError" type="warning" show-icon closable />

    <el-table v-loading="loading" :data="rows" empty-text="暂无售后记录">
      <el-table-column prop="id" label="售后号" width="90" />
      <el-table-column prop="order_id" label="订单号" width="90" />
      <el-table-column label="问题类型" width="130">
        <template #default="{ row }">{{ REASON_LABEL[row.reason] ?? row.reason }}</template>
      </el-table-column>
      <el-table-column label="说明" min-width="200">
        <template #default="{ row }">
          <span v-if="row.description">{{ row.description }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusOf(row.status).type" size="small">{{ statusOf(row.status).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申请时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">
            {{ ['pending', 'processing'].includes(row.status) && canHandle(row) ? '处理' : '查看' }}
          </el-button>
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

    <el-dialog v-model="detailVisible" title="售后处理" width="640px">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="售后号">#{{ detail.id }}</el-descriptions-item>
            <el-descriptions-item label="订单号">#{{ detail.order_id }}</el-descriptions-item>
            <el-descriptions-item label="问题类型">
              {{ REASON_LABEL[detail.reason] ?? detail.reason }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusOf(detail.status).type" size="small">
                {{ statusOf(detail.status).text }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="订单金额">
              {{ detail.order_amount != null ? `￥${detail.order_amount}` : '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="申请时间">
              {{ formatTime(detail.created_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="申请说明" :span="2">
              {{ detail.description || '—' }}
            </el-descriptions-item>
          </el-descriptions>

          <h4 class="section">处理记录（{{ detail.messages.length }}）</h4>
          <p v-if="detail.messages.length === 0" class="muted">暂无留言</p>
          <ul v-else class="messages">
            <li v-for="item in detail.messages" :key="item.id" class="messages__item">
              <span class="messages__author">
                {{ item.author_role === 'buyer' ? '买家' : item.author_role === 'admin' ? '平台' : '商户' }}
              </span>
              <span class="messages__time">{{ formatTime(item.created_at) }}</span>
              <p class="messages__content">{{ item.content }}</p>
            </li>
          </ul>

          <template v-if="['pending', 'processing'].includes(detail.status)">
            <el-input
              v-model="reply"
              type="textarea"
              :rows="2"
              maxlength="300"
              placeholder="留言给买家（最多 300 字）"
            />
            <div class="reply-actions">
              <el-button size="small" :loading="sending" :disabled="!reply.trim()" @click="sendReply">
                发送留言
              </el-button>
            </div>
          </template>
        </template>
      </div>

      <template #footer>
        <template v-if="detail && ['pending', 'processing'].includes(detail.status) && canHandle(detail)">
          <el-button v-if="detail.status === 'pending'" type="primary" :loading="acting" @click="accept">
            受理
          </el-button>
          <el-button v-else type="success" :loading="acting" @click="resolveOne">完成售后</el-button>
          <el-button type="danger" plain :loading="acting" @click="rejectOne">拒绝</el-button>
        </template>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
.section {
  margin: 16px 0 8px;
  font-size: 14px;
}
.messages {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
}
.messages__item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.messages__author {
  font-weight: 600;
  font-size: 13px;
}
.messages__time {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.messages__content {
  margin: 4px 0 0;
  font-size: 13px;
  white-space: pre-wrap;
}
.reply-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>

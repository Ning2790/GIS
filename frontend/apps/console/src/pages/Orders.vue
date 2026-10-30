<script setup lang="ts">
import {
  ApiError,
  deliverOrder,
  exportOrdersCsv,
  getOrderDetail,
  listMerchantOrders,
  paymentCallback,
  refundPayment,
  shipOrder,
  type OrderPublic,
} from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const route = useRoute();
const isAdmin = computed(() => auth.user?.role === 'admin');

// 通知跳转定位：/orders?focus=<id> 时把目标订单带进列表并提示
const focusId = computed(() => {
  const raw = Array.isArray(route.query.focus) ? route.query.focus[0] : route.query.focus;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
});
const focusNotice = ref<number | null>(null);

const rows = ref<OrderPublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const loading = ref(false);
const error = ref('');

const STATUS_MAP: Record<string, { text: string; type: 'warning' | 'success' | 'info' }> = {
  created: { text: '待支付', type: 'warning' },
  paid: { text: '已支付', type: 'success' },
  shipped: { text: '已发货', type: 'success' },
  completed: { text: '已完成', type: 'info' },
  cancelled: { text: '已取消', type: 'info' },
};

// 发货（N3）：承运商 + 运单号必填
const shipDialog = ref(false);
const shipping = ref(false);
const shipTarget = ref<OrderPublic | null>(null);
const shipForm = reactive({ carrier: '', trackingNo: '' });

function openShip(row: OrderPublic) {
  shipTarget.value = row;
  shipForm.carrier = '';
  shipForm.trackingNo = '';
  shipDialog.value = true;
}

async function submitShip() {
  if (!shipTarget.value) return;
  if (!shipForm.carrier.trim()) {
    ElMessage.warning('请填写承运商（如：顺丰）');
    return;
  }
  if (shipForm.trackingNo.trim().length < 4) {
    ElMessage.warning('请填写运单号（至少 4 位）');
    return;
  }
  shipping.value = true;
  try {
    await shipOrder(shipTarget.value.id, shipForm.carrier.trim(), shipForm.trackingNo.trim());
    ElMessage.success('已发货，买家可查看物流并确认收货');
    shipDialog.value = false;
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '发货失败');
  } finally {
    shipping.value = false;
  }
}

/** 标记已签收：签收后超期未确认收货将自动确认。 */
async function markDelivered(row: OrderPublic) {
  try {
    await ElMessageBox.confirm(
      `标记订单 #${row.id} 已签收？签收后 7 天买家未确认收货将自动确认。`,
      '标记签收',
      { type: 'info' },
    );
    await deliverOrder(row.id);
    ElMessage.success('已标记签收');
    void load();
  } catch (err) {
    if (err === 'cancel' || err === 'close') return;
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  }
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listMerchantOrders(page.value, pageSize);
    rows.value = data.items;
    total.value = data.total;
    await focusTarget();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

/** 通知跳转定位：目标不在当前页时按 id 取详情补到列表顶部。 */
async function focusTarget() {
  const target = focusId.value;
  if (!target) return;
  focusNotice.value = target;
  if (rows.value.some((row) => row.id === target)) return;
  try {
    const detail = await getOrderDetail(target);
    rows.value = [detail, ...rows.value];
  } catch {
    // 订单不存在 / 无权限：只显示提示，由用户自行切换分页
  }
}

/** 管理员模拟支付回调（演示闭环：游客点支付创建支付单 → 管理员模拟回调成功）。 */
async function simulatePay(row: OrderPublic) {
  try {
    const detail = await getOrderDetail(row.id);
    if (!detail.payment_id) {
      ElMessage.warning('该订单尚未创建支付单（需游客先点击「创建支付单」）');
      return;
    }
    await ElMessageBox.confirm(
      `将订单 #${row.id} 的支付单 #${detail.payment_id} 模拟为支付成功？`,
      '模拟支付回调',
      { type: 'info' },
    );
    await paymentCallback(detail.payment_id, true, `ADMIN-MOCK-${Date.now()}`);
    ElMessage.success('已模拟支付成功，订单转为已支付');
    void load();
  } catch (err) {
    if (err === 'cancel' || err === 'close') {
      return;
    }
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  }
}

const exporting = ref(false);

// 异常支付退款（管理员）：订单取消 / 重复支付后，线下退款完成再登记关闭
const refundDialog = ref(false);
const refunding = ref(false);
const refundTarget = ref<OrderPublic | null>(null);
const refundNote = ref('');

function openRefund(row: OrderPublic) {
  refundTarget.value = row;
  refundNote.value = '';
  refundDialog.value = true;
}

async function submitRefund() {
  if (!refundTarget.value?.payment_id) {
    ElMessage.warning('该订单没有可退款的支付单');
    return;
  }
  refunding.value = true;
  try {
    await refundPayment(refundTarget.value.payment_id, refundNote.value.trim() || undefined);
    ElMessage.success('已登记退款，买卖双方会收到通知');
    refundDialog.value = false;
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '退款登记失败');
  } finally {
    refunding.value = false;
  }
}

/** 导出商户订单 CSV（Excel 可直接打开；UTF-8 BOM 与截断标记由后端带）。 */
async function exportCsv() {
  exporting.value = true;
  try {
    const { blob, rows, truncated } = await exportOrdersCsv({});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    // 本地日期：toISOString 取 UTC，中国时间 00:00–08:00 会显示成前一天
    const today = new Date();
    const stamp = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-');
    link.download = `orders-${stamp}.csv`;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
    // 延迟回收：立即 revoke 会让部分浏览器取消仍在进行的下载
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (truncated) {
      ElMessage.warning(
        `已导出最近 ${rows ?? ''} 行（超过 5 万行上限，更早订单请用时间范围分段导出）`,
      );
    } else {
      ElMessage.success('已导出订单 CSV');
    }
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '导出失败');
  } finally {
    exporting.value = false;
  }
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}

onMounted(load);
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>{{ isAdmin ? '订单管理（全平台）' : '订单管理' }}</span>
        <span class="head__right">
          <el-tag v-if="isAdmin" size="small" type="danger">管理员视角 · 可模拟支付回调</el-tag>
          <el-button link type="primary" :loading="exporting" @click="exportCsv">
            导出 CSV
          </el-button>
        </span>
      </div>
    </template>
    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />
    <el-alert
      v-if="focusNotice"
      :title="`已定位订单 #${focusNotice}`"
      type="info"
      show-icon
      closable
      style="margin-bottom: 12px"
      @close="focusNotice = null"
    />
    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="订单号" width="90" />
      <el-table-column label="金额（元）" width="120">
        <template #default="{ row }">￥{{ row.amount }}</template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <el-tag :type="STATUS_MAP[row.status]?.type ?? 'info'" size="small">
            {{ STATUS_MAP[row.status]?.text ?? row.status }}
          </el-tag>
          <el-tag
            v-if="row.payment_refund_status === 'pending'"
            type="danger"
            size="small"
            style="margin-left: 4px"
          >
            待退款
          </el-tag>
          <el-tag
            v-else-if="row.payment_refund_status === 'refunded'"
            type="success"
            size="small"
            style="margin-left: 4px"
          >
            已退款
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="支付时间" width="180">
        <template #default="{ row }">{{ formatTime(row.paid_at) }}</template>
      </el-table-column>
      <el-table-column label="收货信息" min-width="220">
        <template #default="{ row }">
          <template v-if="row.receiver_name">
            <span>{{ row.receiver_name }} · {{ row.receiver_phone }}</span>
            <br />
            <span class="muted">{{ row.receiver_address }}</span>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="物流" min-width="180">
        <template #default="{ row }">
          <template v-if="row.carrier || row.tracking_no">
            <span>{{ row.carrier ?? '—' }} {{ row.tracking_no ?? '' }}</span>
            <br />
            <span class="muted">
              {{ row.delivered_at ? `已签收 ${formatTime(row.delivered_at)}` : '运输中' }}
            </span>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="user_id" label="买家 ID" width="90" />
      <el-table-column label="操作" width="190">
        <template #default="{ row }">
          <template v-if="row.payment_refund_status === 'pending' && isAdmin">
            <el-button link type="danger" @click="openRefund(row)">登记退款</el-button>
          </template>
          <template v-else-if="row.status === 'paid'">
            <el-button link type="primary" @click="openShip(row)">发货</el-button>
          </template>
          <template v-else-if="row.status === 'shipped' && !row.delivered_at">
            <el-button link type="primary" @click="markDelivered(row)">标记签收</el-button>
          </template>
          <template v-else-if="row.status === 'created' && isAdmin">
            <el-button link type="primary" @click="simulatePay(row)">模拟支付成功</el-button>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="shipDialog" title="发货" width="420px">
      <p class="muted">订单 #{{ shipTarget?.id }} · 收货人 {{ shipTarget?.receiver_name }}</p>
      <el-form label-width="80px" class="ship-form">
        <el-form-item label="承运商">
          <el-input v-model="shipForm.carrier" maxlength="32" placeholder="如：顺丰" />
        </el-form-item>
        <el-form-item label="运单号">
          <el-input v-model="shipForm.trackingNo" maxlength="64" placeholder="物流单号（不少于 4 位）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="shipDialog = false">取消</el-button>
        <el-button type="primary" :loading="shipping" @click="submitShip">确认发货</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="refundDialog" title="登记退款" width="440px">
      <p class="muted">
        订单 #{{ refundTarget?.id }} · 支付单 #{{ refundTarget?.payment_id }} ·
        ￥{{ refundTarget?.amount }}
      </p>
      <el-alert
        title="该支付发生在订单取消 / 重复支付之后。请先在线下或支付渠道完成退款，再在此登记关闭。"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-form label-width="80px">
        <el-form-item label="退款说明">
          <el-input
            v-model="refundNote"
            maxlength="255"
            placeholder="退款渠道 / 凭证号（选填）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="refundDialog = false">取消</el-button>
        <el-button type="danger" :loading="refunding" @click="submitRefund">
          确认已退款
        </el-button>
      </template>
    </el-dialog>

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
}
.head__right {
  display: flex;
  align-items: center;
  gap: 8px;
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
.ship-form {
  margin-top: 12px;
}
</style>

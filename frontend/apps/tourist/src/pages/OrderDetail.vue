<script setup lang="ts">
import {
  applyAfterSale,
  cancelOrder,
  createPayment,
  getOrderDetail,
  receiveOrder,
  withdrawAfterSale,
  type OrderDetail,
  type PaymentPublic,
} from '@qh/api-client';
import { QhButton, QhCard, QhTag } from '@qh/ui';
import { computed, onMounted, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();

const order = ref<OrderDetail | null>(null);
const payment = ref<PaymentPublic | null>(null);
const loading = ref(true);
const error = ref('');
const submitting = ref(false);
// 取消订单：两段式确认，避免误触
const confirmingCancel = ref(false);
const cancelling = ref(false);
// 申请售后（需求 2.3）：选原因 + 填说明，提交后生成售后单（可在「我的售后」跟踪）
const afterSaleOpen = ref(false);
const afterSaleReason = ref('quality');
const afterSaleNote = ref('');
const afterSaleSubmitting = ref(false);
const withdrawing = ref(false);

const REASON_OPTIONS = [
  { value: 'quality', label: '质量问题' },
  { value: 'missing', label: '少发 / 漏发' },
  { value: 'mismatch', label: '与描述不符' },
  { value: 'damaged', label: '包装 / 商品破损' },
  { value: 'other', label: '其他' },
];

type QhTone = 'default' | 'primary' | 'danger' | 'success' | 'warning';

const AFTER_SALE_STATUS: Record<string, { text: string; tone: QhTone }> = {
  pending: { text: '售后待处理', tone: 'warning' },
  processing: { text: '售后处理中', tone: 'primary' },
  resolved: { text: '售后已解决', tone: 'success' },
  rejected: { text: '售后被拒绝', tone: 'danger' },
  withdrawn: { text: '售后已撤销', tone: 'default' },
};

function afterSaleStatusInfo(status: string | null): { text: string; tone: QhTone } {
  return (status ? AFTER_SALE_STATUS[status] : null) ?? { text: status ?? '', tone: 'default' };
}

/** 是否已有未结单售后（结单后可再次发起申请）。 */
const afterSaleOpenNow = computed(() =>
  ['pending', 'processing'].includes(order.value?.after_sale_status ?? ''),
);
// 确认收货（N3）
const receiving = ref(false);

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

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
}

async function load() {
  try {
    order.value = await getOrderDetail(Number(route.params.id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function handlePay() {
  if (!order.value || submitting.value) {
    return;
  }
  error.value = '';
  submitting.value = true;
  try {
    payment.value = await createPayment(order.value.id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建支付单失败';
  } finally {
    submitting.value = false;
  }
}

async function handleCancel() {
  if (!order.value || cancelling.value) {
    return;
  }
  error.value = '';
  cancelling.value = true;
  try {
    order.value = await cancelOrder(order.value.id);
    confirmingCancel.value = false;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '取消订单失败';
  } finally {
    cancelling.value = false;
  }
}

async function handleReceive() {
  if (!order.value || receiving.value) {
    return;
  }
  if (!window.confirm('确认已收到货物？确认后交易完成。')) {
    return;
  }
  error.value = '';
  receiving.value = true;
  try {
    order.value = await receiveOrder(order.value.id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '确认收货失败';
  } finally {
    receiving.value = false;
  }
}

async function submitAfterSale() {
  if (!order.value || afterSaleSubmitting.value) {
    return;
  }
  error.value = '';
  afterSaleSubmitting.value = true;
  try {
    const sale = await applyAfterSale(
      order.value.id,
      afterSaleReason.value,
      afterSaleNote.value.trim() || undefined,
    );
    await router.push(`/after-sales/${sale.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交售后申请失败';
  } finally {
    afterSaleSubmitting.value = false;
  }
}

async function handleWithdrawAfterSale() {
  if (!order.value?.after_sale_id || withdrawing.value) {
    return;
  }
  if (!window.confirm('确定撤销本次售后申请？')) {
    return;
  }
  error.value = '';
  withdrawing.value = true;
  try {
    await withdrawAfterSale(order.value.after_sale_id);
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '撤销售后失败';
  } finally {
    withdrawing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <p class="back">
    <RouterLink to="/orders">← 返回订单列表</RouterLink>
  </p>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>

  <template v-else-if="order">
    <QhCard v-if="order.payment_refund_status === 'pending'" class="summary">
      <p class="pay-card__hint">
        该订单已取消，但支付已到账。平台正在安排退款，到账后会通知你，无需重复支付。
      </p>
    </QhCard>
    <QhCard v-else-if="order.payment_refund_status === 'refunded'" class="summary">
      <p class="pay-card__hint">该笔支付已退款完成。</p>
    </QhCard>
    <QhCard class="summary">
      <div class="summary__head">
        <h2>订单 #{{ order.id }}</h2>
        <QhTag :tone="statusOf(order).tone">{{ statusOf(order).text }}</QhTag>
      </div>
      <dl class="summary__meta">
        <dt>金额</dt>
        <dd class="summary__amount">￥{{ order.amount }}</dd>
        <dt>创建时间</dt>
        <dd>{{ formatTime(order.created_at) }}</dd>
        <dt>支付时间</dt>
        <dd>{{ formatTime(order.paid_at) }}</dd>
        <template v-if="order.status === 'created' && order.expire_at">
          <dt>支付截止</dt>
          <dd class="summary__deadline">
            {{ formatTime(order.expire_at) }}（超时未支付将自动取消并回补库存）
          </dd>
        </template>
      </dl>
    </QhCard>

    <QhCard class="detail-card">
      <template #header>商品明细</template>
      <ul class="items">
        <li v-for="item in order.items" :key="item.id" class="items__row">
          <RouterLink :to="`/products/${item.product_id}`" class="items__name">
            {{ item.product_name }}
          </RouterLink>
          <span class="items__unit">￥{{ item.unit_price }} × {{ item.quantity }}</span>
          <span class="items__amount">￥{{ item.amount }}</span>
        </li>
      </ul>
    </QhCard>

    <QhCard class="detail-card">
      <template #header>收货信息</template>
      <dl class="receiver">
        <dt>收货人</dt>
        <dd>{{ order.receiver_name ?? '—' }}</dd>
        <dt>手机号</dt>
        <dd>{{ order.receiver_phone ?? '—' }}</dd>
        <dt>收货地址</dt>
        <dd>{{ order.receiver_address ?? '—' }}</dd>
      </dl>
      <p class="hint">收货信息为下单时的快照，之后修改个人中心地址不影响本订单。</p>
    </QhCard>

    <QhCard v-if="order.shipped_at" class="detail-card">
      <template #header>物流信息</template>
      <dl class="receiver">
        <dt>承运商</dt>
        <dd>{{ order.carrier ?? '—' }} {{ order.tracking_no ?? '' }}</dd>
        <dt>发货时间</dt>
        <dd>{{ formatTime(order.shipped_at) }}</dd>
        <dt>签收时间</dt>
        <dd>
          {{
            order.delivered_at
              ? formatTime(order.delivered_at) + '（签收后超期未确认将自动确认收货）'
              : '运输中'
          }}
        </dd>
      </dl>
    </QhCard>

    <QhCard class="pay-card">
      <template #header>支付与售后</template>
      <template v-if="['paid', 'shipped', 'completed'].includes(order.status)">
        <p class="pay-card__ok">
          <QhTag v-if="order.status === 'paid'" tone="success">已支付</QhTag>
          <QhTag v-else-if="order.status === 'shipped'" tone="success">已发货</QhTag>
          <QhTag v-else tone="primary">已完成</QhTag>
          <span v-if="order.status === 'paid'">支付时间：{{ formatTime(order.paid_at) }}</span>
          <span v-else-if="order.status === 'shipped'">
            {{
              order.delivered_at
                ? `已签收（${formatTime(order.delivered_at)}）`
                : '商家已发货，运输中'
            }}，确认收货后交易完成
          </span>
          <span v-else>完成时间：{{ formatTime(order.completed_at) }}</span>
        </p>
        <div class="pay-card__actions">
          <QhButton
            v-if="order.status === 'shipped'"
            size="sm"
            :disabled="receiving"
            @click="handleReceive"
          >
            {{ receiving ? '确认中…' : '确认收货' }}
          </QhButton>
          <!-- 已有未结单售后：展示进度与入口（待处理时可撤销） -->
          <template v-if="order.after_sale_id && afterSaleOpenNow">
            <QhTag :tone="afterSaleStatusInfo(order.after_sale_status).tone">
              {{ afterSaleStatusInfo(order.after_sale_status).text }}
            </QhTag>
            <RouterLink class="pay-card__link" :to="`/after-sales/${order.after_sale_id}`">
              查看售后详情 →
            </RouterLink>
            <QhButton
              v-if="order.after_sale_status === 'pending'"
              size="sm"
              variant="ghost"
              :disabled="withdrawing"
              @click="handleWithdrawAfterSale"
            >
              {{ withdrawing ? '撤销中…' : '撤销申请' }}
            </QhButton>
          </template>
          <template v-else-if="order.after_sale_id">
            <QhTag :tone="afterSaleStatusInfo(order.after_sale_status).tone">
              上次{{ afterSaleStatusInfo(order.after_sale_status).text }}
            </QhTag>
            <RouterLink class="pay-card__link" :to="`/after-sales/${order.after_sale_id}`">
              查看上次售后 →
            </RouterLink>
          </template>
          <QhButton
            v-if="!afterSaleOpenNow && !afterSaleOpen"
            size="sm"
            variant="ghost"
            @click="afterSaleOpen = true"
          >
            申请售后
          </QhButton>
        </div>
        <div v-if="afterSaleOpen && !afterSaleOpenNow" class="after-sale">
          <p class="after-sale__hint">
            选择问题类型并补充说明，提交后生成售后单，商户会受理并跟进（退款 / 换货由商户
            线下或经第三方处理，平台不经手资金）。需要即时沟通也可用在线客服。
          </p>
          <label class="after-sale__field">
            <span>问题类型</span>
            <select v-model="afterSaleReason" class="after-sale__select">
              <option v-for="item in REASON_OPTIONS" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <textarea
            v-model="afterSaleNote"
            class="after-sale__note"
            rows="3"
            maxlength="300"
            placeholder="补充说明（可选），例如：收到时包装破损，其中两袋漏气…"
          ></textarea>
          <div class="after-sale__actions">
            <QhButton size="sm" :disabled="afterSaleSubmitting" @click="submitAfterSale">
              {{ afterSaleSubmitting ? '提交中…' : '提交售后申请' }}
            </QhButton>
            <QhButton size="sm" variant="ghost" @click="afterSaleOpen = false">返回</QhButton>
          </div>
        </div>
      </template>
      <template v-else-if="order.status === 'cancelled'">
        <p class="pay-card__ok">
          <QhTag tone="default">已取消</QhTag>
          <span v-if="order.cancel_reason === 'expired'">
            订单超时未支付，已自动取消，库存已回补。
          </span>
          <span v-else>订单已取消，库存已回补。</span>
        </p>
        <p class="pay-card__hint">
          如需重新购买，可回到 <RouterLink to="/products">农产品商城</RouterLink> 重新下单。
        </p>
      </template>
      <template v-else-if="payment || order.payment_status === 'created'">
        <p class="pay-card__hint">
          支付单已创建（单号 #{{ payment?.id ?? '—' }}，状态：{{
            payment?.status ?? order.payment_status
          }}）。
          演示环境由管理员模拟支付回调，回调成功后订单将变为「已支付」。
        </p>
        <div class="pay-card__actions">
          <QhButton
            v-if="order.payment_status !== 'success'"
            size="sm"
            variant="ghost"
            :disabled="cancelling"
            @click="confirmingCancel = true"
          >
            取消订单
          </QhButton>
        </div>
      </template>
      <template v-else>
        <p class="pay-card__hint">
          当前为支付占位流程：点击创建支付单后，由管理员在后台模拟第三方回调。
        </p>
        <div class="pay-card__actions">
          <QhButton size="sm" :disabled="submitting" @click="handlePay">创建支付单</QhButton>
          <QhButton
            size="sm"
            variant="ghost"
            :disabled="cancelling"
            @click="confirmingCancel = true"
          >
            取消订单
          </QhButton>
        </div>
      </template>
      <div v-if="confirmingCancel && order.status === 'created'" class="confirm">
        <p class="confirm__text">确认取消该订单？取消后库存将立即回补，此操作不可撤销。</p>
        <div class="confirm__actions">
          <QhButton size="sm" variant="danger" :disabled="cancelling" @click="handleCancel">
            {{ cancelling ? '取消中…' : '确认取消订单' }}
          </QhButton>
          <QhButton size="sm" variant="ghost" @click="confirmingCancel = false">暂不取消</QhButton>
        </div>
      </div>
    </QhCard>
  </template>
</template>

<style scoped>
.back {
  margin: 0 0 var(--qh-space-4);
  font-size: var(--qh-fs-sm);
}
.summary {
  margin-bottom: var(--qh-space-4);
}
.summary__head {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin-bottom: var(--qh-space-3);
}
.summary__head h2 {
  margin: 0;
  font-size: var(--qh-fs-xl);
}
.summary__meta {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr;
  gap: var(--qh-space-2) var(--qh-space-4);
  margin: 0;
  font-size: var(--qh-fs-sm);
}
.summary__meta dt {
  color: var(--qh-muted);
}
.summary__meta dd {
  margin: 0;
}
.summary__amount {
  color: var(--qh-primary);
  font-weight: 700;
}
.receiver {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--qh-space-1) var(--qh-space-4);
  margin: 0;
  font-size: var(--qh-fs-sm);
}
.receiver dt {
  color: var(--qh-muted);
}
.receiver dd {
  margin: 0;
}
.hint {
  margin: var(--qh-space-3) 0 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.pay-card__link {
  margin-left: var(--qh-space-3);
  font-size: var(--qh-fs-sm);
}
.after-sale__field {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-1);
  margin-bottom: var(--qh-space-3);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
.after-sale__select {
  padding: 8px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
}
.summary__deadline {
  color: var(--qh-warning);
}
.detail-card {
  margin-bottom: var(--qh-space-4);
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.items__row {
  display: flex;
  align-items: center;
  gap: var(--qh-space-4);
  padding: var(--qh-space-3) 0;
  border-bottom: 1px solid var(--qh-border);
}
.items__row:last-child {
  border-bottom: none;
}
.items__name {
  flex: 1;
  font-weight: 600;
  color: var(--qh-ink);
}
.items__unit {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.items__amount {
  width: 90px;
  text-align: right;
  font-weight: 700;
  color: var(--qh-primary);
}
.pay-card__ok {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.pay-card__hint {
  margin: 0 0 var(--qh-space-3);
  color: var(--qh-ink-2);
  line-height: 1.7;
}
.pay-card__actions {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin-top: var(--qh-space-3);
}
.after-sale {
  margin-top: var(--qh-space-4);
  padding-top: var(--qh-space-4);
  border-top: 1px dashed var(--qh-border-strong);
}
.after-sale__hint {
  margin: 0 0 var(--qh-space-3);
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
  line-height: 1.7;
}
.after-sale__note {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.after-sale__note:focus {
  border-color: var(--qh-primary);
  box-shadow: 0 0 0 3px var(--qh-primary-weak);
}
.after-sale__actions {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin-top: var(--qh-space-3);
}
.confirm {
  margin-top: var(--qh-space-4);
  padding: var(--qh-space-3) var(--qh-space-4);
  border: 1px solid var(--qh-border-strong);
  border-left: 3px solid var(--qh-danger);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-danger-bg);
}
.confirm__text {
  margin: 0 0 var(--qh-space-3);
  color: var(--qh-ink-2);
  font-size: var(--qh-fs-sm);
  line-height: 1.7;
}
.confirm__actions {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
</style>

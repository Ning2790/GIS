<script setup lang="ts">
/** 售后详情（需求 2.3）：进度 + 双方留言；待处理时可撤销申请。 */

import {
  ApiError,
  getAfterSale,
  postAfterSaleMessage,
  withdrawAfterSale,
  type AfterSaleDetail,
} from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhTag } from '@qh/ui';
import { computed, onMounted, ref } from 'vue';
import { RouterLink, useRoute } from 'vue-router';

const route = useRoute();
const sale = ref<AfterSaleDetail | null>(null);
const loading = ref(true);
const error = ref('');
const message = ref('');
const sending = ref(false);
const withdrawing = ref(false);

const REASON_LABEL: Record<string, string> = {
  quality: '质量问题',
  missing: '少发 / 漏发',
  mismatch: '与描述不符',
  damaged: '包装 / 商品破损',
  other: '其他',
};

type QhTone = 'default' | 'primary' | 'danger' | 'success' | 'warning';

const STATUS_INFO: Record<string, { text: string; tone: QhTone }> = {
  pending: { text: '待商户处理', tone: 'warning' },
  processing: { text: '处理中', tone: 'primary' },
  resolved: { text: '已解决', tone: 'success' },
  rejected: { text: '已拒绝', tone: 'danger' },
  withdrawn: { text: '已撤销', tone: 'default' },
};

const statusInfo = computed<{ text: string; tone: QhTone } | null>(() =>
  sale.value
    ? (STATUS_INFO[sale.value.status] ?? { text: sale.value.status, tone: 'default' })
    : null,
);
const isOpen = computed(() =>
  sale.value ? ['pending', 'processing'].includes(sale.value.status) : false,
);

const ROLE_LABEL: Record<string, string> = {
  buyer: '买家',
  merchant: '商户',
  admin: '平台',
};

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    sale.value = await getAfterSale(Number(route.params.id));
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function send() {
  if (!sale.value || sending.value || !message.value.trim()) {
    return;
  }
  sending.value = true;
  error.value = '';
  try {
    await postAfterSaleMessage(sale.value.id, message.value.trim());
    message.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '留言失败';
  } finally {
    sending.value = false;
  }
}

async function withdraw() {
  if (!sale.value || withdrawing.value) {
    return;
  }
  if (!window.confirm('确定撤销本次售后申请？')) {
    return;
  }
  withdrawing.value = true;
  error.value = '';
  try {
    await withdrawAfterSale(sale.value.id);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '撤销失败';
  } finally {
    withdrawing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <p class="back">
    <RouterLink to="/after-sales">← 返回我的售后</RouterLink>
  </p>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error && !sale" class="state state--error">{{ error }}</p>

  <template v-else-if="sale">
    <PageTitle :title="`售后 #${sale.id}`" subtitle="平台不经手资金：退款 / 换货由商户线下或经第三方处理" />

    <QhCard class="summary">
      <div class="summary__head">
        <h2>订单 #{{ sale.order_id }}</h2>
        <QhTag v-if="statusInfo" :tone="statusInfo.tone">{{ statusInfo.text }}</QhTag>
      </div>
      <dl class="summary__meta">
        <dt>问题类型</dt>
        <dd>{{ REASON_LABEL[sale.reason] ?? sale.reason }}</dd>
        <dt>订单金额</dt>
        <dd>{{ sale.order_amount != null ? `￥${sale.order_amount}` : '—' }}</dd>
        <dt>申请时间</dt>
        <dd>{{ formatTime(sale.created_at) }}</dd>
        <dt v-if="sale.closed_at">结单时间</dt>
        <dd v-if="sale.closed_at">{{ formatTime(sale.closed_at) }}</dd>
      </dl>
      <p v-if="sale.description" class="summary__desc">申请说明：{{ sale.description }}</p>
      <div class="summary__actions">
        <RouterLink class="summary__link" :to="`/orders/${sale.order_id}`">查看订单详情 →</RouterLink>
        <QhButton
          v-if="sale.status === 'pending'"
          size="sm"
          variant="ghost"
          :disabled="withdrawing"
          @click="withdraw"
        >
          {{ withdrawing ? '撤销中…' : '撤销申请' }}
        </QhButton>
      </div>
    </QhCard>

    <QhCard class="messages">
      <template #header>处理记录（{{ sale.messages.length }} 条）</template>
      <p v-if="sale.messages.length === 0" class="state">暂无留言。</p>
      <ul v-else class="messages__list">
        <li v-for="item in sale.messages" :key="item.id" class="messages__item">
          <div class="messages__head">
            <span class="messages__author">{{ ROLE_LABEL[item.author_role] ?? item.author_role }}</span>
            <span class="messages__time">{{ formatTime(item.created_at) }}</span>
          </div>
          <p class="messages__content">{{ item.content }}</p>
        </li>
      </ul>

      <template v-if="isOpen">
        <textarea
          v-model="message"
          class="messages__input"
          rows="3"
          maxlength="300"
          placeholder="补充说明或与商户沟通（最多 300 字）"
        ></textarea>
        <div class="messages__actions">
          <QhButton size="sm" :disabled="sending || !message.trim()" @click="send">
            {{ sending ? '发送中…' : '发送留言' }}
          </QhButton>
        </div>
      </template>
      <p v-else class="state">售后单已结单，如需继续沟通可再发起售后或使用在线客服。</p>

      <p v-if="error" class="state state--error">{{ error }}</p>
    </QhCard>
  </template>
</template>

<style scoped>
.back {
  margin-bottom: var(--qh-space-3);
}
.summary__head {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin-bottom: var(--qh-space-3);
}
.summary__head h2 {
  margin: 0;
}
.summary__meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--qh-space-1) var(--qh-space-4);
  margin: 0;
  font-size: var(--qh-fs-sm);
}
.summary__meta dt {
  color: var(--qh-muted);
}
.summary__meta dd {
  margin: 0;
}
.summary__desc {
  margin: var(--qh-space-3) 0 0;
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
.summary__actions {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  margin-top: var(--qh-space-3);
}
.summary__link {
  font-size: var(--qh-fs-sm);
}
.messages {
  margin-top: var(--qh-space-4);
}
.messages__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
}
.messages__item {
  padding: var(--qh-space-3);
  border: 1px solid var(--qh-border);
  border-radius: var(--qh-radius-sm);
}
.messages__head {
  display: flex;
  align-items: baseline;
  gap: var(--qh-space-3);
}
.messages__author {
  font-weight: 600;
  font-size: var(--qh-fs-sm);
}
.messages__time {
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.messages__content {
  margin: var(--qh-space-1) 0 0;
  font-size: var(--qh-fs-sm);
  white-space: pre-wrap;
}
.messages__input {
  width: 100%;
  margin-top: var(--qh-space-3);
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
  resize: vertical;
}
.messages__actions {
  margin-top: var(--qh-space-2);
  display: flex;
  justify-content: flex-end;
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
</style>

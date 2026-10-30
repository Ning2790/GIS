<script setup lang="ts">
import {
  checkoutCart,
  getCart,
  newIdemKey,
  removeCartItem,
  updateCartItem,
  type Cart,
} from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhEmpty, QhTag } from '@qh/ui';
import type { ReceiverPayload } from '@qh/api-client';
import { onMounted, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';

import ReceiverForm from '../components/ReceiverForm.vue';

import { useCartStore } from '../stores/cart';

const router = useRouter();
const cartStore = useCartStore();

const cart = ref<Cart | null>(null);
const loading = ref(true);
const error = ref('');
const message = ref('');
const submitting = ref(false);
const receiver = ref<ReceiverPayload>({ receiver_name: '', receiver_phone: '', receiver_address: '' });

function receiverReady(): boolean {
  return (
    receiver.value.receiver_name.length > 0 &&
    /^1[3-9]\d{9}$/.test(receiver.value.receiver_phone) &&
    receiver.value.receiver_address.length >= 5
  );
}

function applyCart(next: Cart) {
  cart.value = next;
  cartStore.setFromCart(next);
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    applyCart(await getCart());
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function changeQuantity(itemId: number, quantity: number) {
  if (quantity < 1 || quantity > 999) {
    return;
  }
  message.value = '';
  try {
    applyCart(await updateCartItem(itemId, quantity));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '更新数量失败';
  }
}

async function removeItem(itemId: number) {
  message.value = '';
  try {
    applyCart(await removeCartItem(itemId));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '移除失败';
  }
}

async function handleCheckout() {
  if (!cart.value || cart.value.items.length === 0 || submitting.value) {
    return;
  }
  message.value = '';
  if (!receiverReady()) {
    message.value = '请先填写收货人、11 位手机号与收货地址';
    return;
  }
  submitting.value = true;
  try {
    const order = await checkoutCart(newIdemKey(), receiver.value);
    cartStore.clear();
    void router.push(`/orders/${order.id}`);
  } catch (err) {
    message.value = err instanceof Error ? err.message : '结算失败';
  } finally {
    submitting.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageTitle title="购物车" subtitle="确认数量后结算；同一订单只结算同一商户的商品" />

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>

  <template v-else-if="cart">
    <QhEmpty v-if="cart.items.length === 0" text="购物车还是空的">
      <RouterLink to="/products"><QhButton size="sm">去逛逛特产</QhButton></RouterLink>
    </QhEmpty>

    <template v-else>
      <QhCard>
        <ul class="items">
          <li v-for="item in cart.items" :key="item.id" class="items__row">
            <div class="items__info">
              <RouterLink :to="`/products/${item.product_id}`" class="items__name">
                {{ item.name }}
              </RouterLink>
              <p class="items__meta">
                单价 ￥{{ item.price }}
                <QhTag v-if="!item.available" tone="danger">库存不足</QhTag>
              </p>
            </div>
            <div class="stepper">
              <button
                type="button"
                :disabled="item.quantity <= 1"
                @click="changeQuantity(item.id, item.quantity - 1)"
              >
                −
              </button>
              <span>{{ item.quantity }}</span>
              <button type="button" @click="changeQuantity(item.id, item.quantity + 1)">+</button>
            </div>
            <span class="items__amount">￥{{ item.amount }}</span>
            <button class="items__remove" type="button" @click="removeItem(item.id)">移除</button>
          </li>
        </ul>
      </QhCard>

      <QhCard class="receiver-card">
        <template #header>收货信息</template>
        <ReceiverForm @change="(value) => (receiver = value)" />
      </QhCard>

      <div class="checkout">
        <p class="checkout__total">
          合计：<strong>￥{{ cart.total_amount }}</strong>
        </p>
        <QhButton :disabled="submitting" @click="handleCheckout">去结算</QhButton>
      </div>
      <p v-if="message" class="state state--error">{{ message }}</p>
    </template>
  </template>
</template>

<style scoped>
.items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.items__row {
  display: flex;
  align-items: center;
  gap: var(--qh-space-4);
  padding: var(--qh-space-4) 0;
  border-bottom: 1px solid var(--qh-border);
}
.items__row:last-child {
  border-bottom: none;
}
.items__info {
  flex: 1;
  min-width: 0;
}
.items__name {
  font-weight: 600;
  color: var(--qh-ink);
}
.items__meta {
  margin: var(--qh-space-1) 0 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
  display: flex;
  align-items: center;
  gap: var(--qh-space-2);
}
.stepper {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  padding: 4px 10px;
}
.stepper button {
  border: none;
  background: none;
  font-size: var(--qh-fs-lg);
  color: var(--qh-ink);
  cursor: pointer;
  padding: 0 4px;
}
.stepper button:disabled {
  color: var(--qh-faint);
  cursor: not-allowed;
}
.items__amount {
  width: 90px;
  text-align: right;
  font-weight: 700;
  color: var(--qh-primary);
}
.items__remove {
  border: none;
  background: none;
  color: var(--qh-muted);
  cursor: pointer;
  font-size: var(--qh-fs-sm);
}
.items__remove:hover {
  color: var(--qh-danger);
}
.receiver-card {
  margin-bottom: var(--qh-space-4);
}
.checkout {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--qh-space-5);
  margin-top: var(--qh-space-5);
}
.checkout__total {
  margin: 0;
  color: var(--qh-ink-2);
}
.checkout__total strong {
  color: var(--qh-primary);
  font-size: var(--qh-fs-xl);
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 720px) {
  .items__row {
    flex-wrap: wrap;
  }
  .items__amount {
    width: auto;
  }
}
</style>

<script setup lang="ts">
import {
  addCartItem,
  addFavorite,
  createOrder,
  getProductDetail,
  hasSession,
  newIdemKey,
  removeFavorite,
  type ProductDetail as ProductDetailData,
} from '@qh/api-client';
import { QhButton, QhCard, QhEmpty, QhTag } from '@qh/ui';
import type { ReceiverPayload } from '@qh/api-client';
import { onMounted, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

import ReceiverForm from '../components/ReceiverForm.vue';
import { useCartStore } from '../stores/cart';

const route = useRoute();
const router = useRouter();
const cartStore = useCartStore();

const product = ref<ProductDetailData | null>(null);
const favoriting = ref(false);
const quantity = ref(1);
const loading = ref(true);
const error = ref('');
const message = ref('');
const messageOk = ref(false);
const submitting = ref(false);
const buyFormOpen = ref(false);
const receiver = ref<ReceiverPayload>({ receiver_name: '', receiver_phone: '', receiver_address: '' });

function receiverReady(): boolean {
  return (
    receiver.value.receiver_name.length > 0 &&
    /^1[3-9]\d{9}$/.test(receiver.value.receiver_phone) &&
    receiver.value.receiver_address.length >= 5
  );
}

function coverStyle(id: number) {
  const hue = (id * 71 + 200) % 360;
  return {
    background: `linear-gradient(120deg, hsl(${hue} 55% 36%), hsl(${(hue + 35) % 360} 60% 52%))`,
  };
}

function changeQuantity(delta: number) {
  const max = Math.min(product.value?.stock ?? 1, 999);
  quantity.value = Math.min(Math.max(1, quantity.value + delta), Math.max(1, max));
}

function requireLogin(): boolean {
  if (hasSession()) {
    return true;
  }
  void router.push({ name: 'login', query: { redirect: route.fullPath } });
  return false;
}

async function handleAddToCart() {
  if (!product.value || !requireLogin()) {
    return;
  }
  message.value = '';
  submitting.value = true;
  try {
    const cart = await addCartItem(product.value.id, quantity.value);
    cartStore.setFromCart(cart);
    messageOk.value = true;
    message.value = '已加入购物车';
  } catch (err) {
    messageOk.value = false;
    message.value = err instanceof Error ? err.message : '加入购物车失败';
  } finally {
    submitting.value = false;
  }
}

async function handleBuyNow() {
  if (!product.value || !requireLogin()) {
    return;
  }
  message.value = '';
  if (!receiverReady()) {
    messageOk.value = false;
    message.value = '请先填写收货人、11 位手机号与收货地址';
    return;
  }
  submitting.value = true;
  try {
    const order = await createOrder(
      product.value.id,
      quantity.value,
      newIdemKey(),
      receiver.value,
    );
    cartStore.refresh();
    void router.push(`/orders/${order.id}`);
  } catch (err) {
    messageOk.value = false;
    message.value = err instanceof Error ? err.message : '下单失败';
  } finally {
    submitting.value = false;
  }
}

/** 收藏 / 取消收藏（登录后切换；成功后同步本地状态与收藏数）。 */
async function toggleFavorite() {
  if (!product.value || !requireLogin() || favoriting.value) {
    return;
  }
  favoriting.value = true;
  const target = !product.value.is_favorited;
  try {
    const result = target
      ? await addFavorite(product.value.id)
      : await removeFavorite(product.value.id);
    // 用服务端返回的权威计数（幂等命中时本地 ±1 会漂移）
    product.value.is_favorited = result.is_favorited;
    product.value.favorite_count = result.favorite_count;
    messageOk.value = true;
    message.value = result.is_favorited ? '已收藏' : '已取消收藏';
  } catch (err) {
    messageOk.value = false;
    message.value = err instanceof Error ? err.message : '操作失败';
  } finally {
    favoriting.value = false;
  }
}

onMounted(async () => {
  try {
    product.value = await getProductDetail(Number(route.params.id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <p class="back">
    <RouterLink to="/products">← 返回商城</RouterLink>
  </p>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>

  <template v-else-if="product">
    <section class="banner" :style="coverStyle(product.id)">
      <h1>{{ product.name }}</h1>
      <div class="banner__meta">
        <QhTag :tone="product.stock > 0 ? 'default' : 'danger'">库存 {{ product.stock }}</QhTag>
        <QhTag v-if="product.favorite_count > 0">{{ product.favorite_count }} 人收藏</QhTag>
      </div>
    </section>

    <div class="layout">
      <div class="layout__main">
        <QhCard v-if="product.image_url" class="layout__card media" padding="none">
          <img :src="product.image_url" :alt="product.name" class="media__img" />
        </QhCard>
        <QhCard class="layout__card">
          <template #header>商品介绍</template>
          <p class="desc">{{ product.description || '暂无简介' }}</p>
        </QhCard>
      </div>

      <aside class="layout__side">
        <QhCard class="layout__card">
          <p class="price">￥{{ product.price }}</p>
          <div class="quantity">
            <span class="quantity__label">数量</span>
            <div class="stepper">
              <button type="button" :disabled="quantity <= 1" @click="changeQuantity(-1)">−</button>
              <span>{{ quantity }}</span>
              <button type="button" :disabled="quantity >= product.stock" @click="changeQuantity(1)">
                +
              </button>
            </div>
          </div>
          <div class="receiver-block">
            <button class="receiver-toggle" type="button" @click="buyFormOpen = !buyFormOpen">
              {{ buyFormOpen ? '收起收货信息' : '填写 / 选择收货信息' }}
              <span v-if="receiverReady()" class="receiver-ready">已填写</span>
            </button>
            <div v-if="buyFormOpen" class="receiver-form">
              <ReceiverForm @change="(value) => (receiver = value)" />
            </div>
          </div>
          <QhButton
            class="action"
            variant="ghost"
            :disabled="favoriting"
            @click="toggleFavorite"
          >
            {{ product.is_favorited ? '♥ 已收藏' : '♡ 收藏' }}
          </QhButton>
          <QhButton
            class="action"
            variant="ghost"
            :disabled="submitting || product.stock <= 0"
            @click="handleAddToCart"
          >
            加入购物车
          </QhButton>
          <QhButton class="action" :disabled="submitting || product.stock <= 0" @click="handleBuyNow">
            立即购买
          </QhButton>
          <p v-if="message" class="message">
            <QhTag :tone="messageOk ? 'success' : 'danger'">{{ message }}</QhTag>
          </p>
        </QhCard>
      </aside>
    </div>
  </template>
</template>

<style scoped>
.back {
  margin: 0 0 var(--qh-space-4);
  font-size: var(--qh-fs-sm);
}
.banner {
  border-radius: var(--qh-radius-lg);
  color: #fff;
  padding: 26px 32px;
  margin-bottom: var(--qh-space-4);
}
.banner h1 {
  margin: 0 0 var(--qh-space-2);
  font-size: 28px;
  letter-spacing: 0.02em;
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--qh-space-4);
}
.layout__card {
  height: 100%;
}
.media {
  height: auto;
  overflow: hidden;
}
.media__img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: var(--qh-bg);
}
.layout__side .layout__card {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
}
.price {
  margin: 0;
  color: var(--qh-primary);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.quantity {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.quantity__label {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
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
.action {
  width: 100%;
}
.desc {
  margin: 0;
  line-height: 1.9;
  color: var(--qh-ink-2);
  white-space: pre-line;
}
.message {
  margin: 0;
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

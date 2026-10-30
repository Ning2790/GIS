<script setup lang="ts">
/** 商品卡片（收藏 / 浏览历史 / 首页推荐共用；商城主列表另有自己的卡片）。 */

import type { ProductPublic } from '@qh/api-client';
import { QhCard, QhTag } from '@qh/ui';

defineProps<{
  product: ProductPublic;
  /** 是否显示「在售 / 已下架」（收藏与历史里需要，推荐里都是在售商品）。 */
  showStatus?: boolean;
}>();

function coverStyle(id: number) {
  const hue = 185 + ((id * 47) % 45);
  return {
    background: `linear-gradient(145deg, hsl(${hue} 45% 28%), hsl(${(hue + 24) % 360} 55% 46%))`,
  };
}
</script>

<template>
  <QhCard class="product" padding="none">
    <div class="product__cover" :style="product.image_url ? undefined : coverStyle(product.id)">
      <img
        v-if="product.image_url"
        :src="product.image_thumbnail_url ?? product.image_url"
        :alt="product.name"
        class="product__img"
        loading="lazy"
      />
      <span v-else class="product__cover-name">{{ product.name }}</span>
    </div>
    <div class="product__body">
      <h3>{{ product.name }}</h3>
      <p class="product__meta">
        <span class="product__price">￥{{ product.price }}</span>
        <QhTag v-if="showStatus" :tone="product.status === 'on_sale' ? 'default' : 'warning'">
          {{ product.status === 'on_sale' ? '在售' : '已下架' }}
        </QhTag>
        <span v-else-if="product.stock <= 0" class="product__sold-out">缺货</span>
      </p>
    </div>
  </QhCard>
</template>

<style scoped>
.product.qh-card {
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--tourist-line, #e6dfd3);
  border-radius: 16px;
  background: var(--tourist-surface, #fffdfa);
  box-shadow: none;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}
.product.qh-card:hover {
  transform: translateY(-4px);
  border-color: rgba(8, 145, 178, 0.3);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
}
.product__cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 170px;
  overflow: hidden;
  background: #e9e4da;
}
.product__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s ease;
}
.product:hover .product__img {
  transform: scale(1.05);
}
.product__cover-name {
  padding: 0 var(--qh-space-3);
  color: #fff;
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: var(--qh-fs-lg);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-align: center;
}
.product__body {
  padding: 14px 16px 18px;
}
.product__body h3 {
  display: -webkit-box;
  overflow: hidden;
  min-height: 42px;
  margin: 0 0 10px;
  color: var(--tourist-ink, #0b1220);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.product__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-2);
  margin: 0;
}
.product__price {
  color: var(--tourist-cyan, #0891b2);
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: 18px;
  font-weight: 700;
}
.product__sold-out {
  color: var(--qh-danger, #dc2626);
  font-size: var(--qh-fs-sm);
}
</style>

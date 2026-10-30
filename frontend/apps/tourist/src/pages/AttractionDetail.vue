<script setup lang="ts">
import { getAttractionDetail, type AttractionDetail } from '@qh/api-client';
import { QhCard, QhEmpty, QhTag } from '@qh/ui';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RouterLink, useRoute } from 'vue-router';

import { galleryOf } from '../data/attractionMedia';

const route = useRoute();
const detail = ref<AttractionDetail | null>(null);
const loading = ref(true);
const error = ref('');

/** 图片加载失败时仍保留品牌渐变兜底。 */
function bannerStyle(id: number) {
  const hue = (id * 137) % 360;
  return {
    background: `linear-gradient(120deg, hsl(${hue} 60% 38%), hsl(${(hue + 40) % 360} 65% 52%))`,
  };
}

const galleryTrack = ref<HTMLElement | null>(null);
const galleryReady = ref(false);
const activePhoto = ref(0);
const galleryPhotos = computed(() => (detail.value ? galleryOf(detail.value.name) : []));
const descriptionParagraphs = computed(() => {
  const text = detail.value?.description?.trim() ?? '';
  return text ? text.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean) : ['暂无简介'];
});

/** 首尾各放一张克隆：最后一张再向后，会真的从右侧滑入第一张，而不是倒卷。 */
const displayPhotos = computed(() => {
  const photos = galleryPhotos.value;
  if (photos.length <= 1) return photos;
  return [photos[photos.length - 1], ...photos, photos[0]];
});

let settleTimer: ReturnType<typeof setTimeout> | undefined;

function galleryWidth(): number {
  return Math.max(1, galleryTrack.value?.clientWidth ?? 1);
}

function updateActive(): void {
  const el = galleryTrack.value;
  if (!el) return;
  const count = galleryPhotos.value.length;
  if (count <= 1) {
    activePhoto.value = 0;
    return;
  }
  const raw = Math.round(el.scrollLeft / galleryWidth());
  activePhoto.value = raw <= 0 ? count - 1 : raw >= count + 1 ? 0 : raw - 1;
}

/** 滑到克隆页后，等滚动停下再瞬时归位到对应的真实页（视觉上不可见）。 */
function settleLoop(): void {
  const el = galleryTrack.value;
  const count = galleryPhotos.value.length;
  if (!el || count <= 1) return;
  const width = galleryWidth();
  const raw = Math.round(el.scrollLeft / width);
  if (raw <= 0) {
    el.scrollTo({ left: count * width, behavior: 'auto' });
  } else if (raw >= count + 1) {
    el.scrollTo({ left: width, behavior: 'auto' });
  }
}

function onGalleryScroll(): void {
  updateActive();
  if (settleTimer) clearTimeout(settleTimer);
  settleTimer = setTimeout(settleLoop, 180);
}

function scrollGallery(step: number): void {
  const el = galleryTrack.value;
  const count = galleryPhotos.value.length;
  if (!el || count <= 1) return;
  const width = galleryWidth();
  let raw = Math.round(el.scrollLeft / width);
  // 如果正停在克隆页（快速连点 / 滑动惯性），先无感归位到相邻真实页
  if (raw <= 0) {
    el.scrollTo({ left: count * width, behavior: 'auto' });
    raw = count;
  } else if (raw >= count + 1) {
    el.scrollTo({ left: width, behavior: 'auto' });
    raw = 1;
  }
  const target = Math.min(count + 1, Math.max(0, raw + step));
  el.scrollTo({ left: target * width, behavior: 'smooth' });
}

function scrollToPhoto(index: number): void {
  const el = galleryTrack.value;
  if (!el) return;
  el.scrollTo({ left: (index + 1) * galleryWidth(), behavior: 'smooth' });
}

watch(
  galleryPhotos,
  async () => {
    galleryReady.value = false;
    await nextTick();
    const el = galleryTrack.value;
    if (!el || galleryPhotos.value.length <= 1) return;
    // 初始停在真实第一张（前面有一张“最后一张”的克隆）
    el.scrollTo({ left: galleryWidth(), behavior: 'auto' });
    activePhoto.value = 0;
    galleryReady.value = true;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (settleTimer) clearTimeout(settleTimer);
});

onMounted(async () => {
  try {
    detail.value = await getAttractionDetail(Number(route.params.id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="detail">
    <p class="back">
      <RouterLink to="/attractions">← 返回景点列表</RouterLink>
    </p>

    <p v-if="loading" class="state">加载中…</p>
    <p v-else-if="error" class="state state--error">{{ error }}</p>

    <template v-else-if="detail">
      <section
        class="gallery-hero"
        :style="bannerStyle(detail.id)"
        role="group"
        aria-label="景点实景图集"
      >
        <div
          ref="galleryTrack"
          class="gallery-hero__track"
          :class="{ 'is-ready': galleryReady }"
          @scroll.passive="onGalleryScroll"
        >
          <figure
            v-for="(photo, index) in displayPhotos"
            :key="`${photo}-${index}`"
            class="gallery-hero__slide"
          >
            <img :src="photo" :alt="`${detail.name} 实景 ${index + 1}`" loading="eager" />
          </figure>
        </div>
        <div class="gallery-hero__veil" aria-hidden="true"></div>

        <div class="gallery-hero__content">
          <p class="gallery-hero__eyebrow">DESTINATION · {{ detail.city }}</p>
          <h1>{{ detail.name }}</h1>
          <div class="banner__meta">
            <QhTag tone="default">{{ detail.city }}</QhTag>
            <QhTag v-if="detail.latitude != null && detail.longitude != null" tone="default">
              {{ detail.latitude.toFixed(2) }}, {{ detail.longitude.toFixed(2) }}
            </QhTag>
          </div>
        </div>

        <div v-if="galleryPhotos.length > 1" class="gallery-hero__controls">
          <button
            type="button"
            class="gallery-hero__nav"
            aria-label="上一张实景"
            @click="scrollGallery(-1)"
          >
            ‹
          </button>
          <div class="gallery-hero__dots">
            <button
              v-for="(photo, index) in galleryPhotos"
              :key="photo"
              type="button"
              :class="{ 'is-on': activePhoto === index }"
              :aria-label="`第 ${index + 1} 张实景`"
              @click="scrollToPhoto(index)"
            ></button>
          </div>
          <button
            type="button"
            class="gallery-hero__nav"
            aria-label="下一张实景"
            @click="scrollGallery(1)"
          >
            ›
          </button>
        </div>
        <p v-if="galleryPhotos.length > 1" class="gallery-hero__hint">左右滑动查看更多实景</p>
      </section>

      <div class="layout">
        <div class="layout__main">
          <QhCard class="layout__card">
            <template #header>景点介绍</template>
            <div class="desc">
              <p v-for="(paragraph, index) in descriptionParagraphs" :key="index">
                {{ paragraph }}
              </p>
            </div>
          </QhCard>
        </div>

        <aside class="layout__side">
          <QhCard>
            <template #header>门票</template>
            <QhEmpty v-if="detail.tickets.length === 0" text="暂无可售门票" />
            <ul v-else class="tickets">
              <li v-for="ticket in detail.tickets" :key="ticket.id" class="tickets__item">
                <div>
                  <strong>{{ ticket.name }}</strong>
                  <p>{{ ticket.description || '' }}</p>
                </div>
                <span class="tickets__price">￥{{ ticket.price }}</span>
              </li>
            </ul>
          </QhCard>

          <QhCard class="layout__fill tip">
            <template #header>高原提示</template>
            <p>昼夜温差大，注意防晒与保暖；初到高原避免剧烈运动，多饮水。</p>
          </QhCard>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 宽屏两栏：主栏（介绍）+ 侧栏（门票 / 提示）；窄屏退回单栏。 */
.detail {
  max-width: var(--qh-container);
  margin: 0 auto;
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--qh-space-4);
}
.layout__card {
  height: 100%;
}
.layout__side {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-4);
}
.layout__fill {
  flex: 1;
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
.back {
  margin: 0 0 var(--qh-space-4);
  font-size: var(--qh-fs-sm);
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}

/* 顶部实景图集：横向 scroll-snap，一屏一张 */
.gallery-hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  min-height: 380px;
  margin-bottom: var(--qh-space-4);
  border-radius: 22px;
  background: #08111f;
  color: #fff;
}
.gallery-hero__track {
  position: absolute;
  inset: 0;
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  visibility: hidden;
  -webkit-overflow-scrolling: touch;
}
.gallery-hero__track.is-ready {
  visibility: visible;
}
.gallery-hero__track::-webkit-scrollbar {
  display: none;
}
.gallery-hero__slide {
  flex: 0 0 100%;
  height: 100%;
  margin: 0;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}
.gallery-hero__slide img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 60%;
}
.gallery-hero__veil {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    linear-gradient(90deg, rgba(4, 12, 24, 0.86) 0%, rgba(4, 12, 24, 0.4) 48%, transparent 100%),
    linear-gradient(0deg, rgba(4, 12, 24, 0.8) 0%, transparent 55%);
}
.gallery-hero__content {
  position: absolute;
  right: 24px;
  bottom: 28px;
  left: 32px;
  z-index: 2;
  max-width: 640px;
  pointer-events: none;
}
.gallery-hero__eyebrow {
  margin: 0 0 8px;
  color: var(--tourist-cyan-light, #67e8f9);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.2em;
}
.gallery-hero h1 {
  margin: 0 0 12px;
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: clamp(30px, 4vw, 44px);
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.15;
}
.banner__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--qh-space-2);
}
.gallery-hero__controls {
  position: absolute;
  right: 22px;
  bottom: 22px;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 10px;
}
.gallery-hero__nav {
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 50%;
  background: rgba(8, 17, 31, 0.45);
  color: #fff;
  font-family: inherit;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  backdrop-filter: blur(8px);
}
.gallery-hero__nav:hover {
  background: rgba(8, 145, 178, 0.45);
}
.gallery-hero__dots {
  display: flex;
  align-items: center;
  gap: 6px;
}
.gallery-hero__dots button {
  width: 7px;
  height: 7px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.42);
  cursor: pointer;
  transition:
    background 0.15s ease,
    transform 0.15s ease;
}
.gallery-hero__dots button.is-on {
  background: var(--tourist-cyan-light, #67e8f9);
  transform: scale(1.25);
}
.gallery-hero__hint {
  position: absolute;
  right: 24px;
  bottom: 66px;
  z-index: 3;
  margin: 0;
  color: rgba(255, 255, 255, 0.55);
  font-size: 10px;
  letter-spacing: 0.1em;
}

.desc {
  color: var(--qh-ink-2);
}
.desc p {
  margin: 0 0 14px;
  line-height: 1.9;
  white-space: pre-line;
}
.desc p:first-child {
  color: var(--tourist-ink, #0b1220);
  font-size: 15px;
}
.desc p:last-child {
  margin-bottom: 0;
}
.tip p {
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
  line-height: 1.7;
}
.tickets {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tickets__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-4);
  padding: var(--qh-space-3) 0;
  border-bottom: 1px solid var(--qh-border);
}
.tickets__item:last-child {
  border-bottom: none;
}
.tickets__item strong {
  font-size: var(--qh-fs-md);
}
.tickets__item p {
  margin: var(--qh-space-1) 0 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.tickets__price {
  color: var(--qh-primary);
  font-weight: 700;
  white-space: nowrap;
}
@media (max-width: 720px) {
  .gallery-hero {
    min-height: 300px;
    border-radius: 18px;
  }
  .gallery-hero__content {
    right: 20px;
    bottom: 64px;
    left: 24px;
  }
  .gallery-hero h1 {
    font-size: 30px;
  }
  .gallery-hero__controls {
    right: 16px;
    bottom: 16px;
  }
  .gallery-hero__hint {
    display: none;
  }
}
</style>

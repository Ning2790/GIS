<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import StarRiver from '../components/StarRiver.vue';
import { clamp01, RIVER_SAFE_X, riverHalf, riverPoint } from '../components/starRiverGeometry';

type StarTone = 'ice' | 'lavender' | 'blue' | 'violet';

interface FunctionStar {
  index: string;
  en: string;
  title: string;
  meta: string;
  desc: string;
  to: string;
  tone: StarTone;
  size: 'md' | 'lg' | 'xl';
}

/** 四颗主星，对应首页四个核心入口。 */
const functionStars: FunctionStar[] = [
  {
    index: '01',
    en: 'MAP',
    title: '地图',
    meta: '全域总览 · 三层地图',
    desc: '在行政区划、卫星影像与地形图之间切换，俯看青海的每一道山脊与湖岸。',
    to: '/map',
    tone: 'ice',
    size: 'xl',
  },
  {
    index: '02',
    en: 'DESTINATIONS',
    title: '景点概览',
    meta: '23 个高原目的地',
    desc: '从青海湖到茶卡盐湖，按主题与地区寻找下一站高原目的地。',
    to: '/attractions',
    tone: 'lavender',
    size: 'md',
  },
  {
    index: '03',
    en: 'ROUTES',
    title: '精选路线',
    meta: '环湖 · 摄影 · 人文',
    desc: '环湖、摄影与人文线路，一键套用成自己的行程再按节奏调整。',
    to: '/routes',
    tone: 'blue',
    size: 'lg',
  },
  {
    index: '04',
    en: 'MARKET',
    title: '特产商城',
    meta: '高原风物直购',
    desc: '牦牛肉干、黑枸杞、青稞与藏红花，从青海产地直达你的餐桌。',
    to: '/products',
    tone: 'violet',
    size: 'xl',
  },
];

const skyStage = ref<HTMLElement | null>(null);
const STAR_SLOTS = [0.131, 0.39, 0.63, 0.87];
const starPlacements = ref<Array<{ left: string; top: string }>>(
  STAR_SLOTS.map((slot) => ({ left: '50%', top: `${slot * 100}%` })),
);
let stageObserver: ResizeObserver | null = null;
let placementTimer = 0;

function positionStars() {
  const stage = skyStage.value;
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  const stageTop = rect.top + window.scrollY;
  const docHeight = Math.max(document.documentElement.scrollHeight, window.innerHeight * 2);
  const sideMargin =
    window.innerWidth <= 720 ? 110 : rect.width < 1000 ? Math.round(rect.width * 0.2) : 120;
  const narrow = window.innerWidth <= 720;
  const offsets = narrow ? [-0.16, 0.18, -0.14, 0.16] : [-0.24, 0.28, -0.2, 0.24];
  const viewportWidth = window.innerWidth;
  const safeInset = viewportWidth * RIVER_SAFE_X;
  const innerWidth = viewportWidth - safeInset * 2;

  starPlacements.value = STAR_SLOTS.map((slot, index) => {
    const top = rect.height * slot;
    const t = clamp01((stageTop + top) / docHeight);
    const point = riverPoint(t);
    const half = riverHalf(t);
    const normalizedX = point.x + offsets[index] * half;
    const viewportX = safeInset + normalizedX * innerWidth;
    const left = Math.min(rect.width - sideMargin, Math.max(sideMargin, viewportX - rect.left));
    return { left: `${left}px`, top: `${top}px` };
  });
}

function schedulePositionStars() {
  window.clearTimeout(placementTimer);
  placementTimer = window.setTimeout(positionStars, 80);
}

const activeStar = ref<FunctionStar | null>(null);
let previousOverflow = '';

function openStar(star: FunctionStar) {
  previousOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  activeStar.value = star;
}

function closeStar() {
  activeStar.value = null;
  document.body.style.overflow = previousOverflow;
}

function onStarKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeStar();
}

onMounted(() => {
  window.addEventListener('keydown', onStarKeydown);
  window.addEventListener('resize', schedulePositionStars);
  if (typeof ResizeObserver !== 'undefined') {
    stageObserver = new ResizeObserver(schedulePositionStars);
    stageObserver.observe(document.body);
  }
  void nextTick(positionStars);
  window.setTimeout(positionStars, 450);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onStarKeydown);
  window.removeEventListener('resize', schedulePositionStars);
  stageObserver?.disconnect();
  stageObserver = null;
  window.clearTimeout(placementTimer);
  document.body.style.overflow = previousOverflow;
});
</script>

<template>
  <StarRiver />

  <div class="galaxy-page">
    <section class="galaxy-intro">
      <p class="galaxy-intro__eyebrow">
        <span class="galaxy-intro__line" aria-hidden="true"></span>
        天境源康 · 青海高原
        <span class="galaxy-intro__line" aria-hidden="true"></span>
      </p>
      <h1>
        每一个入口，<br />都是一颗星。
        <span class="galaxy-intro__sub">点击星体，查看它通往的那一页。</span>
      </h1>
      <p class="galaxy-intro__hint">
        <span class="galaxy-intro__hint-line" aria-hidden="true"></span>
        沿星河向下
      </p>
    </section>

    <section class="galaxy-flow" aria-label="页面功能星体">
      <div ref="skyStage" class="galaxy-flow__stage">
        <button
          v-for="(star, index) in functionStars"
          :key="star.to"
          type="button"
          class="sky-star"
          :class="[`sky-star--${star.tone}`, `sky-star--${star.size}`]"
          :style="{
            left: starPlacements[index]?.left ?? '50%',
            top: starPlacements[index]?.top ?? '0px',
            '--star-delay': `${Number(star.index) * 0.7}s`,
          }"
          :aria-label="`打开${star.title}介绍`"
          aria-haspopup="dialog"
          @click="openStar(star)"
        >
          <span class="sky-star__visual" aria-hidden="true">
            <span class="sky-star__pulse"></span>
            <span class="sky-star__halo"></span>
            <span class="sky-star__aura"></span>
            <span class="sky-star__core"></span>
            <span class="sky-star__glint"></span>
          </span>
          <span class="sky-star__label">
            <small>{{ star.index }} · {{ star.en }}</small>
            <strong>{{ star.title }}</strong>
            <em>{{ star.meta }}</em>
          </span>
        </button>
      </div>
    </section>
  </div>

  <Teleport to="body">
    <Transition name="star-modal">
      <div
        v-if="activeStar"
        class="star-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="star-modal-title"
        @click.self="closeStar"
      >
        <div class="star-modal__card">
          <button type="button" class="star-modal__close" aria-label="关闭" @click="closeStar">×</button>
          <span class="star-modal__orb" :class="`star-modal__orb--${activeStar.tone}`" aria-hidden="true"></span>
          <p class="star-modal__eyebrow">STAR {{ activeStar.index }} · {{ activeStar.en }}</p>
          <h2 id="star-modal-title">{{ activeStar.title }}</h2>
          <p class="star-modal__desc">{{ activeStar.desc }}</p>
          <p class="star-modal__meta">{{ activeStar.meta }}</p>
          <RouterLink class="star-modal__cta" :to="activeStar.to">
            进入{{ activeStar.title }} <span aria-hidden="true">→</span>
          </RouterLink>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.galaxy-page {
  position: relative;
  z-index: 1;
}

/* 星河上方的细体标题 */
.galaxy-intro {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 62vh;
  padding: 9vh 0 10vh;
  text-align: center;
}
.galaxy-intro__eyebrow {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 0 0 30px;
  color: rgba(166, 190, 222, 0.78);
  font-family: 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 0.28em;
  text-transform: uppercase;
}
.galaxy-intro__line {
  width: 32px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(196, 181, 253, 0.65));
}
.galaxy-intro__line:last-child {
  background: linear-gradient(90deg, rgba(103, 232, 249, 0.55), transparent);
}
.galaxy-intro h1 {
  max-width: 920px;
  margin: 0;
  color: #f1f7ff;
  font-family: 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: clamp(36px, 5vw, 62px);
  font-weight: 300;
  line-height: 1.34;
  letter-spacing: 0.065em;
  text-shadow:
    0 2px 12px rgba(3, 12, 30, 0.32),
    0 0 26px rgba(196, 181, 253, 0.22),
    0 0 60px rgba(34, 211, 238, 0.08);
}
.galaxy-intro__sub {
  display: block;
  margin-top: 22px;
  color: rgba(170, 190, 216, 0.78);
  font-size: clamp(12px, 1.4vw, 15px);
  font-weight: 300;
  letter-spacing: 0.12em;
  line-height: 1.8;
  text-shadow: 0 0 20px rgba(103, 232, 249, 0.1);
}
.galaxy-intro__hint {
  position: absolute;
  bottom: 22px;
  left: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin: 0;
  color: rgba(146, 168, 198, 0.62);
  font-size: 9px;
  letter-spacing: 0.22em;
  transform: translateX(-50%);
}
.galaxy-intro__hint-line {
  width: 1px;
  height: 48px;
  background: linear-gradient(180deg, rgba(196, 181, 253, 0.6), transparent);
}

/* 纵向星河舞台 */
.galaxy-flow {
  position: relative;
  min-height: 1600px;
  padding-bottom: 150px;
}
.galaxy-flow__stage {
  position: relative;
  width: 100%;
  height: 1600px;
}
.sky-star {
  position: absolute;
  width: 156px;
  height: 156px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #e8f1ff;
  font: inherit;
  cursor: pointer;
  transform: translate(-50%, -50%);
}
.sky-star__visual {
  position: absolute;
  top: 50%;
  left: 50%;
  display: block;
  width: 130px;
  height: 130px;
  transform: translate(-50%, -50%);
  transition: transform 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}
.sky-star--md .sky-star__visual {
  width: 116px;
  height: 116px;
}
.sky-star--lg .sky-star__visual {
  width: 130px;
  height: 130px;
}
.sky-star--xl .sky-star__visual {
  width: 150px;
  height: 150px;
}
.sky-star__pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  width: min(220px, 26vw);
  height: min(220px, 26vw);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle, var(--star-aura) 0%, transparent 68%);
  opacity: 0.5;
  filter: blur(8px);
  animation: starPulse 8.5s ease-in-out infinite;
  animation-delay: var(--star-delay, 0s);
  pointer-events: none;
}
.sky-star__halo {
  position: absolute;
  top: 50%;
  left: 50%;
  width: min(280px, 32vw);
  height: min(280px, 32vw);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: radial-gradient(
    circle,
    var(--star-halo) 0%,
    var(--star-aura) 38%,
    rgba(255, 255, 255, 0) 70%
  );
  opacity: 0.72;
  filter: blur(16px);
  transition: opacity 0.45s ease, filter 0.45s ease, transform 0.45s ease;
  will-change: transform, opacity;
}
.sky-star__aura {
  position: absolute;
  inset: -8%;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.16) 0%,
    var(--star-aura) 40%,
    rgba(255, 255, 255, 0) 74%
  );
  opacity: 0.9;
  filter: blur(7px);
}
.sky-star__core {
  position: absolute;
  top: 35%;
  left: 35%;
  width: 30%;
  height: 30%;
  border-radius: 50%;
  background: radial-gradient(
    circle at 38% 32%,
    #fff 0%,
    var(--star-a) 18%,
    var(--star-b) 46%,
    rgba(255, 255, 255, 0) 84%
  );
  box-shadow:
    0 0 30px var(--star-halo),
    0 0 95px var(--star-aura);
  filter: blur(0.8px);
  transition: box-shadow 0.45s ease, filter 0.45s ease;
}
.sky-star__glint {
  position: absolute;
  top: 23%;
  left: 22%;
  width: 25%;
  height: 16%;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.6);
  filter: blur(4px);
  transform: rotate(-26deg);
}
.sky-star--ice {
  --star-a: #e7feff;
  --star-b: #67e8f9;
  --star-halo: rgba(34, 211, 238, 0.42);
  --star-aura: rgba(56, 189, 248, 0.13);
}
.sky-star--lavender {
  --star-a: #f4edff;
  --star-b: #a78bfa;
  --star-halo: rgba(139, 92, 246, 0.42);
  --star-aura: rgba(167, 139, 250, 0.13);
}
.sky-star--blue {
  --star-a: #e1f3ff;
  --star-b: #60a5fa;
  --star-halo: rgba(96, 165, 250, 0.4);
  --star-aura: rgba(59, 130, 246, 0.12);
}
.sky-star--violet {
  --star-a: #fbeaff;
  --star-b: #c084fc;
  --star-halo: rgba(192, 132, 252, 0.4);
  --star-aura: rgba(192, 132, 252, 0.12);
}
.sky-star__label {
  position: absolute;
  top: calc(100% + 2px);
  left: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  width: 220px;
  text-align: center;
  transform: translateX(-50%);
}
.sky-star__label small {
  color: rgba(159, 181, 212, 0.8);
  font-size: 8.5px;
  font-weight: 500;
  letter-spacing: 0.24em;
  line-height: 1.5;
}
.sky-star__label strong {
  color: rgba(235, 244, 255, 0.96);
  font-family: 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  font-weight: 400;
  letter-spacing: 0.1em;
  line-height: 1.5;
  text-shadow:
    0 1px 3px rgba(2, 8, 22, 0.9),
    0 0 16px rgba(139, 92, 246, 0.25);
}
.sky-star__label em {
  color: rgba(158, 180, 210, 0.82);
  font-size: 9.5px;
  font-style: normal;
  letter-spacing: 0.06em;
  line-height: 1.6;
}
.sky-star:hover .sky-star__visual,
.sky-star:focus-visible .sky-star__visual {
  transform: translate(-50%, -50%) scale(1.22);
}
.sky-star:hover .sky-star__halo,
.sky-star:focus-visible .sky-star__halo {
  opacity: 1;
  filter: blur(26px);
  transform: translate(-50%, -50%) scale(1.06);
}
.sky-star:hover .sky-star__core,
.sky-star:focus-visible .sky-star__core {
  filter: brightness(1.16) blur(1px);
  box-shadow:
    0 0 44px var(--star-halo),
    0 0 130px var(--star-aura);
}
.sky-star:hover .sky-star__label strong,
.sky-star:focus-visible .sky-star__label strong {
  color: #fff;
}
.sky-star:hover .sky-star__label em,
.sky-star:focus-visible .sky-star__label em {
  color: rgba(196, 181, 253, 0.9);
}
.sky-star:focus-visible {
  outline: 1px solid rgba(196, 181, 253, 0.65);
  outline-offset: 10px;
  border-radius: 50%;
}
@keyframes starPulse {
  0%,
  100% {
    opacity: 0.38;
    transform: translate(-50%, -50%) scale(0.94);
  }
  50% {
    opacity: 0.68;
    transform: translate(-50%, -50%) scale(1.08);
  }
}

/* 半透明玻璃卡片 */
.star-modal {
  position: fixed;
  inset: 0;
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(2, 7, 17, 0.62);
  backdrop-filter: blur(12px);
}
.star-modal__card {
  position: relative;
  width: min(430px, 100%);
  padding: 36px 32px 30px;
  overflow: hidden;
  border: 1px solid rgba(186, 200, 255, 0.22);
  border-radius: 26px;
  background:
    radial-gradient(circle at 50% 0%, rgba(139, 92, 246, 0.2), transparent 58%),
    linear-gradient(155deg, rgba(18, 30, 60, 0.66), rgba(6, 14, 30, 0.82));
  box-shadow:
    0 34px 90px rgba(0, 0, 0, 0.55),
    inset 0 1px rgba(255, 255, 255, 0.08);
  color: #eaf3ff;
  text-align: center;
  backdrop-filter: blur(20px);
}
.star-modal__close {
  position: absolute;
  top: 12px;
  right: 14px;
  width: 30px;
  height: 30px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  color: #d7e5ff;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}
.star-modal__orb {
  position: relative;
  display: block;
  width: 78px;
  height: 78px;
  margin: 2px auto 20px;
  border-radius: 50%;
  background: radial-gradient(
    circle at 38% 32%,
    #fff 0%,
    var(--star-a) 18%,
    var(--star-b) 46%,
    rgba(255, 255, 255, 0) 84%
  );
  box-shadow:
    0 0 34px var(--star-halo),
    0 0 100px var(--star-aura);
  filter: blur(0.8px);
}
.star-modal__orb::before {
  content: '';
  position: absolute;
  inset: -85%;
  border-radius: 50%;
  background: radial-gradient(circle, var(--star-halo), transparent 70%);
  opacity: 0.75;
  filter: blur(18px);
}
.star-modal__orb--ice {
  --star-a: #e7feff;
  --star-b: #67e8f9;
  --star-halo: rgba(34, 211, 238, 0.45);
  --star-aura: rgba(56, 189, 248, 0.13);
}
.star-modal__orb--lavender {
  --star-a: #f4edff;
  --star-b: #a78bfa;
  --star-halo: rgba(139, 92, 246, 0.45);
  --star-aura: rgba(167, 139, 250, 0.13);
}
.star-modal__orb--blue {
  --star-a: #e1f3ff;
  --star-b: #60a5fa;
  --star-halo: rgba(96, 165, 250, 0.42);
  --star-aura: rgba(59, 130, 246, 0.12);
}
.star-modal__orb--violet {
  --star-a: #fbeaff;
  --star-b: #c084fc;
  --star-halo: rgba(192, 132, 252, 0.42);
  --star-aura: rgba(192, 132, 252, 0.12);
}
.star-modal__eyebrow {
  margin: 0 0 8px;
  color: rgba(167, 195, 230, 0.72);
  font-size: 9px;
  font-weight: 500;
  letter-spacing: 0.26em;
}
.star-modal h2 {
  margin: 0 0 14px;
  color: #f4f9ff;
  font-family: 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 28px;
  font-weight: 300;
  letter-spacing: 0.08em;
}
.star-modal__desc {
  margin: 0 0 14px;
  color: rgba(190, 205, 228, 0.86);
  font-size: 13.5px;
  font-weight: 300;
  line-height: 1.9;
}
.star-modal__meta {
  margin: 0 0 24px;
  color: rgba(158, 186, 222, 0.68);
  font-size: 10px;
  letter-spacing: 0.08em;
}
.star-modal__cta {
  display: inline-flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 18px;
  border: 1px solid rgba(214, 226, 255, 0.18);
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(109, 88, 220, 0.9), rgba(14, 165, 233, 0.88));
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.04em;
  box-shadow: 0 12px 30px rgba(14, 32, 74, 0.4);
}
.star-modal__cta:hover {
  text-decoration: none;
  filter: brightness(1.08);
}
.star-modal-enter-active,
.star-modal-leave-active {
  transition: opacity 0.22s ease;
}
.star-modal-enter-active .star-modal__card,
.star-modal-leave-active .star-modal__card {
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.22s ease;
}
.star-modal-enter-from,
.star-modal-leave-to {
  opacity: 0;
}
.star-modal-enter-from .star-modal__card,
.star-modal-leave-to .star-modal__card {
  transform: translateY(16px) scale(0.96);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .sky-star__pulse {
    animation: none;
  }
  .sky-star__visual,
  .sky-star__halo,
  .sky-star__core {
    transition: none;
  }
}

@media (max-width: 720px) {
  .galaxy-intro {
    min-height: 56vh;
    padding: 7vh 0 8vh;
  }
  .galaxy-intro__eyebrow {
    margin-bottom: 22px;
    font-size: 9px;
    letter-spacing: 0.2em;
  }
  .galaxy-intro h1 {
    font-size: 34px;
    line-height: 1.4;
  }
  .galaxy-intro__sub {
    margin-top: 16px;
    font-size: 12px;
  }
  .galaxy-intro__hint-line {
    height: 34px;
  }
  .galaxy-flow {
    min-height: 1280px;
    padding-bottom: 90px;
  }
  .galaxy-flow__stage {
    height: 1280px;
  }
  .sky-star {
    width: 128px;
    height: 128px;
  }
  .sky-star__visual {
    width: 82px;
    height: 82px;
  }
  .sky-star--md .sky-star__visual {
    width: 78px;
    height: 78px;
  }
  .sky-star--lg .sky-star__visual {
    width: 88px;
    height: 88px;
  }
  .sky-star--xl .sky-star__visual {
    width: 96px;
    height: 96px;
  }
  .sky-star__label {
    width: 176px;
    gap: 4px;
  }
  .sky-star__label small {
    font-size: 8px;
    letter-spacing: 0.17em;
  }
  .sky-star__label strong {
    font-size: 13px;
  }
  .sky-star__label em {
    font-size: 9px;
  }
  .star-modal__card {
    padding: 32px 24px 26px;
  }
}
</style>

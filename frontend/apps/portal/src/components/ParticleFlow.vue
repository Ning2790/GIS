<script setup lang="ts">
/** 门户背景粒子流场。
 *
 * 轻量 Canvas 2D：粒子沿正弦流场缓慢漂移，带短拖尾与轻微辉光。
 * - 不拦截鼠标事件（pointer-events: none），纯背景氛围；
 * - prefers-reduced-motion: reduce 时只画静态星点，不启动动画；
 * - 页面隐藏时暂停，重新可见时恢复；DPR 上限 2，避免高分屏过度绘制。
 */

import { onBeforeUnmount, onMounted, ref } from 'vue';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  hue: number;
  /** 个体方向偏置，避免所有粒子朝同一个方向流。 */
  angleOffset: number;
  /** 个体速度倍率，制造快慢层次。 */
  speedScale: number;
  /** 个体拖尾长度倍率。 */
  trailScale: number;
}

const canvas = ref<HTMLCanvasElement | null>(null);

let ctx: CanvasRenderingContext2D | null = null;
let width = 0;
let height = 0;
let dpr = 1;
let particles: Particle[] = [];
let frameId = 0;
let running = false;
let reducedMotion = false;
let resizeObserver: ResizeObserver | null = null;

function seed(): void {
  const count = Math.max(32, Math.min(78, Math.round((width * height) / 20000)));
  // 分层抖动：把画布切成网格，每个格子随机取一点，避免粒子扎堆。
  const cols = Math.ceil(Math.sqrt(count * (width / height)));
  const rows = Math.ceil(count / cols);
  const cellW = width / cols;
  const cellH = height / rows;

  particles = Array.from({ length: count }, (_, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    return {
      x: (col + Math.random()) * cellW,
      y: (row + Math.random()) * cellH,
      vx: 0,
      vy: 0,
      size: 0.8 + Math.pow(Math.random(), 1.8) * 2.8,
      alpha: 0.16 + Math.random() * 0.46,
      hue: Math.random() > 0.45 ? 188 : 208,
      angleOffset: (Math.random() - 0.5) * 1.0,
      speedScale: 0.55 + Math.random() * 0.6,
      trailScale: 0.7 + Math.random() * 0.7,
    };
  });
}

/** 流场方向：整体略微向右上，叠加两组正弦扰动，形成缓慢的“水流”。 */
function flowAngle(x: number, y: number, t: number): number {
  return (
    Math.sin(x * 0.0022 + t * 0.22) * 0.95 +
    Math.cos(y * 0.0028 - t * 0.15) * 0.7 -
    0.22
  );
}

function drawStatic(): void {
  if (!ctx) return;
  ctx.clearRect(0, 0, width, height);
  for (const p of particles) {
    ctx.beginPath();
    ctx.fillStyle = `hsla(${p.hue}, 92%, 68%, ${p.alpha})`;
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawFrame(t: number): void {
  if (!ctx) return;
  ctx.clearRect(0, 0, width, height);
  ctx.globalCompositeOperation = 'lighter';

  for (const p of particles) {
    const angle = flowAngle(p.x, p.y, t) + p.angleOffset;
    const targetVx = Math.cos(angle) * 0.85 * p.speedScale;
    const targetVy = Math.sin(angle) * 0.85 * p.speedScale;
    // 平滑转向，避免方向突变；速度约 0.7px/帧
    p.vx += (targetVx - p.vx) * 0.035;
    p.vy += (targetVy - p.vy) * 0.035;
    p.x += p.vx;
    p.y += p.vy;

    // 环绕边界，粒子离场后从另一侧回来
    if (p.x < -24) p.x = width + 24;
    if (p.x > width + 24) p.x = -24;
    if (p.y < -24) p.y = height + 24;
    if (p.y > height + 24) p.y = -24;

    // 拖尾：从稍早的位置画到当前位置
    const tail = (18 + p.size * 5) * p.trailScale;
    const tx = p.x - p.vx * tail;
    const ty = p.y - p.vy * tail;
    const gradient = ctx.createLinearGradient(tx, ty, p.x, p.y);
    gradient.addColorStop(0, `hsla(${p.hue}, 92%, 68%, 0)`);
    gradient.addColorStop(1, `hsla(${p.hue}, 95%, 70%, ${p.alpha})`);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = p.size * 0.75;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();

    // 柔和辉光 + 粒子头部
    ctx.beginPath();
    ctx.fillStyle = `hsla(${p.hue}, 95%, 62%, ${p.alpha * 0.12})`;
    ctx.arc(p.x, p.y, p.size * 3.4, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.fillStyle = `hsla(${p.hue}, 95%, 74%, ${p.alpha})`;
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.globalCompositeOperation = 'source-over';
}

function loop(now: number): void {
  if (!running) return;
  drawFrame(now / 1000);
  frameId = requestAnimationFrame(loop);
}

function start(): void {
  if (!ctx || running || reducedMotion) return;
  running = true;
  frameId = requestAnimationFrame(loop);
}

function stop(): void {
  running = false;
  cancelAnimationFrame(frameId);
}

function resize(): void {
  const el = canvas.value;
  if (!el || !ctx) return;
  const rect = el.getBoundingClientRect();
  width = Math.max(1, rect.width);
  height = Math.max(1, rect.height);
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  el.width = Math.round(width * dpr);
  el.height = Math.round(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  seed();
  if (reducedMotion) {
    drawStatic();
  }
}

function handleVisibility(): void {
  if (document.hidden) {
    stop();
    return;
  }
  if (!reducedMotion) start();
}

onMounted(() => {
  const el = canvas.value;
  if (!el) return;
  try {
    ctx = el.getContext('2d');
  } catch {
    ctx = null;
  }
  if (!ctx) return;

  reducedMotion =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  resize();

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => resize());
    resizeObserver.observe(el);
  } else {
    window.addEventListener('resize', resize);
  }
  document.addEventListener('visibilitychange', handleVisibility);

  if (!reducedMotion) start();
});

onBeforeUnmount(() => {
  stop();
  resizeObserver?.disconnect();
  resizeObserver = null;
  window.removeEventListener('resize', resize);
  document.removeEventListener('visibilitychange', handleVisibility);
});
</script>

<template>
  <canvas ref="canvas" aria-hidden="true"></canvas>
</template>

<style scoped>
canvas {
  display: block;
}
</style>

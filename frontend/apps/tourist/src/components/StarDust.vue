<script setup lang="ts">
/**
 * 地图 / 旅游 / 商城 / AI / 客服等模块的轻量星尘背景。
 *
 * 透明 Canvas，只作为空白背景的底层点缀；顶部/主内容/页脚都在更高层级。
 * 主体是细小星点，少量四角星高光；颜色克制、动画缓慢。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue';

type DustKind = 'dot' | 'soft' | 'spark';

interface DustParticle {
  x: number;
  y: number;
  size: number;
  alpha: number;
  phase: number;
  twinkleSpeed: number;
  driftY: number;
  swayAmp: number;
  swayPhase: number;
  swaySpeed: number;
  kind: DustKind;
  rotation: number;
  color: string;
}

const canvas = ref<HTMLCanvasElement | null>(null);

// 浅蓝为主，少量更柔的浅天蓝；亮星中心才用白色，不出现金光或深色星。
const PALE_BLUE = '96, 165, 250';
const SOFT_BLUE = '147, 197, 253';
const DUST_COUNT_DIVISOR = 26000;

let ctx: CanvasRenderingContext2D | null = null;
let particles: DustParticle[] = [];
let vw = 1;
let vh = 1;
let dpr = 1;
let raf = 0;
let lastFrame = 0;
let reduced = false;
const spriteCache = new Map<string, HTMLCanvasElement>();

function pickColor(): string {
  return Math.random() < 0.72 ? PALE_BLUE : SOFT_BLUE;
}

function pickKind(index: number): DustKind {
  if (index === 0) return 'spark';
  const roll = Math.random();
  if (roll < 0.15) return 'spark';
  if (roll < 0.5) return 'soft';
  return 'dot';
}

function starSprite(kind: DustKind, color: string): HTMLCanvasElement {
  const key = `${kind}|${color}`;
  const cached = spriteCache.get(key);
  if (cached) return cached;

  const size = 96;
  const half = size / 2;
  const sprite = document.createElement('canvas');
  sprite.width = size;
  sprite.height = size;
  const c = sprite.getContext('2d');
  if (!c) return sprite;

  if (kind === 'spark') {
    const halo = c.createRadialGradient(half, half, 0, half, half, half);
    halo.addColorStop(0, `rgba(${color}, 0.36)`);
    halo.addColorStop(0.36, `rgba(${color}, 0.12)`);
    halo.addColorStop(0.74, `rgba(${color}, 0.02)`);
    halo.addColorStop(1, `rgba(${color}, 0)`);
    c.fillStyle = halo;
    c.fillRect(0, 0, size, size);

    const star = c.createRadialGradient(half, half, 0, half, half, half * 0.92);
    star.addColorStop(0, 'rgba(255, 255, 255, 0.96)');
    star.addColorStop(0.14, `rgba(${color}, 0.96)`);
    star.addColorStop(0.44, `rgba(${color}, 0.56)`);
    star.addColorStop(0.8, `rgba(${color}, 0.08)`);
    star.addColorStop(1, `rgba(${color}, 0)`);

    c.save();
    c.translate(half, half);
    const reach = half * 0.92;
    const waist = half * 0.09;
    c.fillStyle = star;
    c.beginPath();
    c.moveTo(0, -reach);
    c.quadraticCurveTo(waist, -waist, reach, 0);
    c.quadraticCurveTo(waist, waist, 0, reach);
    c.quadraticCurveTo(-waist, waist, -reach, 0);
    c.quadraticCurveTo(-waist, -waist, 0, -reach);
    c.closePath();
    c.fill();
    c.restore();
  } else {
    const glow = c.createRadialGradient(half, half, 0, half, half, half);
    if (kind === 'soft') {
      glow.addColorStop(0, `rgba(${color}, 0.94)`);
      glow.addColorStop(0.18, `rgba(${color}, 0.54)`);
      glow.addColorStop(0.48, `rgba(${color}, 0.15)`);
      glow.addColorStop(1, `rgba(${color}, 0)`);
    } else {
      glow.addColorStop(0, `rgba(${color}, 0.96)`);
      glow.addColorStop(0.3, `rgba(${color}, 0.5)`);
      glow.addColorStop(0.62, `rgba(${color}, 0.1)`);
      glow.addColorStop(1, `rgba(${color}, 0)`);
    }
    c.fillStyle = glow;
    c.fillRect(0, 0, size, size);
  }

  spriteCache.set(key, sprite);
  return sprite;
}

function createParticle(index: number): DustParticle {
  const kind = pickKind(index);
  const size =
    kind === 'spark'
      ? 28 + Math.random() * 8
      : kind === 'soft'
        ? 16 + Math.random() * 5
        : 9 + Math.random() * 4;
  const alpha =
    kind === 'spark'
      ? 0.9 + Math.random() * 0.1
      : kind === 'soft'
        ? 0.75 + Math.random() * 0.13
        : 0.7 + Math.random() * 0.15;
  return {
    x: Math.random() * vw,
    y: Math.random() * vh,
    size,
    alpha,
    phase: Math.random() * Math.PI * 2,
    twinkleSpeed: 0.12 + Math.random() * 0.22,
    driftY: 2 + Math.random() * 2.6,
    swayAmp: 5 + Math.random() * 9,
    swayPhase: Math.random() * Math.PI * 2,
    swaySpeed: 0.05 + Math.random() * 0.1,
    kind,
    rotation: Math.random() * Math.PI * 2,
    color: pickColor(),
  };
}

function buildParticles() {
  const count = Math.max(28, Math.min(40, Math.round((vw * vh) / DUST_COUNT_DIVISOR)));
  particles = Array.from({ length: count }, (_, index) => createParticle(index));
  const rank: Record<DustKind, number> = { dot: 0, soft: 1, spark: 2 };
  particles.sort((a, b) => rank[a.kind] - rank[b.kind]);
}

function resizeCanvas() {
  const el = canvas.value;
  if (!el) return;
  vw = Math.max(1, window.innerWidth);
  vh = Math.max(1, window.innerHeight);
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  el.width = Math.round(vw * dpr);
  el.height = Math.round(vh * dpr);
  el.style.width = `${vw}px`;
  el.style.height = `${vh}px`;
  ctx = el.getContext('2d');
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  buildParticles();
  render(performance.now(), 0);
}

function smoothstep(value: number): number {
  const t = Math.min(1, Math.max(0, value));
  return t * t * (3 - 2 * t);
}

/** 靠近视口边缘时连续淡出，星星不会在边界突然出现或消失。 */
function edgeFade(x: number, y: number): number {
  const margin = 48;
  return (
    smoothstep(Math.min(x, vw - x) / margin) *
    smoothstep(Math.min(y, vh - y) / margin)
  );
}

function drawParticle(particle: DustParticle, x: number, y: number, twinkle: number) {
  if (!ctx) return;
  const alpha = particle.alpha * twinkle * edgeFade(x, y);
  if (alpha <= 0.003) return;
  const sprite = starSprite(particle.kind, particle.color);
  ctx.globalAlpha = alpha;

  if (particle.kind === 'spark') {
    const halo = particle.size * 2;
    ctx.globalAlpha = alpha * 0.22;
    ctx.drawImage(starSprite('soft', particle.color), x - halo / 2, y - halo / 2, halo, halo);
    ctx.globalAlpha = alpha;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(particle.rotation);
    ctx.drawImage(sprite, -particle.size / 2, -particle.size / 2, particle.size, particle.size);
    ctx.restore();
    return;
  }

  ctx.drawImage(sprite, x - particle.size / 2, y - particle.size / 2, particle.size, particle.size);
}

/** dt 为毫秒；为 0 时只画静态帧。 */
function render(now: number, dt: number) {
  if (!ctx) return;
  const time = now / 1000;
  ctx.clearRect(0, 0, vw, vh);

  for (const particle of particles) {
    if (dt > 0) {
      particle.y -= (particle.driftY * dt) / 1000;
      if (particle.y < -36) {
        particle.y = vh + 36;
        particle.x = Math.random() * vw;
      }
    }

    const x = particle.x + Math.sin(time * particle.swaySpeed + particle.swayPhase) * particle.swayAmp;
    const y = particle.y;
    if (y < -40 || y > vh + 40) continue;

    const breath = 0.8 + 0.2 * Math.sin(time * particle.twinkleSpeed + particle.phase);
    drawParticle(particle, x, y, reduced ? 0.9 : breath);
  }

  ctx.globalAlpha = 1;
}

function loop(now: number) {
  const elapsed = lastFrame ? Math.min(now - lastFrame, 64) : 16;
  lastFrame = now;
  render(now, reduced ? 0 : elapsed);
  raf = requestAnimationFrame(loop);
}

function start() {
  if (raf || reduced) return;
  lastFrame = 0;
  raf = requestAnimationFrame(loop);
}

function stop() {
  cancelAnimationFrame(raf);
  raf = 0;
}

function onResize() {
  resizeCanvas();
}

function onVisibility() {
  if (document.hidden) stop();
  else start();
}

onMounted(() => {
  reduced =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  resizeCanvas();
  window.addEventListener('resize', onResize);
  document.addEventListener('visibilitychange', onVisibility);
  if (!reduced) start();
});

onBeforeUnmount(() => {
  stop();
  window.removeEventListener('resize', onResize);
  document.removeEventListener('visibilitychange', onVisibility);
  ctx = null;
  particles = [];
});
</script>

<template>
  <canvas ref="canvas" class="star-dust-canvas" aria-hidden="true"></canvas>
</template>

<style scoped>
.star-dust-canvas {
  position: fixed;
  inset: 0;
  z-index: 0;
  display: block;
  width: 100vw;
  height: 100vh;
  opacity: 1;
  pointer-events: none;
}
</style>

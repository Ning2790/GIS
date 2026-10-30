<script setup lang="ts">
/**
 * 首页 S 型星云河道。
 *
 * 原生 Canvas 2D，不依赖任何图片或第三方库：
 * - 中心线由三次贝塞尔曲线定义（见 starRiverGeometry.ts）；
 * - 星云由多层预渲染柔光精灵沿曲线叠加，中心亮、两侧透明雾化；
 * - 所有星点都按“河道参数 t + 横向偏移”生成，不会跑到河道外；
 * - 三层不同滚动系数形成视差；
 * - 星云边缘、粒子沿河漂移和明暗闪烁全部逐帧动画。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue';

import { clamp01, RIVER_SAFE_X, riverHalf, riverPoint } from './starRiverGeometry';

interface StarParticle {
  t: number;
  offset: number;
  size: number;
  brightness: number;
  phase: number;
  twinkleSpeed: number;
  driftT: number;
  driftPhase: number;
  driftSpeed: number;
  color: string;
  sparkle: boolean;
  layer: 0 | 1 | 2;
  vT?: number;
  vOffset?: number;
}

interface NebulaPuff {
  t: number;
  offset: number;
  size: number;
  phase: number;
  speed: number;
  tone: 0 | 1 | 2 | 3;
  opacity: number;
  layer: 0 | 1 | 2;
}

const canvas = ref<HTMLCanvasElement | null>(null);

let ctx: CanvasRenderingContext2D | null = null;
let vw = 1;
let vh = 1;
let dpr = 1;
let docH = 1;
let stars: StarParticle[] = [];
let puffs: NebulaPuff[] = [];
let targetScroll = 0;
let parallaxScroll = 0;
let raf = 0;
let lastFrame = 0;
let frameBudget = 0;
const FRAME_INTERVAL = 1000 / 60;
let reduced = false;
let observer: ResizeObserver | null = null;
let rebuildTimer = 0;
let safeInset = 0;
let innerWidth = 1;
function projectX(x: number): number {
  return safeInset + x * innerWidth;
}

const starSpriteCache = new Map<string, HTMLCanvasElement>();
const haloSpriteCache = new Map<string, HTMLCanvasElement>();
const puffSpriteCache = new Map<number, HTMLCanvasElement>();

// 三层深度：远处大而淡、近处小而亮。factor 就是页面滚动系数。
const NEBULA_LAYERS = [
  { factor: 0.9, alpha: 0.58, sizeScale: 1.15 },
  { factor: 0.95, alpha: 0.82, sizeScale: 1.0 },
  { factor: 1.0, alpha: 0.7, sizeScale: 0.86 },
] as const;
const STAR_LAYERS = [
  { factor: 0.86, scale: 0.55, alpha: 0.42 },
  { factor: 0.94, scale: 0.9, alpha: 0.75 },
  { factor: 1.0, scale: 1.3, alpha: 1 },
] as const;

const STAR_COLORS = [
  '198, 243, 255',
  '236, 248, 255',
  '220, 232, 255',
  '204, 190, 255',
  '154, 232, 255',
];
const GOLD_COLORS = ['238, 204, 132', '250, 226, 170'];
function pickStarColor(): string {
  if (Math.random() < 0.13) return GOLD_COLORS[Math.floor(Math.random() * GOLD_COLORS.length)];
  return STAR_COLORS[Math.floor(Math.random() * STAR_COLORS.length)];
}

function starSprite(color: string, sparkle: boolean): HTMLCanvasElement {
  const key = `${color}|${sparkle ? 'cross' : 'glow'}`;
  const cached = starSpriteCache.get(key);
  if (cached) return cached;

  const size = 96;
  const half = size / 2;
  const sprite = document.createElement('canvas');
  sprite.width = size;
  sprite.height = size;
  const c = sprite.getContext('2d');
  if (!c) return sprite;
  c.filter = sparkle ? 'blur(0.8px)' : 'blur(1.3px)';

  const glow = c.createRadialGradient(half, half, 0, half, half, half);
  glow.addColorStop(0, `rgba(${color}, 1)`);
  glow.addColorStop(0.06, `rgba(${color}, 0.96)`);
  glow.addColorStop(0.18, `rgba(${color}, 0.3)`);
  glow.addColorStop(0.52, `rgba(${color}, 0.07)`);
  glow.addColorStop(1, `rgba(${color}, 0)`);
  c.fillStyle = glow;
  c.beginPath();
  c.arc(half, half, half, 0, Math.PI * 2);
  c.fill();

  if (sparkle) {
    c.lineCap = 'round';
    c.strokeStyle = `rgba(${color}, 0.78)`;
    c.lineWidth = 1.2;
    c.beginPath();
    c.moveTo(half, 10);
    c.lineTo(half, size - 10);
    c.moveTo(10, half);
    c.lineTo(size - 10, half);
    c.stroke();
    c.globalAlpha = 0.4;
    c.lineWidth = 0.8;
    c.beginPath();
    c.moveTo(26, 26);
    c.lineTo(size - 26, size - 26);
    c.moveTo(size - 26, 26);
    c.lineTo(26, size - 26);
    c.stroke();
    c.globalAlpha = 1;
  }

  c.filter = 'none';
  starSpriteCache.set(key, sprite);
  return sprite;
}

/** 近景大星额外的大光晕（颜色沿用现有星色）。 */
function haloSprite(color: string): HTMLCanvasElement {
  const cached = haloSpriteCache.get(color);
  if (cached) return cached;
  const size = 128;
  const half = size / 2;
  const sprite = document.createElement('canvas');
  sprite.width = size;
  sprite.height = size;
  const c = sprite.getContext('2d');
  if (!c) return sprite;
  c.filter = 'blur(9px)';
  const gradient = c.createRadialGradient(half, half, 0, half, half, half);
  gradient.addColorStop(0, `rgba(${color}, 0.4)`);
  gradient.addColorStop(0.3, `rgba(${color}, 0.15)`);
  gradient.addColorStop(0.66, `rgba(${color}, 0.035)`);
  gradient.addColorStop(1, `rgba(${color}, 0)`);
  c.fillStyle = gradient;
  c.fillRect(0, 0, size, size);
  c.filter = 'none';
  haloSpriteCache.set(color, sprite);
  return sprite;
}

/** 星云柔光精灵：tone0 深墨核心、tone1 蓝雾、tone2 淡紫、tone3 亮核。 */
function puffSprite(tone: 0 | 1 | 2 | 3): HTMLCanvasElement {
  const cached = puffSpriteCache.get(tone);
  if (cached) return cached;

  const size = 256;
  const half = size / 2;
  const sprite = document.createElement('canvas');
  sprite.width = size;
  sprite.height = size;
  const c = sprite.getContext('2d');
  if (!c) return sprite;

  c.filter = 'blur(16px)';
  const gradient = c.createRadialGradient(half, half, 0, half, half, half);
  if (tone === 0) {
    gradient.addColorStop(0, 'rgba(4, 12, 34, 0.94)');
    gradient.addColorStop(0.28, 'rgba(9, 28, 68, 0.72)');
    gradient.addColorStop(0.62, 'rgba(18, 53, 108, 0.24)');
    gradient.addColorStop(1, 'rgba(18, 53, 108, 0)');
  } else if (tone === 1) {
    gradient.addColorStop(0, 'rgba(27, 66, 132, 0.56)');
    gradient.addColorStop(0.42, 'rgba(44, 100, 168, 0.25)');
    gradient.addColorStop(1, 'rgba(44, 100, 168, 0)');
  } else if (tone === 2) {
    gradient.addColorStop(0, 'rgba(92, 72, 176, 0.34)');
    gradient.addColorStop(0.44, 'rgba(125, 110, 205, 0.15)');
    gradient.addColorStop(1, 'rgba(125, 110, 205, 0)');
  } else {
    gradient.addColorStop(0, 'rgba(190, 235, 255, 0.26)');
    gradient.addColorStop(0.34, 'rgba(160, 195, 255, 0.1)');
    gradient.addColorStop(1, 'rgba(160, 195, 255, 0)');
  }
  c.fillStyle = gradient;
  c.fillRect(0, 0, size, size);
  c.filter = 'none';
  puffSpriteCache.set(tone, sprite);
  return sprite;
}

type BandKind = 'outer' | 'core' | 'glow';
const bandSpriteCache = new Map<BandKind, HTMLCanvasElement>();

/** 河道横截面：中心深、两侧透明，竖向再羽化，叠成连续的 S 形水带。 */
function bandSprite(kind: BandKind): HTMLCanvasElement {
  const cached = bandSpriteCache.get(kind);
  if (cached) return cached;

  const width = 1024;
  const height = 192;
  const sprite = document.createElement('canvas');
  sprite.width = width;
  sprite.height = height;
  const c = sprite.getContext('2d');
  if (!c) return sprite;

  // 用横截面径向渐变代替原来的线性横条：中心深、外缘先转淡色再化入白色，
  // 中段留出很长的半透明过渡带，避免在带边形成一圈可辨认的轮廓线。
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = width / 2;
  c.filter = 'blur(22px)';
  const feather = c.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
  if (kind === 'core') {
    feather.addColorStop(0, 'rgba(2, 9, 24, 1)');
    feather.addColorStop(0.16, 'rgba(2, 9, 24, 1)');
    feather.addColorStop(0.28, 'rgba(3, 12, 30, 0.98)');
    feather.addColorStop(0.4, 'rgba(5, 18, 44, 0.93)');
    feather.addColorStop(0.5, 'rgba(8, 26, 58, 0.78)');
    feather.addColorStop(0.6, 'rgba(12, 38, 86, 0.55)');
    feather.addColorStop(0.7, 'rgba(18, 57, 112, 0.3)');
    feather.addColorStop(0.8, 'rgba(26, 77, 142, 0.1)');
    feather.addColorStop(0.88, 'rgba(50, 105, 165, 0.035)');
    feather.addColorStop(0.94, 'rgba(120, 170, 220, 0.01)');
    feather.addColorStop(1, 'rgba(255, 255, 255, 0)');
  } else if (kind === 'glow') {
    feather.addColorStop(0, 'rgba(210, 240, 255, 0.24)');
    feather.addColorStop(0.18, 'rgba(200, 235, 255, 0.18)');
    feather.addColorStop(0.35, 'rgba(180, 220, 255, 0.1)');
    feather.addColorStop(0.55, 'rgba(160, 210, 255, 0.045)');
    feather.addColorStop(0.75, 'rgba(150, 200, 255, 0.015)');
    feather.addColorStop(1, 'rgba(170, 220, 255, 0)');
  } else {
    feather.addColorStop(0, 'rgba(16, 44, 96, 0.52)');
    feather.addColorStop(0.12, 'rgba(16, 44, 96, 0.44)');
    feather.addColorStop(0.3, 'rgba(42, 88, 155, 0.24)');
    feather.addColorStop(0.45, 'rgba(42, 88, 155, 0.14)');
    feather.addColorStop(0.6, 'rgba(80, 130, 190, 0.06)');
    feather.addColorStop(0.75, 'rgba(120, 170, 220, 0.02)');
    feather.addColorStop(0.88, 'rgba(180, 210, 240, 0.005)');
    feather.addColorStop(1, 'rgba(40, 82, 145, 0)');
  }
  c.fillStyle = feather;
  c.fillRect(0, 0, width, height);
  c.filter = 'none';

  // 上下方向再羽化，叠段时不会出现横向接缝。
  c.globalCompositeOperation = 'destination-in';
  const vertical = c.createLinearGradient(0, 0, 0, height);
  vertical.addColorStop(0, 'rgba(0, 0, 0, 0)');
  vertical.addColorStop(0.16, 'rgba(0, 0, 0, 0.6)');
  vertical.addColorStop(0.3, 'rgba(0, 0, 0, 0.95)');
  vertical.addColorStop(0.7, 'rgba(0, 0, 0, 0.95)');
  vertical.addColorStop(0.84, 'rgba(0, 0, 0, 0.6)');
  vertical.addColorStop(1, 'rgba(0, 0, 0, 0)');
  c.fillStyle = vertical;
  c.fillRect(0, 0, width, height);
  c.globalCompositeOperation = 'source-over';

  bandSpriteCache.set(kind, sprite);
  return sprite;
}

function buildScene() {
  puffs = [];
  stars = [];

  // 中心密、边缘疏：横向偏移向 0 收敛
  const surfaceOffset = (max = 0.78) => {
    const u = Math.random();
    return (Math.random() < 0.5 ? -1 : 1) * Math.pow(u, 1.65) * max;
  };

  // 星云边缘的碎雾；主体由连续 bandSprite 叠出，这里只负责不规则轮廓
  for (let layer = 0; layer < 3; layer += 1) {
    const layerInfo = NEBULA_LAYERS[layer];
    for (let i = 0; i < 24; i += 1) {
      const t = (i + Math.random() * 0.8) / 24;
      const side = Math.random() > 0.5 ? 1 : -1;
      const offset = side * (0.82 + Math.random() * 0.3);
      puffs.push({
        t,
        offset,
        size: vw * (0.04 + Math.random() * 0.06) * layerInfo.sizeScale,
        phase: Math.random() * Math.PI * 2,
        speed: 0.035 + Math.random() * 0.08,
        tone: Math.random() > 0.6 ? 2 : 1,
        opacity: 0.08 + Math.random() * 0.13,
        layer: layer as 0 | 1 | 2,
      });
    }
  }

  // 标题下方的柔和星河池：让浅白细体字落在深色星云上
  for (let i = 0; i < 5; i += 1) {
    puffs.push({
      t: 0.1 + i * 0.035,
      offset: (i - 2) * 0.18,
      size: vw * (0.24 + i * 0.025),
      phase: Math.random() * Math.PI * 2,
      speed: 0.02 + Math.random() * 0.03,
      tone: 0,
      opacity: 0.55,
      layer: 1,
    });
  }

  // 所有星点都在河道参数内：横向偏移最大 ±0.78 个半宽
  for (let i = 0; i < 1700; i += 1) {
    const t = Math.random();
    const offset = surfaceOffset(0.78);
    const depthRoll = Math.random();
    const layer: 0 | 1 | 2 = depthRoll < 0.36 ? 0 : depthRoll < 0.72 ? 1 : 2;
    const bright = Math.pow(Math.random(), 1.55);
    const size = 0.55 + bright * 2.55;
    stars.push({
      t,
      offset,
      size,
      brightness: 0.3 + bright * 0.7,
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: 0.16 + Math.random() * 0.42,
      driftT: 0.0004 + Math.random() * 0.0018,
      driftPhase: Math.random() * Math.PI * 2,
      driftSpeed: 0.035 + Math.random() * 0.1,
      color: pickStarColor(),
      sparkle: bright > 0.72 || Math.random() > 0.9,
      layer,
    });
  }

  // 河心再补一层细密星点，让中心比两侧更亮
  for (let i = 0; i < 550; i += 1) {
    const t = Math.random();
    const bright = Math.pow(Math.random(), 1.5);
    stars.push({
      t,
      offset: surfaceOffset(0.5),
      size: 0.45 + bright * 1.7,
      brightness: 0.35 + bright * 0.55,
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: 0.18 + Math.random() * 0.4,
      driftT: 0.0004 + Math.random() * 0.0014,
      driftPhase: Math.random() * Math.PI * 2,
      driftSpeed: 0.03 + Math.random() * 0.09,
      color: pickStarColor(),
      sparkle: bright > 0.8,
      layer: Math.random() > 0.35 ? 2 : 1,
    });
  }

  // 少数大星作为视觉锚点，更靠近河心
  for (let i = 0; i < 28; i += 1) {
    const t = Math.random();
    stars.push({
      t,
      offset: surfaceOffset(0.5),
      size: 1.7 + Math.random() * 1.25,
      brightness: 0.75 + Math.random() * 0.22,
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: 0.12 + Math.random() * 0.26,
      driftT: 0.0003 + Math.random() * 0.0012,
      driftPhase: Math.random() * Math.PI * 2,
      driftSpeed: 0.03 + Math.random() * 0.08,
      color: Math.random() > 0.5 ? '236, 248, 255' : '204, 190, 255',
      sparkle: true,
      layer: 2,
    });
  }

  // 微尘：更小更淡，全部在河宽内
  for (let i = 0; i < 380; i += 1) {
    const t = Math.random();
    const depthRoll = Math.random();
    stars.push({
      t,
      offset: surfaceOffset(0.78),
      size: 0.5 + Math.random() * 1.2,
      brightness: 0.18 + Math.random() * 0.42,
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: 0.1 + Math.random() * 0.3,
      driftT: 0.0005 + Math.random() * 0.0015,
      driftPhase: Math.random() * Math.PI * 2,
      driftSpeed: 0.03 + Math.random() * 0.08,
      color: pickStarColor(),
      sparkle: false,
      layer: depthRoll < 0.5 ? 0 : depthRoll < 0.8 ? 1 : 2,
    });
  }

  // 每帧积分用的缓慢速度；碰到河道边界就反向，永远不跑出河宽
  for (const particle of stars) {
    const tSpeed = 0.000002 + Math.random() * 0.000005;
    const offsetSpeed = 0.00001 + Math.random() * 0.00002;
    particle.vT = (Math.random() < 0.5 ? -1 : 1) * tSpeed;
    particle.vOffset = (Math.random() < 0.5 ? -1 : 1) * offsetSpeed;
  }
}

function updateParticles(dtMs: number) {
  const dt = Math.min(dtMs, 32);
  for (const particle of stars) {
    particle.t += (particle.vT ?? 0) * dt;
    particle.offset += (particle.vOffset ?? 0) * dt;
    if (particle.t < 0.005) {
      particle.t = 0.005;
      particle.vT = Math.abs(particle.vT ?? 0);
    } else if (particle.t > 0.995) {
      particle.t = 0.995;
      particle.vT = -Math.abs(particle.vT ?? 0);
    }
    if (particle.offset < -0.78) {
      particle.offset = -0.78;
      particle.vOffset = Math.abs(particle.vOffset ?? 0);
    } else if (particle.offset > 0.78) {
      particle.offset = 0.78;
      particle.vOffset = -Math.abs(particle.vOffset ?? 0);
    }
  }
}

function resizeCanvas() {
  const el = canvas.value;
  if (!el) return;
  vw = Math.max(1, window.innerWidth);
  vh = Math.max(1, window.innerHeight);
  dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  el.width = Math.round(vw * dpr);
  el.height = Math.round(vh * dpr);
  el.style.width = `${vw}px`;
  el.style.height = `${vh}px`;
  ctx = el.getContext('2d', { alpha: true, desynchronized: true });
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function rebuild() {
  resizeCanvas();
  docH = Math.max(document.documentElement.scrollHeight, window.innerHeight * 2);
  targetScroll = window.scrollY;
  if (reduced) parallaxScroll = targetScroll;
  buildScene();
  draw(performance.now());
}

function drawRingedPlanet(
  c: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  tone: 'blue' | 'lavender',
) {
  c.save();
  c.translate(x, y);
  c.rotate(-0.18);

  const halo = c.createRadialGradient(0, 0, r * 0.7, 0, 0, r * 2.2);
  halo.addColorStop(0, tone === 'blue' ? 'rgba(120, 190, 255, 0.18)' : 'rgba(190, 170, 255, 0.18)');
  halo.addColorStop(1, 'rgba(120, 190, 255, 0)');
  c.fillStyle = halo;
  c.beginPath();
  c.arc(0, 0, r * 2.2, 0, Math.PI * 2);
  c.fill();

  c.save();
  c.scale(1, 0.3);
  c.strokeStyle = 'rgba(236, 205, 137, 0.72)';
  c.lineWidth = Math.max(0.8, r * 0.07);
  c.beginPath();
  c.arc(0, 0, r * 1.75, 0, Math.PI * 2);
  c.stroke();
  c.restore();

  const sphere = c.createRadialGradient(-r * 0.36, -r * 0.4, r * 0.08, 0, 0, r);
  if (tone === 'blue') {
    sphere.addColorStop(0, 'rgba(238, 251, 255, 0.98)');
    sphere.addColorStop(0.36, 'rgba(99, 164, 218, 0.95)');
    sphere.addColorStop(0.72, 'rgba(36, 78, 132, 0.95)');
    sphere.addColorStop(1, 'rgba(8, 26, 58, 0.98)');
  } else {
    sphere.addColorStop(0, 'rgba(248, 243, 255, 0.98)');
    sphere.addColorStop(0.38, 'rgba(160, 139, 224, 0.94)');
    sphere.addColorStop(0.74, 'rgba(78, 58, 142, 0.94)');
    sphere.addColorStop(1, 'rgba(22, 14, 52, 0.98)');
  }
  c.fillStyle = sphere;
  c.beginPath();
  c.arc(0, 0, r, 0, Math.PI * 2);
  c.fill();

  c.save();
  c.clip();
  c.globalAlpha = 0.18;
  c.fillStyle = 'rgb(245, 250, 255)';
  for (let i = 0; i < 3; i += 1) {
    c.beginPath();
    c.ellipse(0, -r * 0.4 + i * r * 0.34, r * 1.05, r * 0.07, 0, 0, Math.PI * 2);
    c.fill();
  }
  c.restore();

  c.save();
  c.scale(1, 0.3);
  c.strokeStyle = 'rgba(246, 220, 160, 0.9)';
  c.lineWidth = Math.max(0.8, r * 0.07);
  c.beginPath();
  c.arc(0, 0, r * 1.75, 0, Math.PI);
  c.stroke();
  c.restore();
  c.restore();
}

function drawStar(
  c: CanvasRenderingContext2D,
  particle: StarParticle,
  advance: number,
  time: number,
  layerInfo: (typeof STAR_LAYERS)[number],
  layer: number,
) {
  const t = particle.t;
  const baseY = t * docH - advance;
  if (baseY < -32 || baseY > vh + 32) return;

  const point = riverPoint(t);
  const half = riverHalf(t);
  const x = projectX(point.x + particle.offset * half);
  const twinkle = 0.55 + 0.45 * Math.sin(time * particle.twinkleSpeed + particle.phase);
  const edge = Math.min(1, Math.abs(particle.offset) / 0.78);
  // 外围星点沿河带边缘连续淡出，不做可见的边界截断；位置和漂移逻辑不变。
  const edgeFade = Math.pow(1 - edge, 1.2);
  const alpha = particle.brightness * layerInfo.alpha * twinkle * edgeFade;
  const size = particle.size * layerInfo.scale;

  // 近景星体多层柔光；远处只保留细小核心
  if (layer === 2 && size > 0.7) {
    const halo = haloSprite(particle.color);
    const haloSize = Math.max(8, size * 5.8);
    c.globalAlpha = Math.min(0.78, alpha * 0.34);
    c.drawImage(halo, x - haloSize / 2, baseY - haloSize / 2, haloSize, haloSize);
  }

  if (size > 1.3) {
    const sprite = starSprite(particle.color, particle.sparkle);
    const drawSize = size * (particle.sparkle ? 10.5 : 8);
    c.globalAlpha = Math.min(1, alpha * 1.12);
    c.drawImage(sprite, x - drawSize / 2, baseY - drawSize / 2, drawSize, drawSize);
    return;
  }

  c.globalAlpha = alpha;
  c.fillStyle = `rgb(${particle.color})`;
  const dot = Math.max(1, size * 1.3);
  c.fillRect(x - dot / 2, baseY - dot / 2, dot, dot);
}

function draw(now: number) {
  if (!ctx) return;
  const time = now / 1000;
  safeInset = vw * RIVER_SAFE_X;
  innerWidth = vw - safeInset * 2;
  ctx.clearRect(0, 0, vw, vh);
  // 星云之外是纯白页面背景，不铺满星空
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, vw, vh);

  for (let layer = 0; layer < 3; layer += 1) {
    const nebulaInfo = NEBULA_LAYERS[layer];
    const starInfo = STAR_LAYERS[layer];
    const advanceNebula = parallaxScroll * nebulaInfo.factor;
    const advanceStars = parallaxScroll * starInfo.factor;

    // 连续 S 形星云带：把横截面精灵沿页面纵向逐段叠起来
    const band = bandSprite(layer === 0 ? 'outer' : 'core');
    const bandAlpha = layer === 0 ? 0.15 : layer === 1 ? 0.28 : 0.24;
    const widthFactor = layer === 0 ? 1.2 : layer === 1 ? 1.12 : 1.04;

    // 外缘做两层很淡的晕开：一层贴近河带，一层更宽地渗进白色背景。
    const haze = bandSprite('outer');
    for (let pageY = advanceNebula - 80; pageY <= advanceNebula + vh + 80; pageY += 10) {
      const t = clamp01(pageY / docH);
      const point = riverPoint(t);
      const half = riverHalf(t);
      const screenY = pageY - advanceNebula;
      const wide = half * 2 * widthFactor * 1.9 * innerWidth;
      ctx.globalAlpha = 0.014;
      ctx.drawImage(haze, projectX(point.x) - wide / 2, screenY - 32, wide, 64);
      const near = half * 2 * widthFactor * 1.45 * innerWidth;
      ctx.globalAlpha = 0.03;
      ctx.drawImage(haze, projectX(point.x) - near / 2, screenY - 32, near, 64);
    }

    for (let pageY = advanceNebula - 72; pageY <= advanceNebula + vh + 72; pageY += 8) {
      const t = clamp01(pageY / docH);
      const point = riverPoint(t);
      const half = riverHalf(t);
      const morph = Math.sin(time * 0.22 + t * 7.8 + layer * 1.7);
      const x = projectX(point.x + Math.sin(time * 0.09 + t * 4.2) * 0.005);
      const width = half * 2 * widthFactor * (1 + morph * 0.05) * innerWidth;
      const screenY = pageY - advanceNebula;
      ctx.globalAlpha = bandAlpha * (0.94 + 0.06 * morph);
      ctx.drawImage(band, x - width / 2, screenY - 32, width, 64);
    }

    // 河心的一层淡青亮光：中心比两侧更亮，但仍保留深色可读底
    if (layer === 2) {
      const glowBand = bandSprite('glow');
      for (let pageY = advanceNebula - 72; pageY <= advanceNebula + vh + 72; pageY += 8) {
        const t = clamp01(pageY / docH);
        const point = riverPoint(t);
        const half = riverHalf(t);
        const morph = Math.sin(time * 0.3 + t * 9);
        const x = projectX(point.x + Math.sin(time * 0.09 + t * 4.2) * 0.005);
        const width = half * 2 * 0.58 * (1 + morph * 0.06) * innerWidth;
        ctx.globalAlpha = 0.065 * (0.92 + 0.08 * morph);
        ctx.drawImage(glowBand, x - width / 2, pageY - advanceNebula - 32, width, 64);
      }
    }

    // 上下端加宽的星云池：像参考图一样让顶端/底端自然展开
    if (layer === 2) {
      const pool = puffSprite(0);
      for (const [t, size, alpha] of [
        [0.08, 0.48, 0.44],
        [0.13, 0.6, 0.55],
        [0.18, 0.46, 0.4],
        [0.88, 0.42, 0.34],
        [0.94, 0.5, 0.4],
      ] as const) {
        const y = t * docH - advanceNebula;
        const poolSize = size * innerWidth;
        if (y + poolSize < 0 || y - poolSize > vh) continue;
        ctx.globalAlpha = alpha;
        ctx.drawImage(pool, projectX(0.53) - poolSize / 2, y - poolSize / 2, poolSize, poolSize);
      }
    }

    // S 带内的少量装饰星球（部分带环）；四颗大星仍是可点击的 DOM 节点
    if (layer === 2) {
      const planetA = riverPoint(0.24);
      const halfA = riverHalf(0.24);
      const yA = 0.24 * docH - advanceNebula;
      if (yA > -80 && yA < vh + 80) {
        drawRingedPlanet(ctx, projectX(planetA.x - halfA * 0.28), yA, Math.max(10, innerWidth * 0.022), 'blue');
      }
      const planetB = riverPoint(0.46);
      const halfB = riverHalf(0.46);
      const yB = 0.46 * docH - advanceNebula;
      if (yB > -80 && yB < vh + 80) {
        drawRingedPlanet(ctx, projectX(planetB.x + halfB * 0.3), yB, Math.max(8, innerWidth * 0.017), 'lavender');
      }
    }

    // 边缘碎雾，让轮廓缓慢形变
    for (const puff of puffs) {
      if (puff.layer !== layer) continue;
      const t = clamp01(puff.t + Math.sin(time * puff.speed + puff.phase) * 0.0022);
      const baseY = t * docH - advanceNebula;
      if (baseY + puff.size < 0 || baseY - puff.size > vh) continue;
      const point = riverPoint(t);
      const half = riverHalf(t);
      const morph = Math.sin(time * puff.speed * 0.8 + puff.phase * 1.3);
      const x = projectX(point.x + (puff.offset + morph * 0.06) * half);
      const size = puff.size * (innerWidth / vw) * (1 + morph * 0.08);
      ctx.globalAlpha =
        puff.opacity * nebulaInfo.alpha * (0.9 + 0.1 * Math.sin(time * puff.speed + puff.phase));
      ctx.drawImage(puffSprite(puff.tone), x - size / 2, baseY - size / 2, size, size);
    }

    for (const particle of stars) {
      if (particle.layer !== layer) continue;
      drawStar(ctx, particle, advanceStars, time, starInfo, layer);
    }
  }

  // 左右白色淡出带：无论河道怎么扭转，都不与网页边框相贴，留白与开头一致
  const sideFade = Math.max(30, vw * 0.055);
  const leftFade = ctx.createLinearGradient(0, 0, sideFade, 0);
  leftFade.addColorStop(0, '#ffffff');
  leftFade.addColorStop(1, 'rgba(255, 255, 255, 0)');
  ctx.fillStyle = leftFade;
  ctx.fillRect(0, 0, sideFade, vh);
  const rightFade = ctx.createLinearGradient(vw - sideFade, 0, vw, 0);
  rightFade.addColorStop(0, 'rgba(255, 255, 255, 0)');
  rightFade.addColorStop(1, '#ffffff');
  ctx.fillStyle = rightFade;
  ctx.fillRect(vw - sideFade, 0, sideFade, vh);

  ctx.globalAlpha = 1;
}

function loop(now: number) {
  const elapsed = lastFrame ? Math.min(now - lastFrame, 100) : FRAME_INTERVAL;
  lastFrame = now;
  if (!reduced) updateParticles(elapsed);
  frameBudget += elapsed;
  if (frameBudget >= FRAME_INTERVAL) {
    if (!reduced) parallaxScroll += (targetScroll - parallaxScroll) * 0.09;
    else parallaxScroll = targetScroll;
    draw(now);
    frameBudget %= FRAME_INTERVAL;
  }
  raf = requestAnimationFrame(loop);
}

function start() {
  if (raf || reduced) return;
  raf = requestAnimationFrame(loop);
}

function stop() {
  cancelAnimationFrame(raf);
  raf = 0;
}

function onScroll() {
  targetScroll = window.scrollY;
  if (reduced) {
    parallaxScroll = targetScroll;
    draw(performance.now());
  }
}

function onVisibility() {
  if (document.hidden) stop();
  else start();
}

function scheduleRebuild() {
  window.clearTimeout(rebuildTimer);
  rebuildTimer = window.setTimeout(rebuild, 220);
}

onMounted(() => {
  reduced =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  targetScroll = window.scrollY;
  parallaxScroll = targetScroll;
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(scheduleRebuild);
    observer.observe(document.body);
  } else {
    window.addEventListener('resize', scheduleRebuild);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  document.addEventListener('visibilitychange', onVisibility);
  raf = requestAnimationFrame(() => {
    raf = 0;
    rebuild();
    if (!reduced) start();
    else draw(performance.now());
  });
});

onBeforeUnmount(() => {
  stop();
  observer?.disconnect();
  observer = null;
  window.removeEventListener('resize', scheduleRebuild);
  window.removeEventListener('scroll', onScroll);
  document.removeEventListener('visibilitychange', onVisibility);
  window.clearTimeout(rebuildTimer);
});
</script>

<template>
  <canvas ref="canvas" class="star-river-canvas" aria-hidden="true"></canvas>
</template>

<style scoped>
.star-river-canvas {
  position: fixed;
  inset: 0;
  z-index: -1;
  display: block;
  width: 100vw;
  height: 100vh;
  background: transparent;
  pointer-events: none;
}
</style>

/**
 * 首页流体星云河道的共享几何。
 *
 * 中心线用 Catmull-Rom 经过一组上下回旋的航点，得到连续、自然卷曲的
 * 流体河道；宽度按航点附近的呼吸曲线变化，两端略展开。
 * Canvas 与 DOM 大星体共用这套坐标，保证粒子、行星和交互星都在河道内。
 */

/** 星云左右安全边距（占视口宽度比例）。 */
export const RIVER_SAFE_X = 0.07;

const WAYPOINT_T = [0, 0.2, 0.4, 0.62, 0.82, 1];
const WAYPOINT_X = [0.42, 0.64, 0.41, 0.61, 0.42, 0.55];

export function riverPoint(t: number): { x: number; y: number } {
  const u = Math.min(1, Math.max(0, t));
  let index = 0;
  while (index < WAYPOINT_T.length - 2 && u > WAYPOINT_T[index + 1]) index += 1;
  const t0 = WAYPOINT_T[index];
  const t1 = WAYPOINT_T[index + 1];
  const local = t1 === t0 ? 0 : (u - t0) / (t1 - t0);
  const p0 = WAYPOINT_X[Math.max(0, index - 1)];
  const p1 = WAYPOINT_X[index];
  const p2 = WAYPOINT_X[index + 1];
  const p3 = WAYPOINT_X[Math.min(WAYPOINT_X.length - 1, index + 2)];
  const s = local;
  const x =
    0.5 *
    (2 * p1 +
      (-p0 + p2) * s +
      (2 * p0 - 5 * p1 + 4 * p2 - p3) * s * s +
      (-p0 + 3 * p1 - 3 * p2 + p3) * s * s * s);
  return { x, y: u };
}

/** 河道半宽：连续膨胀/收窄，两端略微展开。 */
export function riverHalf(t: number): number {
  const u = Math.min(1, Math.max(0, t));
  // 中下段沿用标注段（标题所在开头）的宽度和留白比例，
  // 只保留很轻的沿程呼吸，不再叠中段鼓包或高频波纹。
  const base =
    0.325 +
    0.006 * Math.sin(u * 5.0 + 1.3) +
    0.004 * Math.sin(u * 10.7 + 0.4);
  const top = Math.pow(Math.max(0, (0.3 - u) / 0.3), 1.3) * 0.075;
  const bottom = Math.pow(Math.max(0, (u - 0.8) / 0.2), 1.3) * 0.05;
  return base + top + bottom;
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

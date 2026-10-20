// levels/helpers.js — three-free (TF). Level-data builders (spec §5.1, exact semantics).
import { TUNING } from 'a3d/core/tuning.js';

/** Axis-aligned box, solid from min.y to max.y, walkable top unless `walkable:false`. */
export const box = (min, max, style = 'grass', extra = {}) => ({ type: 'box', min, max, style, ...extra });

/** Vertical cylinder centred on (cx, cz), solid between y0 and y1, walkable top. */
export const cyl = (cx, cz, r, y0, y1, style = 'concrete', extra = {}) => ({ type: 'cyl', c: [cx, cz], r, y0, y1, style, ...extra });

/**
 * Axis-aligned ramp. Footprint min.xz..max.xz. Surface height = min.y at the low side and max.y at the side
 * named by `up` ('+x' | '-x' | '+z' | '-z'). The solid wedge spans from (min.y - thickness) to the surface.
 */
export const ramp = (min, max, up, style = 'laterite', extra = {}) => ({ type: 'ramp', min, max, up, thickness: 0.4, style, ...extra });

/** n >= 2 points from a to b inclusive: p_i = a + (b - a) * i / (n - 1). */
export function line(a, b, n) {
  const count = Math.max(2, Math.floor(n));
  const out = new Array(count);
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1);
    out[i] = [
      a[0] + (b[0] - a[0]) * t,
      a[1] + (b[1] - a[1]) * t,
      a[2] + (b[2] - a[2]) * t,
    ];
  }
  return out;
}

/**
 * Exact jump-pad trajectory parameters (same formula as Player.launch, spec §5.1 / §7.2 step 14).
 * g = TUNING.pad.gravity; apexY = max(a.y, b.y) + apexAbove; vy0 = sqrt(2g(apexY - a.y));
 * T = vy0/g + sqrt(2(apexY - b.y)/g).
 * @returns {{g:number, apexY:number, vy0:number, T:number}}
 */
export function padTrajectory(a, b, apexAbove) {
  const g = TUNING.pad.gravity;
  const above = Number.isFinite(apexAbove) ? apexAbove : TUNING.pad.defaultApexAbove;
  const apexY = Math.max(a[1], b[1]) + above;
  const vy0 = Math.sqrt(2 * g * Math.max(0, apexY - a[1]));
  const T = vy0 / g + Math.sqrt(2 * Math.max(0, apexY - b[1]) / g);
  return { g, apexY, vy0, T };
}

/**
 * n points on the exact jump-pad trajectory at t_i = T*(i+1)/(n+1); x/z linear in t;
 * y = a.y + vy0*t - g*t*t/2, then +0.55 (player centre, i.e. where a goutte must sit to be collected).
 */
export function padArc(a, b, apexAbove, n) {
  const { g, vy0, T } = padTrajectory(a, b, apexAbove);
  const count = Math.max(1, Math.floor(n));
  const out = new Array(count);
  for (let i = 0; i < count; i++) {
    const t = (T * (i + 1)) / (count + 1);
    const u = T > 0 ? t / T : 0;
    out[i] = [
      a[0] + (b[0] - a[0]) * u,
      a[1] + vy0 * t - (g * t * t) / 2 + 0.55,
      a[2] + (b[2] - a[2]) * u,
    ];
  }
  return out;
}

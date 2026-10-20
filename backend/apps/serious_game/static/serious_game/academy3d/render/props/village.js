// render/props/village.js — decor kinds (spec §12.5): ravinala, baobab, tree, bush, rock, flowers, fence (points),
// path (points, width), pipe (points, radius), rice_patch (pos, size), cart, crate, barrel, sign (text).
// Foliage kinds (grass, flowers, bush, tree, ravinala) are returned as instances of shared prototypes so the
// static world can instance them (wind sway on medium/high) or merge them (low tier).
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';
import {
  boxGeom, cylGeom, icoGeom, sphereGeom, latheGeom, discGeom, cylBetween, prepStatic, tf, mergeStatic, paintVertices,
  paintTriangles, jitterPositions, flatNormals, bakeAO, hash3, makeRng,
} from 'a3d/render/geometry.js';

/** Kinds instanced (and swaying) on medium/high; merged on low. */
export const FOLIAGE_KINDS = Object.freeze(['grass', 'flowers', 'bush', 'tree', 'ravinala']);
export const DECOR_KINDS = Object.freeze(['ravinala', 'baobab', 'tree', 'bush', 'rock', 'flowers', 'fence', 'path', 'pipe',
  'rice_patch', 'cart', 'crate', 'barrel', 'sign']);
/** Kinds whose shadow is worth casting when instanced. */
export const FOLIAGE_CASTS_SHADOW = Object.freeze({ grass: false, flowers: false, bush: true, tree: true, ravinala: true });

const FLOWER_COLORS = [0xff7eb6, 0xffd84d, 0xffffff, 0xff9f43, 0xb98bff, 0xff5d73];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function gradientY(g, bottomHex, topHex, y0, y1) {
  const a = new THREE.Color().setHex(bottomHex), b = new THREE.Color().setHex(topHex);
  const span = Math.max(1e-3, y1 - y0);
  return paintVertices(g, (o, x, y) => { o.copy(a).lerp(b, clamp((y - y0) / span, 0, 1)); });
}

// ---------------------------------------------------------------------------------------------
// Foliage prototypes (local space, base at y = 0, facing +Z)
// ---------------------------------------------------------------------------------------------

function blade(x, z, height, ang, tilt, baseHex, tipHex, radius = 0.035) {
  const g = prepStatic(new THREE.ConeGeometry(radius, height, 3, 1, true));
  g.translate(0, height / 2, 0);
  gradientY(g, baseHex, tipHex, 0, height);
  return tf(g, x, 0, z, ang, 1, 1, 1, tilt, 0);
}

function protoGrass(variant, lowDetail) {
  const rng = makeRng(`grass-${variant}`);
  const parts = [];
  const n = (lowDetail ? 4 : 6) + (variant % 2);
  const tips = [PALETTE.GRASS_LIGHT, 0xb8e070, PALETTE.GRASS];
  for (let i = 0; i < n; i++) {
    const ang = (i / n) * Math.PI * 2 + rng.range(-0.4, 0.4);
    const r = rng.range(0.0, 0.07);
    parts.push(blade(Math.sin(ang) * r, Math.cos(ang) * r, rng.range(0.12, 0.26), ang, rng.range(0.25, 0.6),
      PALETTE.GRASS_DARK, tips[variant % tips.length], 0.026));
  }
  return mergeStatic(parts);
}

function protoFlowers(variant, lowDetail) {
  const rng = makeRng(`flowers-${variant}`);
  const parts = [];
  const color = FLOWER_COLORS[variant % FLOWER_COLORS.length];
  const n = lowDetail ? 3 : 5;
  for (let i = 0; i < n; i++) {
    const ang = (i / n) * Math.PI * 2 + rng.range(-0.5, 0.5);
    const r = rng.range(0.03, 0.14);
    const h = rng.range(0.22, 0.38);
    const x = Math.sin(ang) * r, z = Math.cos(ang) * r;
    parts.push(cylGeom(0.012, 0.016, h, 3, x, 0, z, PALETTE.LEAF_DARK, true));
    const head = icoGeom(rng.range(0.05, 0.075), 0, x, h + 0.02, z, color);
    flatNormals(head);
    parts.push(head);
    parts.push(icoGeom(0.025, 0, x, h + 0.05, z, PALETTE.HYDRIA_YELLOW));
  }
  for (let i = 0; i < 3; i++) {
    const ang = rng.range(0, Math.PI * 2);
    parts.push(blade(0, 0, rng.range(0.15, 0.22), ang, 0.7, PALETTE.LEAF_DARK, PALETTE.LEAF, 0.05));
  }
  return mergeStatic(parts);
}

function protoBush(variant, lowDetail) {
  const rng = makeRng(`bush-${variant}`);
  const parts = [];
  const detail = lowDetail ? 0 : 1;
  const puffs = [[0, 0.32, 0, 0.38], [0.3, 0.24, 0.1, 0.28], [-0.28, 0.22, -0.05, 0.27], [0.05, 0.25, -0.28, 0.25]];
  const greens = [[PALETTE.LEAF_DARK, PALETTE.LEAF], [0x3f8a34, PALETTE.LEAF_LIGHT], [PALETTE.LEAF_DARK, 0x6aa84a]];
  const [lo, hi] = greens[variant % greens.length];
  for (const [x, y, z, r] of puffs) {
    const g = icoGeom(r * rng.range(0.9, 1.1), detail, x, y, z, hi);
    parts.push(g);
  }
  const m = mergeStatic(parts);
  jitterPositions(m, 0.04, null, 5 + variant);
  flatNormals(m);
  gradientY(m, lo, hi, 0, 0.6);
  if (variant % 3 === 2) {
    // small red berries / flowers
    const extra = [];
    for (let i = 0; i < 6; i++) {
      const a = rng.range(0, Math.PI * 2), y = rng.range(0.25, 0.55);
      extra.push(icoGeom(0.04, 0, Math.sin(a) * 0.36, y, Math.cos(a) * 0.32, 0xe5383b));
    }
    return mergeStatic([m, ...extra]);
  }
  return m;
}

function protoTree(variant, lowDetail) {
  const rng = makeRng(`tree-${variant}`);
  const parts = [];
  const detail = lowDetail ? 0 : 1;
  const trunkH = variant === 1 ? 2.2 : 1.6;
  const trunk = cylGeom(0.11, 0.17, trunkH, lowDetail ? 5 : 7, 0, 0, 0, PALETTE.TRUNK);
  gradientY(trunk, PALETTE.TRUNK_DARK, PALETTE.TRUNK, 0, trunkH);
  parts.push(trunk);
  // two branches
  parts.push(cylBetween(0, trunkH * 0.7, 0, 0.45, trunkH + 0.35, 0.1, 0.06, 5, PALETTE.TRUNK, 0.04));
  parts.push(cylBetween(0, trunkH * 0.75, 0, -0.4, trunkH + 0.3, -0.15, 0.06, 5, PALETTE.TRUNK, 0.04));
  const blobs = variant === 1
    ? [[0, trunkH + 0.5, 0, 0.75], [0.15, trunkH + 1.25, 0.05, 0.6], [-0.1, trunkH + 1.85, -0.05, 0.42]]
    : [[0, trunkH + 0.75, 0, 1.0], [0.62, trunkH + 0.45, 0.2, 0.7], [-0.6, trunkH + 0.5, -0.12, 0.72], [0.05, trunkH + 1.25, -0.35, 0.62]];
  const canopy = [];
  for (const [x, y, z, r] of blobs) canopy.push(icoGeom(r * rng.range(0.92, 1.08), detail, x, y, z, PALETTE.LEAF));
  const c = mergeStatic(canopy);
  jitterPositions(c, 0.06, null, 9 + variant);
  flatNormals(c);
  const top = trunkH + 2.0;
  gradientY(c, PALETTE.LEAF_DARK, variant === 1 ? 0x7cbf45 : PALETTE.LEAF_LIGHT, trunkH, top);
  // a few mangoes on the default tree
  if (variant !== 1) {
    for (let i = 0; i < 5; i++) {
      const a = rng.range(0, Math.PI * 2);
      parts.push(icoGeom(0.07, 0, Math.sin(a) * 0.85, trunkH + rng.range(0.2, 0.7), Math.cos(a) * 0.85, 0xf2b233));
    }
  }
  parts.push(c);
  return mergeStatic(parts);
}

function protoRavinala(variant, lowDetail) {
  const rng = makeRng(`ravinala-${variant}`);
  const parts = [];
  const trunkH = variant === 1 ? 1.4 : 2.4;
  const trunk = cylGeom(0.13, 0.18, trunkH, lowDetail ? 6 : 8, 0, 0, 0, 0x9a8a6a, false, lowDetail ? 1 : 4);
  const ringA = new THREE.Color().setHex(0x9a8a6a), ringB = new THREE.Color().setHex(0x7d6e52);
  paintVertices(trunk, (o, x, y) => { o.copy(Math.floor(y / 0.3) % 2 ? ringA : ringB); });
  parts.push(trunk);
  // fan of leaves in the local XY plane (the fan faces ±Z)
  const n = lowDetail ? 9 : 13;
  const crown = trunkH + 0.15;
  parts.push(sphereGeom(0.2, 6, 4, 0, crown, 0, 0x6f8f3a, 1, 1.2, 0.6));
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const phi = THREE.MathUtils.degToRad(-72 + 144 * t) + rng.range(-0.05, 0.05);
    const stalkLen = rng.range(0.7, 1.0) * (1 - Math.abs(t - 0.5) * 0.5);
    const sx = Math.sin(phi) * stalkLen, sy = crown + Math.cos(phi) * stalkLen;
    const z = rng.range(-0.04, 0.04);
    parts.push(cylBetween(0, crown, 0, sx, sy, z, 0.035, 4, 0x7d9a45, 0.025));
    const bladeLen = rng.range(0.95, 1.25);
    const leaf = sphereGeom(1, lowDetail ? 5 : 7, lowDetail ? 3 : 5, 0, 0, 0, PALETTE.LEAF, 0.2, bladeLen / 2, 0.035);
    leaf.translate(0, bladeLen / 2, 0);
    gradientY(leaf, PALETTE.LEAF_DARK, PALETTE.LEAF_LIGHT, 0, bladeLen);
    tf(leaf, sx, sy, z, 0, 1, 1, 1, rng.range(-0.08, 0.08), -phi);
    parts.push(leaf);
  }
  return mergeStatic(parts);
}

const PROTO_BUILDERS = { grass: protoGrass, flowers: protoFlowers, bush: protoBush, tree: protoTree, ravinala: protoRavinala };
const PROTO_VARIANTS = { grass: 3, flowers: 6, bush: 3, tree: 2, ravinala: 2 };
const _protos = new Map();

/** Shared local prototype geometry for a foliage kind (do not dispose; see disposePrototypes()). */
export function getFoliagePrototype(kind, variant = 0, lowDetail = false) {
  const nv = PROTO_VARIANTS[kind] || 1;
  const v = ((variant | 0) % nv + nv) % nv;
  const key = `${kind}:${v}:${lowDetail ? 'l' : 'h'}`;
  let g = _protos.get(key);
  if (!g) {
    const build = PROTO_BUILDERS[kind];
    if (!build) return null;
    g = build(v, lowDetail);
    g.computeBoundingSphere();
    _protos.set(key, g);
  }
  return g;
}

export function protoKey(kind, variant, lowDetail) {
  const nv = PROTO_VARIANTS[kind] || 1;
  return `${kind}:${((variant | 0) % nv + nv) % nv}:${lowDetail ? 'l' : 'h'}`;
}

export function variantCount(kind) {
  return PROTO_VARIANTS[kind] || 1;
}

export function disposePrototypes() {
  for (const g of _protos.values()) g.dispose();
  _protos.clear();
}

// ---------------------------------------------------------------------------------------------
// Merged decor (built in local space, then placed)
// ---------------------------------------------------------------------------------------------

function decorBaobab(variant, lowDetail, rng) {
  const parts = [];
  const H = variant === 1 ? 4.2 : 5.0;
  const profile = [[0.95, 0], [1.08, 0.35], [1.12, H * 0.25], [1.0, H * 0.5], [0.8, H * 0.72], [0.58, H * 0.9], [0.5, H]];
  const trunk = latheGeom(profile, lowDetail ? 8 : 12, PALETTE.BAOBAB_BARK);
  const a = new THREE.Color().setHex(PALETTE.BAOBAB_BARK), b = new THREE.Color().setHex(PALETTE.BAOBAB_BARK_DARK);
  paintVertices(trunk, (o, x, y, z) => {
    const ang = Math.atan2(z, x);
    o.copy(a).lerp(b, 0.25 + 0.35 * (0.5 + 0.5 * Math.sin(ang * 5 + y * 0.6)) * (1 - y / H * 0.5));
  });
  bakeAO(trunk, 0, 0.3, 0.72);
  parts.push(trunk);
  const nb = lowDetail ? 5 : 7;
  for (let i = 0; i < nb; i++) {
    const ang = (i / nb) * Math.PI * 2 + rng.range(-0.3, 0.3);
    const len = rng.range(1.1, 1.8);
    const el = rng.range(0.55, 1.0);
    const sx = Math.sin(ang) * 0.3, sz = Math.cos(ang) * 0.3;
    const ex = Math.sin(ang) * (0.3 + Math.cos(el) * len), ey = H - 0.1 + Math.sin(el) * len, ez = Math.cos(ang) * (0.3 + Math.cos(el) * len);
    parts.push(cylBetween(sx, H - 0.2, sz, ex, ey, ez, 0.16, lowDetail ? 4 : 6, PALETTE.BAOBAB_BARK_DARK, 0.07));
    // twigs + leaf tuft
    parts.push(cylBetween(ex, ey, ez, ex + Math.sin(ang + 0.6) * 0.4, ey + 0.35, ez + Math.cos(ang + 0.6) * 0.4, 0.06, 4, PALETTE.BAOBAB_BARK_DARK, 0.03));
    const tuft = icoGeom(rng.range(0.35, 0.5), 0, ex, ey + 0.15, ez, PALETTE.LEAF, 1, 0.65, 1);
    flatNormals(tuft);
    gradientY(tuft, PALETTE.LEAF_DARK, PALETTE.LEAF_LIGHT, ey - 0.2, ey + 0.5);
    parts.push(tuft);
  }
  return mergeStatic(parts);
}

function decorRock(variant, lowDetail) {
  const shapes = [[1, 0.7, 0.9], [1.2, 0.55, 0.8], [0.8, 0.9, 0.85]];
  const [sx, sy, sz] = shapes[variant % shapes.length];
  const g = prepStatic(new THREE.DodecahedronGeometry(0.6, 0));
  jitterPositions(g, 0.09, null, 31 + variant);
  tf(g, 0, 0.6 * sy * 0.75, 0, variant * 0.7, sx, sy, sz);
  flatNormals(g);
  const t = new THREE.Color().setHex(PALETTE.ROCK_LIGHT), s = new THREE.Color().setHex(PALETTE.ROCK), d = new THREE.Color().setHex(PALETTE.ROCK_DARK);
  const moss = new THREE.Color().setHex(PALETTE.GRASS_DARK);
  paintTriangles(g, (o, f) => {
    if (f.ny > 0.65) o.copy(t).lerp(moss, hash3(f.cx, f.cy, f.cz, 4) < 0.3 ? 0.4 : 0.05);
    else o.copy(s).lerp(d, hash3(f.cx, f.cy, f.cz, 8) * 0.6 + (f.ny < 0 ? 0.25 : 0));
  });
  return g;
}

function decorCrate() {
  const parts = [];
  const s = 0.6;
  const body = boxGeom(s, s, s, 0, s / 2, 0, PALETTE.WOOD, [1, 3, 1]);
  const a = new THREE.Color().setHex(PALETTE.WOOD), b = new THREE.Color().setHex(PALETTE.WOOD_LIGHT);
  paintTriangles(body, (o, f) => { o.copy(Math.floor(f.cy / (s / 3)) % 2 ? a : b); if (f.ny > 0.5) o.copy(b); });
  bakeAO(body, 0);
  parts.push(body);
  const e = 0.07;
  for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    parts.push(boxGeom(e, s + 0.02, e, x * (s / 2 - e / 2 + 0.01), s / 2, z * (s / 2 - e / 2 + 0.01), PALETTE.WOOD_DARK));
  }
  parts.push(boxGeom(s * 0.9, 0.05, 0.02, 0, s * 0.5, s / 2 + 0.01, PALETTE.WOOD_DARK, null));
  return mergeStatic(parts);
}

function decorBarrel(variant) {
  const parts = [];
  if (variant % 3 === 2) {
    // yellow jerrycan (bidon jaune)
    const can = boxGeom(0.3, 0.42, 0.18, 0, 0.21, 0, PALETTE.JERRYCAN_YELLOW);
    bakeAO(can, 0, 0.1, 0.8);
    parts.push(can);
    parts.push(boxGeom(0.18, 0.05, 0.05, 0.02, 0.46, 0, PALETTE.JERRYCAN_YELLOW));
    parts.push(cylGeom(0.035, 0.035, 0.06, 6, -0.1, 0.42, 0, 0x2b6cd6));
    return mergeStatic(parts);
  }
  const body = variant % 3 === 1 ? 0x9b4a2c : PALETTE.HYDRIA_BLUE;
  const ring = variant % 3 === 1 ? 0x6e3420 : PALETTE.HYDRIA_BLUE_DARK;
  const g = cylGeom(0.3, 0.3, 0.88, 12, 0, 0, 0, body, false, 3);
  bakeAO(g, 0, 0.2, 0.75);
  parts.push(g);
  for (const y of [0.18, 0.7]) parts.push(cylGeom(0.315, 0.315, 0.05, 12, 0, y, 0, ring));
  parts.push(cylGeom(0.25, 0.25, 0.02, 12, 0, 0.88, 0, ring));
  return mergeStatic(parts);
}

function decorCart() {
  const parts = [];
  // bed
  const bed = boxGeom(1.2, 0.1, 1.9, 0, 0.75, 0, PALETTE.WOOD, [1, 1, 6]);
  const a = new THREE.Color().setHex(PALETTE.WOOD), b = new THREE.Color().setHex(PALETTE.WOOD_LIGHT);
  paintTriangles(bed, (o, f) => { o.copy(Math.floor(f.cz / 0.32 + 10) % 2 ? a : b); });
  parts.push(bed);
  // side rails + stakes
  for (const x of [-0.6, 0.6]) {
    parts.push(boxGeom(0.06, 0.06, 1.9, x, 1.15, 0, PALETTE.WOOD_DARK));
    for (const z of [-0.85, -0.3, 0.3, 0.85]) parts.push(boxGeom(0.06, 0.4, 0.06, x, 0.95, z, PALETTE.WOOD_DARK));
  }
  // wheels
  for (const x of [-0.72, 0.72]) {
    const w = prepStatic(new THREE.CylinderGeometry(0.55, 0.55, 0.08, 14, 1, false), PALETTE.WOOD_DARK);
    w.rotateZ(Math.PI / 2);
    w.translate(x, 0.55, 0.1);
    parts.push(w);
    const hub = prepStatic(new THREE.CylinderGeometry(0.12, 0.12, 0.16, 8), PALETTE.TRUNK_DARK);
    hub.rotateZ(Math.PI / 2);
    hub.translate(x, 0.55, 0.1);
    parts.push(hub);
    for (let i = 0; i < 4; i++) {
      const ang = (i / 4) * Math.PI;
      const sp = boxGeom(0.05, 0.96, 0.05, 0, 0, 0, PALETTE.WOOD);
      tf(sp, x * 1.04, 0.55, 0.1, 0, 1, 1, 1, ang, 0);
      parts.push(sp);
    }
  }
  // shafts (timon) down to the ground
  parts.push(cylBetween(-0.2, 0.75, 0.95, -0.12, 0.05, 2.4, 0.05, 5, PALETTE.WOOD_DARK));
  parts.push(cylBetween(0.2, 0.75, 0.95, 0.12, 0.05, 2.4, 0.05, 5, PALETTE.WOOD_DARK));
  return mergeStatic(parts);
}

function decorSign(entity, ctx) {
  const parts = [];
  const text = String(entity.text || '').slice(0, 22);
  const w = clamp(0.5 + text.length * 0.12, 0.9, 2.6), h = 0.45;
  const postH = 1.35;
  parts.push(boxGeom(0.09, postH, 0.09, -w * 0.35, postH / 2, -0.02, PALETTE.WOOD_DARK));
  parts.push(boxGeom(0.09, postH, 0.09, w * 0.35, postH / 2, -0.02, PALETTE.WOOD_DARK));
  parts.push(boxGeom(w + 0.1, h + 0.1, 0.06, 0, postH - 0.05, 0.03, PALETTE.WOOD_DARK));
  return { geom: mergeStatic(parts), sign: text ? { lx: 0, ly: postH - 0.05, lz: 0.065, w, h, text } : null };
}

/** Ribbon along a polyline (paths). */
function ribbon(points, width, yOffset, hexCenter, hexEdge, rngSalt) {
  const v = [];
  const col = [];
  const cc = new THREE.Color().setHex(hexCenter), ce = new THREE.Color().setHex(hexEdge);
  // resample every ~0.8 m
  const pts = [];
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    const len = Math.hypot(b[0] - a[0], b[2] - a[2]);
    const n = Math.max(1, Math.ceil(len / 0.8));
    for (let k = 0; k < n; k++) {
      const t = k / n;
      pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]);
    }
  }
  pts.push(points[points.length - 1]);
  if (pts.length < 2) return null;
  const half = width / 2;
  const L = [], R = [], CL = [], CR = [];
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let dx = b[0] - a[0], dz = b[2] - a[2];
    const l = Math.hypot(dx, dz) || 1;
    dx /= l; dz /= l;
    const nx = -dz, nz = dx;
    const j1 = 1 + (hash3(p[0], p[2], 1, rngSalt) - 0.5) * 0.35;
    const j2 = 1 + (hash3(p[0], p[2], 2, rngSalt) - 0.5) * 0.35;
    const y = p[1] + yOffset;
    L.push([p[0] + nx * half * j1, y, p[2] + nz * half * j1]);
    R.push([p[0] - nx * half * j2, y, p[2] - nz * half * j2]);
    CL.push([p[0] + nx * half * 0.45, y + 0.004, p[2] + nz * half * 0.45]);
    CR.push([p[0] - nx * half * 0.45, y + 0.004, p[2] - nz * half * 0.45]);
  }
  const push = (p, c) => { v.push(p[0], p[1], p[2]); col.push(c.r, c.g, c.b); };
  const tri = (a, ca, b, cb, c, ccol) => { push(a, ca); push(b, cb); push(c, ccol); };
  for (let i = 0; i < pts.length - 1; i++) {
    // strips: L - CL - CR - R (CCW seen from above depends on direction; we emit both windings safely by orientation test)
    const strips = [[L, CL, ce, cc], [CL, CR, cc, cc], [CR, R, cc, ce]];
    for (const [A, B, ca, cb] of strips) {
      const a0 = A[i], a1 = A[i + 1], b0 = B[i], b1 = B[i + 1];
      // orientation: ensure +Y normal
      const ux = a1[0] - a0[0], uz = a1[2] - a0[2], vx = b0[0] - a0[0], vz = b0[2] - a0[2];
      const ny = uz * vx - ux * vz;
      if (ny >= 0) { tri(a0, ca, a1, ca, b1, cb); tri(a0, ca, b1, cb, b0, cb); }
      else { tri(a0, ca, b1, cb, a1, ca); tri(a0, ca, b0, cb, b1, cb); }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(v), 3));
  g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(col), 3));
  g.computeVertexNormals();
  return prepStatic(g);
}

function decorFence(points, scale) {
  const parts = [];
  const postH = 0.95 * scale;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    const len = Math.hypot(b[0] - a[0], b[2] - a[2]);
    const n = Math.max(1, Math.ceil(len / 1.25));
    for (let k = 0; k <= n; k++) {
      if (k === n && i < points.length - 2) continue;
      const t = k / n;
      const x = a[0] + (b[0] - a[0]) * t, y = a[1] + (b[1] - a[1]) * t, z = a[2] + (b[2] - a[2]) * t;
      const post = cylGeom(0.05, 0.06, postH, 5, x, y, z, PALETTE.WOOD_DARK);
      parts.push(post);
      parts.push(icoGeom(0.06, 0, x, y + postH, z, PALETTE.WOOD_DARK));
    }
    for (const hr of [0.35, 0.72]) {
      const r = cylBetween(a[0], a[1] + hr * postH, a[2], b[0], b[1] + hr * postH, b[2], 0.03, 4, PALETTE.WOOD, 0.03);
      if (r) parts.push(r);
    }
  }
  return mergeStatic(parts);
}

function decorPipe(points, radius) {
  const parts = [];
  const r = radius || 0.15;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    const g = cylBetween(a[0], a[1], a[2], b[0], b[1], b[2], r, 10, PALETTE.PIPE, r);
    if (!g) continue;
    paintVertices(g, (o, x, y, z, nx, ny) => { o.setHex(ny > 0.5 ? PALETTE.PIPE_LIGHT : (ny < -0.5 ? PALETTE.PIPE_DARK : PALETTE.PIPE)); });
    parts.push(g);
    // flanges near both ends of each segment
    const len = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    if (len > 0.6) {
      for (const t of [0.15 / len, 1 - 0.15 / len]) {
        const p0 = [a[0] + (b[0] - a[0]) * (t - 0.03 / len), a[1] + (b[1] - a[1]) * (t - 0.03 / len), a[2] + (b[2] - a[2]) * (t - 0.03 / len)];
        const p1 = [a[0] + (b[0] - a[0]) * (t + 0.03 / len), a[1] + (b[1] - a[1]) * (t + 0.03 / len), a[2] + (b[2] - a[2]) * (t + 0.03 / len)];
        const f = cylBetween(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], r * 1.35, 10, PALETTE.PIPE_DARK, r * 1.35);
        if (f) parts.push(f);
      }
    }
  }
  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i];
    parts.push(sphereGeom(r * 1.12, 10, 6, p[0], p[1], p[2], PALETTE.PIPE));
  }
  return mergeStatic(parts);
}

function decorRicePatch(entity, rng, lowDetail) {
  const parts = [];
  const size = entity.size;
  const sx = Array.isArray(size) ? size[0] : (Number.isFinite(size) ? size : 4);
  const sz = Array.isArray(size) ? (size[1] ?? size[0]) : (Number.isFinite(size) ? size : 3);
  const dyke = 0.28, dh = 0.16;
  // flooded paddy surface
  const water = boxGeom(sx - dyke, 0.04, sz - dyke, 0, 0.03, 0, PALETTE.RICE_WATER);
  parts.push(water);
  // mud dykes
  const dk = PALETTE.LATERITE;
  parts.push(boxGeom(sx, dh, dyke, 0, dh / 2, -sz / 2 + dyke / 2, dk));
  parts.push(boxGeom(sx, dh, dyke, 0, dh / 2, sz / 2 - dyke / 2, dk));
  parts.push(boxGeom(dyke, dh, sz - dyke * 2, -sx / 2 + dyke / 2, dh / 2, 0, dk));
  parts.push(boxGeom(dyke, dh, sz - dyke * 2, sx / 2 - dyke / 2, dh / 2, 0, dk));
  for (const g of parts.slice(1)) {
    const a = new THREE.Color().setHex(PALETTE.LATERITE_LIGHT), b = new THREE.Color().setHex(PALETTE.LATERITE);
    paintTriangles(g, (o, f) => { o.copy(f.ny > 0.5 ? a : b); });
  }
  // rows of rice shoots
  const step = lowDetail ? 0.55 : 0.36;
  const nx = Math.max(1, Math.floor((sx - dyke * 2) / step)), nz = Math.max(1, Math.floor((sz - dyke * 2) / step));
  const shoot = [];
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < nz; j++) {
      const x = -sx / 2 + dyke + (i + 0.5) * ((sx - dyke * 2) / nx) + rng.range(-0.04, 0.04);
      const z = -sz / 2 + dyke + (j + 0.5) * ((sz - dyke * 2) / nz) + rng.range(-0.04, 0.04);
      const h = rng.range(0.22, 0.34);
      for (let k = 0; k < 3; k++) {
        const ang = k * 2.1 + rng.range(-0.3, 0.3);
        shoot.push(blade(x, z, h, ang, 0.28, 0x5f9a2c, PALETTE.RICE_SHOOT, 0.022));
      }
    }
  }
  const s = mergeStatic(shoot);
  if (s) { s.translate(0, 0.04, 0); parts.push(s); }
  return mergeStatic(parts);
}

// ---------------------------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------------------------

const _mat = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _e = new THREE.Euler();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();

/** Instance matrix for a decor placement. */
export function placementMatrix(pos, yawRad, scale, out = new THREE.Matrix4()) {
  _e.set(0, yawRad, 0, 'YXZ');
  _q.setFromEuler(_e);
  return out.compose(_p.set(pos[0], pos[1], pos[2]), _q, _s.set(scale, scale, scale));
}

/**
 * Builds one decor entity. ctx = {rng, lowDetail, signs:[]}.
 * @returns {{geoms: THREE.BufferGeometry[], instances: Array<{kind:string, variant:number, matrix:THREE.Matrix4}>}}
 */
export function buildDecor(entity, ctx) {
  const out = { geoms: [], instances: [] };
  if (!entity || !entity.kind) return out;
  const rng = ctx.rng || makeRng(1);
  const lowDetail = !!ctx.lowDetail;
  const pos = entity.pos || [0, 0, 0];
  const scale = Number.isFinite(entity.scale) ? entity.scale : 1;
  const hasYaw = Number.isFinite(entity.yaw);
  const yaw = hasYaw ? THREE.MathUtils.degToRad(entity.yaw) : rng() * Math.PI * 2;
  const variant = Number.isFinite(entity.variant) ? entity.variant | 0 : Math.floor(rng() * 6);
  const place = (g) => { if (g) out.geoms.push(tf(g, pos[0], pos[1], pos[2], yaw, scale)); };

  switch (entity.kind) {
    case 'grass':
    case 'flowers':
    case 'bush':
    case 'tree':
    case 'ravinala': {
      // Ravinala fans face the camera-ish default when no yaw is given: keep authored yaw, else random.
      const jitter = entity.kind === 'tree' || entity.kind === 'ravinala' ? rng.range(0.92, 1.08) : rng.range(0.85, 1.15);
      out.instances.push({ kind: entity.kind, variant, matrix: placementMatrix(pos, yaw, scale * jitter) });
      break;
    }
    case 'baobab': place(decorBaobab(variant % 2, lowDetail, rng)); break;
    case 'rock': place(decorRock(variant, lowDetail)); break;
    case 'crate': place(decorCrate()); break;
    case 'barrel': place(decorBarrel(Number.isFinite(entity.variant) ? entity.variant : variant)); break;
    case 'cart': place(decorCart()); break;
    case 'sign': {
      const s = decorSign(entity, ctx);
      place(s.geom);
      if (s.sign && ctx.signs) {
        const c = Math.cos(yaw), sn = Math.sin(yaw);
        // local (lx, ly, lz) rotated by yaw then scaled
        const wx = pos[0] + (s.sign.lx * c + s.sign.lz * sn) * scale;
        const wz = pos[2] + (-s.sign.lx * sn + s.sign.lz * c) * scale;
        ctx.signs.push({ x: wx, y: pos[1] + s.sign.ly * scale, z: wz, yaw, w: s.sign.w * scale, h: s.sign.h * scale,
          text: s.sign.text, bg: PALETTE.WOOD_LIGHT, fg: 0x3a2414 });
      }
      break;
    }
    case 'fence': {
      const pts = entity.points;
      if (Array.isArray(pts) && pts.length >= 2) out.geoms.push(decorFence(pts, scale));
      break;
    }
    case 'path': {
      const pts = entity.points;
      if (Array.isArray(pts) && pts.length >= 2) {
        const g = ribbon(pts, entity.width || 1.6, 0.02, PALETTE.EARTH_PATH, PALETTE.EARTH_PATH_DARK, 5);
        if (g) out.geoms.push(g);
      }
      break;
    }
    case 'pipe': {
      const pts = entity.points;
      if (Array.isArray(pts) && pts.length >= 2) {
        const g = decorPipe(pts, entity.radius || 0.15);
        if (g) out.geoms.push(g);
      }
      break;
    }
    case 'rice_patch': place(decorRicePatch(entity, rng, lowDetail)); break;
    default:
      console.warn('[a3d] décor inconnu', entity.kind);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// Auto-scatter pieces (merged): small stones and grass patches
// ---------------------------------------------------------------------------------------------

/** Small faceted stone, world-placed. */
export function scatterStone(x, y, z, rng) {
  const r = rng.range(0.08, 0.2);
  const g = icoGeom(r, 0, 0, r * 0.45, 0, PALETTE.ROCK, 1, rng.range(0.5, 0.8), 1);
  jitterPositions(g, r * 0.25, null, Math.floor(rng() * 1000));
  flatNormals(g);
  const a = new THREE.Color().setHex(PALETTE.ROCK_LIGHT), b = new THREE.Color().setHex(PALETTE.ROCK_DARK);
  paintTriangles(g, (o, f) => { o.copy(f.ny > 0.4 ? a : b); });
  return tf(g, x, y, z, rng() * Math.PI * 2);
}

/** Irregular flat grass patch (lighter / darker green), world-placed slightly above the top. */
export function scatterPatch(x, y, z, rng, light = true) {
  const r = rng.range(0.6, 1.5);
  const seg = 9;
  const g = discGeom(r, seg, 0, 0, 0, light ? PALETTE.GRASS_LIGHT : 0x6aa83f);
  const p = g.attributes.position.array;
  for (let i = 0; i < p.length; i += 3) {
    const d = Math.hypot(p[i], p[i + 2]);
    if (d > 1e-4) {
      const k = 0.75 + 0.5 * hash3(Math.round(p[i] * 50), Math.round(p[i + 2] * 50), 3, Math.floor(x * 7 + z * 13));
      p[i] *= k; p[i + 2] *= k;
    }
  }
  const lightC = new THREE.Color().setHex(light ? PALETTE.GRASS_LIGHT : 0x6aa83f), base = new THREE.Color().setHex(PALETTE.GRASS);
  paintVertices(g, (o, vx, vy, vz) => { o.copy(lightC).lerp(base, Math.min(1, Math.hypot(vx, vz) / r) * 0.8); });
  return tf(g, x, y + 0.012, z, rng() * Math.PI * 2, 1, 1, rng.range(0.6, 1.0));
}

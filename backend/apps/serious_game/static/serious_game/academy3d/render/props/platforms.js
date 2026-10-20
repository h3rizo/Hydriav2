// render/props/platforms.js — visual geometry for static boxes / cylinders / ramps per style (spec §12.5), including
// the house_tin and kiosque buildings, plus the sign-text batch. Everything returned is prepped, world-space
// geometry ready to be merged into a static chunk (or a local geometry for movers / blocks).
//
// Optional extras read on box entities (besides the spec's walkable/solid/sign/cameraIgnore/id):
//   front: '+x'|'-x'|'+z'|'-z'  facade carrying the door / counter / sign (default: the face toward the level centre)
//   roof:  'tin'|'tin_rust'|'thatch'   house_tin roof finish (default 'tin'; 'thatch' keeps the flat walkable top)
import * as THREE from 'three';
import { PALETTE, STYLE_COLORS, toCss } from 'a3d/render/palette.js';
import {
  boxGeom, boxMinMax, roundedBox, cylGeom, wedgeGeom, soupGeom, paintTriangles, paintVertices, jitterPositions,
  bakeAO, shadeColors, tf, mergeStatic, hash3, flatNormals,
} from 'a3d/render/geometry.js';

export const BOX_STYLES = Object.freeze(['grass', 'laterite', 'rock', 'concrete', 'wood', 'brick', 'metal', 'pipe', 'house_tin', 'kiosque', 'invisible']);

const _ca = new THREE.Color();
const _cb = new THREE.Color();
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function colorsFor(style) {
  return STYLE_COLORS[style] || STYLE_COLORS.concrete;
}

// ---------------------------------------------------------------------------------------------
// Facade frames
// ---------------------------------------------------------------------------------------------

/**
 * Frame of one vertical face of a box. yaw = facing direction (sin yaw, 0, cos yaw); along = facade "right".
 * place(u, v, out) → world point at facade coordinate u (along), height v (absolute y), pushed `out` metres outward.
 */
export function faceFrame(min, max, front) {
  const cx = (min[0] + max[0]) / 2, cz = (min[2] + max[2]) / 2;
  let nx = 0, nz = 1, fx = cx, fz = max[2], width = max[0] - min[0], depth = max[2] - min[2], yaw = 0;
  switch (front) {
    case '-z': nx = 0; nz = -1; fz = min[2]; yaw = Math.PI; break;
    case '+x': nx = 1; nz = 0; fx = max[0]; fz = cz; width = max[2] - min[2]; depth = max[0] - min[0]; yaw = Math.PI / 2; break;
    case '-x': nx = -1; nz = 0; fx = min[0]; fz = cz; width = max[2] - min[2]; depth = max[0] - min[0]; yaw = -Math.PI / 2; break;
    default: break;
  }
  const ax = Math.cos(yaw), az = -Math.sin(yaw);
  return {
    nx, nz, yaw, width, depth, ax, az, x: fx, z: fz,
    place(u, out) { return [fx + ax * u + nx * out, fz + az * u + nz * out]; },
  };
}

/** Box of size (sw along the facade, sh, sd outward) centred at facade coords (u, yCentre), `out` = centre offset. */
function faceBox(frame, u, y, sw, sh, sd, out, hex) {
  const [px, pz] = frame.place(u, out);
  return tf(boxGeom(sw, sh, sd, 0, 0, 0, hex), px, y, pz, frame.yaw);
}

/** The four facades of a box, front first. */
function allFronts(front) {
  const order = ['+z', '+x', '-z', '-x'];
  const i = Math.max(0, order.indexOf(front));
  return [order[i], order[(i + 1) % 4], order[(i + 2) % 4], order[(i + 3) % 4]];
}

/** Default front: the side facing `center` ({x, z}) or '+z'. */
export function pickFront(min, max, center) {
  if (!center) return '+z';
  const cx = (min[0] + max[0]) / 2, cz = (min[2] + max[2]) / 2;
  const dx = center.x - cx, dz = center.z - cz;
  if (Math.abs(dx) < 1e-3 && Math.abs(dz) < 1e-3) return '+z';
  if (Math.abs(dx) > Math.abs(dz)) return dx > 0 ? '+x' : '-x';
  return dz > 0 ? '+z' : '-z';
}

// ---------------------------------------------------------------------------------------------
// Painters
// ---------------------------------------------------------------------------------------------

/** Horizontal strata on wall faces between y0..y1 (bottom darker), top faces get `topHex`. */
function paintStrata(g, y0, y1, sideHex, bottomHex, topHex, rowH = 0.5, salt = 1) {
  const side = new THREE.Color().setHex(sideHex), bottom = new THREE.Color().setHex(bottomHex), top = new THREE.Color().setHex(topHex);
  const span = Math.max(0.01, y1 - y0);
  return paintTriangles(g, (out, f) => {
    if (f.ny > 0.6) { out.copy(top); return; }
    if (f.ny < -0.6) { out.copy(bottom).multiplyScalar(0.8); return; }
    const t = clamp((f.cy - y0) / span, 0, 1);
    out.copy(bottom).lerp(side, Math.pow(t, 0.7));
    const row = Math.floor((f.cy - y0) / rowH);
    const k = (row % 2 ? 0.93 : 1.0) * (1 + (hash3(row, salt, 0) - 0.5) * 0.08);
    out.multiplyScalar(k);
  });
}

/** Top faces colour A (with jitter), other faces colour B. */
function paintCap(g, topHex, sideHex, jitter = 0.05, salt = 3) {
  const a = new THREE.Color().setHex(topHex), b = new THREE.Color().setHex(sideHex);
  return paintTriangles(g, (out, f) => {
    if (f.ny > 0.6) {
      out.copy(a).multiplyScalar(1 + (hash3(Math.round(f.cx * 0.7), salt, Math.round(f.cz * 0.7)) - 0.5) * 2 * jitter);
    } else {
      out.copy(b).multiplyScalar(f.ny < -0.5 ? 0.75 : 1);
    }
  });
}

/** Alternating stripes along an axis ('x'|'z'|'y'), period `w`, two hexes, with jitter. */
function paintStripes(g, axis, w, hexA, hexB, jitter = 0.04, salt = 5, onlyFaces = null) {
  const a = new THREE.Color().setHex(hexA), b = new THREE.Color().setHex(hexB);
  return paintTriangles(g, (out, f) => {
    if (onlyFaces && !onlyFaces(f)) return false;
    const v = axis === 'x' ? f.cx : (axis === 'z' ? f.cz : f.cy);
    const idx = Math.floor(v / w + 1e-4);
    out.copy(idx % 2 ? b : a).multiplyScalar(1 + (hash3(idx, salt, 0) - 0.5) * 2 * jitter);
    if (f.ny < -0.5) out.multiplyScalar(0.72);
  });
}

// ---------------------------------------------------------------------------------------------
// Box styles
// ---------------------------------------------------------------------------------------------

function layeredBox(min, max, colors, ctx, capHex, capSideHex) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const capT = clamp(h * 0.45, 0.12, 0.3);
  const bodyTop = max[1] - capT * 0.5;
  const cx = (min[0] + max[0]) / 2, cz = (min[2] + max[2]) / 2;
  if (bodyTop > min[1] + 0.02) {
    const rows = clamp(Math.round((bodyTop - min[1]) / 0.5), 1, 10);
    const body = boxMinMax(min[0], min[1], min[2], max[0], bodyTop, max[2], colors.side, [1, rows, 1]);
    paintStrata(body, min[1], bodyTop, colors.side, colors.bottom, colors.side, 0.5, Math.round(cx * 13 + cz * 7));
    out.push(body);
  }
  const lip = 0.06;
  const cap = roundedBox(w + lip * 2, capT, d + lip * 2, Math.min(0.11, capT * 0.45), ctx.lowDetail ? 1 : 2, cx, max[1] - capT / 2, cz);
  paintCap(cap, capHex, capSideHex);
  out.push(cap);
  return out;
}

function rockBox(min, max, ctx) {
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const segs = ctx.lowDetail
    ? [clamp(Math.ceil(w / 2.2), 1, 4), clamp(Math.ceil(h / 1.6), 1, 3), clamp(Math.ceil(d / 2.2), 1, 4)]
    : [clamp(Math.ceil(w / 1.3), 1, 8), clamp(Math.ceil(h / 0.9), 1, 6), clamp(Math.ceil(d / 1.3), 1, 8)];
  const g = boxMinMax(min[0], min[1], min[2], max[0], max[1], max[2], PALETTE.ROCK, segs);
  const yTop = max[1] - 1e-3, yBot = min[1] + 1e-3;
  jitterPositions(g, Math.min(0.11, Math.min(w, d) * 0.05), (x, y) => [1, (y > yTop || y < yBot) ? 0 : 1, 1], 11);
  flatNormals(g);
  const top = new THREE.Color().setHex(PALETTE.ROCK_LIGHT), moss = new THREE.Color().setHex(PALETTE.GRASS_DARK);
  const side = new THREE.Color().setHex(PALETTE.ROCK), dark = new THREE.Color().setHex(PALETTE.ROCK_DARK);
  paintTriangles(g, (out, f) => {
    const n = hash3(f.cx, f.cy, f.cz, 17);
    if (f.ny > 0.7) { out.copy(top).lerp(moss, n < 0.25 ? 0.35 : 0.08); return; }
    out.copy(side).lerp(dark, n * 0.6 + (f.ny < -0.3 ? 0.3 : 0));
  });
  bakeAO(g, min[1]);
  return [g];
}

function concreteBox(min, max, ctx) {
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const cx = (min[0] + max[0]) / 2, cz = (min[2] + max[2]) / 2;
  const out = [];
  const body = roundedBox(w, h, d, 0.06, 1, cx, (min[1] + max[1]) / 2, cz);
  const top = new THREE.Color().setHex(PALETTE.CONCRETE_LIGHT), side = new THREE.Color().setHex(PALETTE.CONCRETE);
  paintTriangles(body, (out2, f) => {
    if (f.ny > 0.6) out2.copy(top).multiplyScalar(1 + (hash3(Math.round(f.cx), 2, Math.round(f.cz)) - 0.5) * 0.06);
    else out2.copy(side).multiplyScalar(f.ny < -0.5 ? 0.72 : 1);
  });
  out.push(body);
  if (h > 0.5) {
    const plinth = boxMinMax(min[0] - 0.015, min[1], min[2] - 0.015, max[0] + 0.015, min[1] + Math.min(0.18, h * 0.2), max[2] + 0.015, PALETTE.CONCRETE_DARK);
    bakeAO(plinth, min[1], 0.18, 0.75);
    out.push(plinth);
  }
  if (h > 2.2 && !ctx.lowDetail) {
    // formwork seams
    for (let y = min[1] + 1.2; y < max[1] - 0.6; y += 1.2) {
      out.push(boxMinMax(min[0] - 0.01, y - 0.02, min[2] - 0.01, max[0] + 0.01, y + 0.02, max[2] + 0.01, PALETTE.CONCRETE_DARK));
    }
  }
  return out;
}

function woodBox(min, max, ctx) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const longX = w >= d;
  const plankT = Math.min(0.1, h * 0.3);
  const inset = Math.min(0.06, Math.min(w, d) * 0.1);
  const bodyTop = max[1] - plankT;
  if (bodyTop > min[1] + 0.02) {
    const segsX = clamp(Math.ceil(w / 0.24), 1, 40), segsZ = clamp(Math.ceil(d / 0.24), 1, 40);
    const body = boxMinMax(min[0] + inset, min[1], min[2] + inset, max[0] - inset, bodyTop, max[2] - inset, PALETTE.WOOD_DARK,
      ctx.lowDetail ? null : [segsX, 1, segsZ]);
    const a = new THREE.Color().setHex(PALETTE.WOOD), b = new THREE.Color().setHex(PALETTE.WOOD_DARK);
    paintTriangles(body, (out2, f) => {
      const v = Math.abs(f.nx) > 0.5 ? f.cz : f.cx;
      const idx = Math.floor(v / 0.24 + 1e-4);
      out2.copy(idx % 2 ? b : a).multiplyScalar(0.92 + hash3(idx, 3, 1) * 0.1);
      if (Math.abs(f.ny) > 0.5) out2.multiplyScalar(0.7);
    });
    bakeAO(body, min[1], 0.3, 0.72);
    out.push(body);
    // corner posts
    const ps = 0.12;
    for (const [px, pz] of [[min[0], min[2]], [max[0] - ps, min[2]], [min[0], max[2] - ps], [max[0] - ps, max[2] - ps]]) {
      out.push(boxMinMax(px, min[1], pz, px + ps, bodyTop, pz + ps, PALETTE.WOOD_DARK));
    }
    if (h > 1.2) {
      // horizontal bands on tall wooden stacks
      for (const yb of [min[1] + 0.25, bodyTop - 0.18]) {
        out.push(boxMinMax(min[0] + inset - 0.02, yb - 0.06, min[2] + inset - 0.02, max[0] - inset + 0.02, yb + 0.06, max[2] - inset + 0.02, PALETTE.TRUNK_DARK));
      }
    }
  }
  // top planks across the short axis, running along the long axis
  const shortLen = longX ? d : w;
  const n = clamp(Math.ceil(shortLen / 0.28), 1, 60);
  const pw = shortLen / n;
  for (let i = 0; i < n; i++) {
    const hex = i % 2 ? PALETTE.WOOD_LIGHT : PALETTE.WOOD;
    const jitterLen = (hash3(i, min[0], min[2]) - 0.5) * 0.08;
    const g = longX
      ? boxMinMax(min[0] - 0.04 + jitterLen, bodyTop, min[2] + i * pw + 0.012, max[0] + 0.04 + jitterLen, max[1], min[2] + (i + 1) * pw - 0.012, hex)
      : boxMinMax(min[0] + i * pw + 0.012, bodyTop, min[2] - 0.04 + jitterLen, min[0] + (i + 1) * pw - 0.012, max[1], max[2] + 0.04 + jitterLen, hex);
    shadeColors(g, (x, y, z, nx, ny) => (ny < -0.5 ? 0.7 : 0.94 + hash3(i, 9, 9) * 0.1));
    out.push(g);
  }
  return out;
}

function brickBox(min, max, ctx) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const capT = Math.min(0.08, h * 0.2);
  const top = max[1] - capT;
  const rows = clamp(Math.round((top - min[1]) / 0.2), 1, ctx.lowDetail ? 8 : 24);
  const sx = clamp(Math.round(w / 0.45), 1, ctx.lowDetail ? 6 : 20), sz = clamp(Math.round(d / 0.45), 1, ctx.lowDetail ? 6 : 20);
  const g = boxMinMax(min[0], min[1], min[2], max[0], top, max[2], PALETTE.BRICK, [sx, rows, sz]);
  const a = new THREE.Color().setHex(PALETTE.BRICK), b = new THREE.Color().setHex(PALETTE.BRICK_DARK), c = new THREE.Color().setHex(PALETTE.BRICK_LIGHT);
  const rowH = (top - min[1]) / rows;
  paintTriangles(g, (o, f) => {
    const row = Math.floor((f.cy - min[1]) / rowH + 1e-4);
    const col = Math.floor((Math.abs(f.nx) > 0.5 ? f.cz : f.cx) / 0.45 + (row % 2) * 0.5);
    const n = hash3(row, col, f.nx * 3 + f.nz * 5, 21);
    o.copy(n < 0.33 ? b : (n < 0.66 ? a : c));
    if (row % 2) o.multiplyScalar(0.95);
  });
  bakeAO(g, min[1]);
  out.push(g);
  const cap = boxMinMax(min[0] - 0.03, top, min[2] - 0.03, max[0] + 0.03, max[1], max[2] + 0.03, PALETTE.CONCRETE);
  paintCap(cap, PALETTE.CONCRETE_LIGHT, PALETTE.CONCRETE, 0.03);
  out.push(cap);
  return out;
}

function metalBox(min, max, ctx) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const deckT = Math.min(0.22, h);
  const deckBottom = max[1] - deckT;
  // deck plate with chequer stripes
  const deck = boxMinMax(min[0], deckBottom, min[2], max[0], max[1], max[2], PALETTE.METAL,
    ctx.lowDetail ? null : [clamp(Math.ceil(w / 0.5), 1, 24), 1, clamp(Math.ceil(d / 0.5), 1, 24)]);
  const m1 = new THREE.Color().setHex(PALETTE.METAL), m2 = new THREE.Color().setHex(PALETTE.METAL_DARK);
  paintTriangles(deck, (o, f) => {
    if (f.ny > 0.6) {
      const k = (Math.floor(f.cx / 0.5) + Math.floor(f.cz / 0.5)) % 2;
      o.copy(m1).multiplyScalar(k ? 1.0 : 0.9);
    } else o.copy(m2);
  });
  out.push(deck);
  // hazard trim around the deck edge (flush with the top)
  const trimH = Math.min(0.08, deckT * 0.5);
  const seg = 0.45;
  const edges = [
    [min[0], min[2], max[0], min[2]], [min[0], max[2], max[0], max[2]],
    [min[0], min[2], min[0], max[2]], [max[0], min[2], max[0], max[2]],
  ];
  for (const [ax, az, bx, bz] of edges) {
    const len = Math.hypot(bx - ax, bz - az);
    const n = Math.max(1, Math.round(len / seg));
    for (let i = 0; i < n; i++) {
      const t0 = i / n, t1 = (i + 1) / n;
      const x0 = ax + (bx - ax) * t0, x1 = ax + (bx - ax) * t1, z0 = az + (bz - az) * t0, z1 = az + (bz - az) * t1;
      const hex = i % 2 ? PALETTE.HAZARD_DARK : PALETTE.HAZARD_YELLOW;
      const t = 0.03;
      out.push(boxMinMax(Math.min(x0, x1) - t, max[1] - trimH - 0.04, Math.min(z0, z1) - t, Math.max(x0, x1) + t, max[1] - 0.005, Math.max(z0, z1) + t, hex));
    }
  }
  if (deckBottom > min[1] + 0.1) {
    const ps = 0.1;
    const xs = [min[0] + 0.02, max[0] - ps - 0.02];
    const zs = [min[2] + 0.02, max[2] - ps - 0.02];
    if (w > 3) for (let x = min[0] + 2; x < max[0] - 1; x += 2) xs.push(x);
    if (d > 3) for (let z = min[2] + 2; z < max[2] - 1; z += 2) zs.push(z);
    for (const px of xs) for (const pz of [zs[0], zs[1]]) out.push(boxMinMax(px, min[1], pz, px + ps, deckBottom, pz + ps, PALETTE.METAL_DARK));
    for (const pz of zs) for (const px of [xs[0], xs[1]]) out.push(boxMinMax(px, min[1], pz, px + ps, deckBottom, pz + ps, PALETTE.METAL_DARK));
    // inset panels so the solid collider reads as a solid tower
    const pin = 0.06;
    const panel = boxMinMax(min[0] + pin, min[1], min[2] + pin, max[0] - pin, deckBottom, max[2] - pin, PALETTE.METAL_DARK,
      ctx.lowDetail ? null : [clamp(Math.ceil(w / 0.3), 1, 30), 1, clamp(Math.ceil(d / 0.3), 1, 30)]);
    paintStripes(panel, 'x', 0.3, PALETTE.METAL_DARK, 0x4c5660, 0.03, 7, (f) => Math.abs(f.nz) > 0.5);
    paintStripes(panel, 'z', 0.3, PALETTE.METAL_DARK, 0x4c5660, 0.03, 8, (f) => Math.abs(f.nx) > 0.5);
    bakeAO(panel, min[1]);
    out.push(panel);
    // horizontal rails
    const hMid = (min[1] + deckBottom) / 2;
    const r = 0.04;
    out.push(boxMinMax(min[0], hMid - r, min[2], max[0], hMid + r, min[2] + 0.06, PALETTE.HAZARD_YELLOW));
    out.push(boxMinMax(min[0], hMid - r, max[2] - 0.06, max[0], hMid + r, max[2], PALETTE.HAZARD_YELLOW));
    out.push(boxMinMax(min[0], hMid - r, min[2], min[0] + 0.06, hMid + r, max[2], PALETTE.HAZARD_YELLOW));
    out.push(boxMinMax(max[0] - 0.06, hMid - r, min[2], max[0], hMid + r, max[2], PALETTE.HAZARD_YELLOW));
  }
  return out;
}

function pipeBox(min, max, ctx) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const longX = w >= d;
  const cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, cz = (min[2] + max[2]) / 2;
  const radius = Math.min(h, longX ? d : w) * 0.45;
  const body = roundedBox(w, h, d, radius, ctx.lowDetail ? 2 : 3, cx, cy, cz);
  const top = new THREE.Color().setHex(PALETTE.PIPE_LIGHT), side = new THREE.Color().setHex(PALETTE.PIPE), bottom = new THREE.Color().setHex(PALETTE.PIPE_DARK);
  paintVertices(body, (o, x, y, z, nx, ny) => { o.copy(ny > 0.75 ? top : (ny < -0.3 ? bottom : side)); });
  out.push(body);
  // flanges every 2.5 m along the long axis, flush with the walkable top
  const len = longX ? w : d;
  const n = Math.floor(len / 2.5);
  for (let i = 1; i <= n; i++) {
    const t = (i / (n + 1)) * len;
    const fw = longX ? 0.14 : w + 0.08, fd = longX ? d + 0.08 : 0.14;
    const fx = longX ? min[0] + t : cx, fz = longX ? cz : min[2] + t;
    const fl = roundedBox(fw, h + 0.04, fd, Math.min(radius, 0.12), 1, fx, cy - 0.02, fz, PALETTE.PIPE_DARK);
    out.push(fl);
  }
  return out;
}

function windowGeoms(frame, u, y, shutterHex) {
  const g = [];
  g.push(faceBox(frame, u, y, 0.74, 0.74, 0.06, 0.03, PALETTE.WINDOW_FRAME));
  g.push(faceBox(frame, u, y, 0.56, 0.56, 0.06, 0.045, PALETTE.WINDOW));
  g.push(faceBox(frame, u, y + 0.03, 0.56, 0.05, 0.05, 0.07, PALETTE.WINDOW_FRAME));
  g.push(faceBox(frame, u - 0.53, y, 0.3, 0.7, 0.05, 0.035, shutterHex));
  g.push(faceBox(frame, u + 0.53, y, 0.3, 0.7, 0.05, 0.035, shutterHex));
  return g;
}

const SHUTTERS = [0x2fb5a3, 0x4f7cac, 0x6cbf5a, 0xd94f3d, 0xf0a63a];

function houseTin(min, max, ctx, entity) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const roofKind = entity.roof || 'tin';
  const roofT = roofKind === 'thatch' ? 0.28 : 0.2;
  const wallTop = max[1] - roofT;
  const front = entity.front || pickFront(min, max, ctx.center);
  // walls (split at 0.3 m for baked AO)
  const band = Math.min(0.3, (wallTop - min[1]) * 0.3);
  const rows = clamp(Math.round((wallTop - min[1]) / 0.25), 2, ctx.lowDetail ? 6 : 14);
  const lower = boxMinMax(min[0], min[1], min[2], max[0], min[1] + band, max[2], PALETTE.BRICK_DARK);
  bakeAO(lower, min[1], band + 0.01, 0.72);
  out.push(lower);
  const upper = boxMinMax(min[0], min[1] + band, min[2], max[0], wallTop, max[2], PALETTE.BRICK, [1, rows, 1]);
  const ba = new THREE.Color().setHex(PALETTE.BRICK), bb = new THREE.Color().setHex(PALETTE.BRICK_LIGHT);
  const rowH = (wallTop - min[1] - band) / rows;
  paintTriangles(upper, (o, f) => {
    const r = Math.floor((f.cy - min[1] - band) / rowH + 1e-4);
    o.copy(r % 2 ? ba : bb).multiplyScalar(0.96 + hash3(r, w, d, 4) * 0.06);
  });
  out.push(upper);

  const rng = ctx.rng || Math.random;
  const shutter = SHUTTERS[Math.floor(rng() * SHUTTERS.length) % SHUTTERS.length];
  const fronts = allFronts(front);
  const winY = min[1] + Math.max(1.1, (wallTop - min[1]) * 0.55);
  const wallH = wallTop - min[1];
  fronts.forEach((fr, fi) => {
    const f = faceFrame(min, max, fr);
    const half = f.width / 2;
    if (fi === 0) {
      // door
      const doorH = Math.min(1.85, wallH - 0.35);
      const doorU = f.width > 3.6 ? -half * 0.35 : 0;
      if (doorH > 1.0) {
        out.push(faceBox(f, doorU, min[1] + doorH / 2 + 0.02, 1.06, doorH + 0.12, 0.06, 0.03, PALETTE.WINDOW_FRAME));
        out.push(faceBox(f, doorU, min[1] + doorH / 2, 0.86, doorH, 0.06, 0.05, PALETTE.DOOR));
        out.push(faceBox(f, doorU + 0.28, min[1] + doorH * 0.5, 0.06, 0.06, 0.06, 0.09, PALETTE.HYDRIA_YELLOW));
        // step
        out.push(faceBox(f, doorU, min[1] + 0.06, 1.3, 0.12, 0.35, 0.17, PALETTE.CONCRETE));
      }
      if (entity.sign && doorH > 1.0) {
        const signY = Math.min(wallTop - 0.28, min[1] + doorH + 0.38);
        addSignBoard(out, ctx, f, doorU, signY, entity.sign, PALETTE.WOOD_DARK, PALETTE.WOOD_LIGHT, 0x3a2414);
      }
      if (wallH > 1.8) {
        for (const u of [-half + 0.9, half - 0.9]) {
          if (Math.abs(u - doorU) > 1.35 && f.width > 2.6) out.push(...windowGeoms(f, u, winY, shutter));
        }
      }
    } else if (wallH > 1.8 && f.width >= 1.6) {
      const count = Math.max(1, Math.floor(f.width / 2.4));
      for (let i = 0; i < count; i++) {
        const u = -half + (i + 0.5) * (f.width / count);
        out.push(...windowGeoms(f, u, winY, shutter));
      }
    }
  });

  // roof
  const cx = (min[0] + max[0]) / 2, cz = (min[2] + max[2]) / 2;
  if (roofKind === 'thatch') {
    const slab = boxMinMax(min[0] - 0.05, wallTop, min[2] - 0.05, max[0] + 0.05, max[1], max[2] + 0.05, PALETTE.THATCH,
      ctx.lowDetail ? null : [clamp(Math.ceil(w / 0.3), 1, 30), 1, 1]);
    paintStripes(slab, 'x', 0.3, PALETTE.THATCH, PALETTE.THATCH_LIGHT, 0.05, 31);
    out.push(slab);
    out.push(thatchFringe(min, max, max[1] - 0.06, 0.55, 0.5));
  } else {
    const ov = 0.08;
    const ribAxis = w >= d ? 'z' : 'x';
    const len = ribAxis === 'x' ? w + ov * 2 : d + ov * 2;
    const ribs = clamp(Math.round(len / 0.18), 2, ctx.lowDetail ? 16 : 60);
    const slab = boxMinMax(min[0] - ov, wallTop, min[2] - ov, max[0] + ov, max[1], max[2] + ov, PALETTE.TIN,
      ribAxis === 'x' ? [ribs, 1, 1] : [1, 1, ribs]);
    const rust = roofKind === 'tin_rust';
    const t1 = new THREE.Color().setHex(rust ? PALETTE.TIN_RUST : PALETTE.TIN_LIGHT);
    const t2 = new THREE.Color().setHex(rust ? 0x8f4e2f : PALETTE.TIN_DARK);
    const t3 = new THREE.Color().setHex(PALETTE.TIN);
    paintTriangles(slab, (o, f) => {
      const v = ribAxis === 'x' ? f.cx : f.cz;
      const idx = Math.floor(v / 0.18 + 1e-4);
      o.copy(idx % 2 ? t2 : (rust && hash3(idx, 1, 1) < 0.3 ? t3 : t1));
      if (f.ny < -0.5) o.multiplyScalar(0.72);         // under the eaves
    });
    out.push(slab);
    // ridge trim
    out.push(ribAxis === 'x'
      ? boxMinMax(min[0] - ov, max[1] - 0.02, cz - 0.08, max[0] + ov, max[1] + 0.01, cz + 0.08, PALETTE.TIN_DARK)
      : boxMinMax(cx - 0.08, max[1] - 0.02, min[2] - ov, cx + 0.08, max[1] + 0.01, max[2] + ov, PALETTE.TIN_DARK));
  }
  return out;
}

/** Sloped thatch fringe below the flat roof: from the roof edge (yTop) down `drop`, outward `spread`. */
function thatchFringe(min, max, yTop, drop, spread) {
  const x0 = min[0] - 0.05, x1 = max[0] + 0.05, z0 = min[2] - 0.05, z1 = max[2] + 0.05;
  const X0 = x0 - spread, X1 = x1 + spread, Z0 = z0 - spread, Z1 = z1 + spread;
  const yb = yTop - drop;
  const v = [];
  const quad = (a, b, c, d) => { v.push(...a, ...b, ...c, ...a, ...c, ...d); };
  // outer faces (CCW from outside), then the underside
  quad([x0, yTop, z1], [X0, yb, Z1], [X1, yb, Z1], [x1, yTop, z1]);     // +z
  quad([x1, yTop, z0], [X1, yb, Z0], [X0, yb, Z0], [x0, yTop, z0]);     // -z
  quad([x1, yTop, z1], [X1, yb, Z1], [X1, yb, Z0], [x1, yTop, z0]);     // +x
  quad([x0, yTop, z0], [X0, yb, Z0], [X0, yb, Z1], [x0, yTop, z1]);     // -x
  quad([X0, yb, Z1], [x0, yTop - 0.05, z1], [x1, yTop - 0.05, z1], [X1, yb, Z1]);
  quad([X1, yb, Z0], [x1, yTop - 0.05, z0], [x0, yTop - 0.05, z0], [X0, yb, Z0]);
  quad([X1, yb, Z1], [x1, yTop - 0.05, z1], [x1, yTop - 0.05, z0], [X1, yb, Z0]);
  quad([X0, yb, Z0], [x0, yTop - 0.05, z0], [x0, yTop - 0.05, z1], [X0, yb, Z1]);
  const g = soupGeom(v, PALETTE.THATCH);
  const a = new THREE.Color().setHex(PALETTE.THATCH), b = new THREE.Color().setHex(PALETTE.THATCH_DARK);
  paintTriangles(g, (o, f) => {
    o.copy(f.ny > 0 ? a : b).multiplyScalar(f.ny > 0 ? 1 : 0.7);
  });
  return g;
}

function kiosqueBox(min, max, ctx, entity) {
  const out = [];
  const w = max[0] - min[0], h = max[1] - min[1], d = max[2] - min[2];
  const front = entity.front || pickFront(min, max, ctx.center);
  const roofT = 0.16;
  const wallTop = max[1] - roofT;
  const band = Math.min(0.3, (wallTop - min[1]) * 0.3);
  const lower = boxMinMax(min[0], min[1], min[2], max[0], min[1] + band, max[2], PALETTE.CONCRETE_DARK);
  bakeAO(lower, min[1], band + 0.01, 0.72);
  out.push(lower);
  const walls = boxMinMax(min[0], min[1] + band, min[2], max[0], wallTop, max[2], PALETTE.WALL_PLASTER);
  out.push(walls);
  // blue Hydria band near the top
  const bandY = min[1] + (wallTop - min[1]) * 0.8;
  out.push(boxMinMax(min[0] - 0.03, bandY - 0.17, min[2] - 0.03, max[0] + 0.03, bandY + 0.17, max[2] + 0.03, PALETTE.HYDRIA_BLUE));
  // roof slab with a blue edge
  const roof = boxMinMax(min[0] - 0.12, wallTop, min[2] - 0.12, max[0] + 0.12, max[1], max[2] + 0.12, PALETTE.CONCRETE_LIGHT);
  paintCap(roof, PALETTE.CONCRETE_LIGHT, PALETTE.HYDRIA_BLUE_DARK, 0.03);
  shadeColors(roof, (x, y, z, nx, ny) => (ny < -0.5 ? 0.72 : 1));
  out.push(roof);
  // counter window on the front
  const f = faceFrame(min, max, front);
  const winW = Math.min(1.6, f.width - 0.8), winH = Math.min(0.9, (wallTop - min[1]) * 0.35);
  const winY = min[1] + Math.min(1.45, (wallTop - min[1]) * 0.5);
  if (winW > 0.5 && winH > 0.3) {
    out.push(faceBox(f, 0, winY, winW + 0.14, winH + 0.14, 0.05, 0.025, PALETTE.HYDRIA_BLUE_DARK));
    out.push(faceBox(f, 0, winY, winW, winH, 0.05, 0.04, 0x26323d));
    out.push(faceBox(f, 0, winY - winH / 2 - 0.05, winW + 0.3, 0.08, 0.34, 0.17, PALETTE.WOOD));
    // two taps under the counter
    for (const u of [-winW * 0.25, winW * 0.25]) {
      out.push(faceBox(f, u, winY - winH / 2 - 0.22, 0.06, 0.2, 0.06, 0.12, PALETTE.METAL));
      out.push(faceBox(f, u, winY - winH / 2 - 0.3, 0.06, 0.06, 0.16, 0.18, PALETTE.METAL));
    }
  }
  if (entity.sign) addSignBoard(out, ctx, f, 0, bandY, entity.sign, PALETTE.HYDRIA_BLUE, PALETTE.HYDRIA_BLUE, 0xffffff);
  return out;
}

/** Sign board geometry + a text quad request (ctx.signs). Board faces the frame normal. */
function addSignBoard(out, ctx, frame, u, y, text, boardHex, bgHex, fgHex) {
  const label = String(text).slice(0, 22);
  const w = clamp(0.5 + label.length * 0.13, 0.9, Math.max(0.9, frame.width - 0.3));
  const h = 0.4;
  out.push(faceBox(frame, u, y, w + 0.1, h + 0.1, 0.05, 0.05, boardHex));
  if (ctx.signs) {
    const [px, pz] = frame.place(u, 0.078);
    ctx.signs.push({ x: px, y, z: pz, yaw: frame.yaw, w, h, text: label, bg: bgHex, fg: fgHex });
  }
}

// ---------------------------------------------------------------------------------------------
// Cylinders and ramps
// ---------------------------------------------------------------------------------------------

function buildCyl(e, ctx) {
  const out = [];
  const cx = e.c[0], cz = e.c[1], r = e.r, y0 = e.y0, y1 = e.y1, h = y1 - y0;
  if (h <= 0 || r <= 0) return out;
  const seg = clamp(Math.round(r * (ctx.lowDetail ? 8 : 12)), ctx.lowDetail ? 8 : 12, ctx.lowDetail ? 20 : 40);
  const style = e.style || 'concrete';
  const col = colorsFor(style);
  switch (style) {
    case 'grass':
    case 'laterite': {
      const capT = clamp(h * 0.45, 0.12, 0.28);
      const bodyH = h - capT * 0.5;
      if (bodyH > 0.02) {
        const rows = clamp(Math.round(bodyH / 0.5), 1, 10);
        const body = cylGeom(r * 0.97, r * 0.9, bodyH, seg, cx, y0, cz, col.side, false, rows);
        paintStrata(body, y0, y0 + bodyH, col.side, col.bottom, col.side, 0.5, Math.round(cx * 7 + cz * 3));
        out.push(body);
      }
      const cap = cylGeom(r + 0.06, r + 0.02, capT, seg, cx, y1 - capT, cz, col.top);
      paintCap(cap, style === 'grass' ? PALETTE.GRASS : PALETTE.LATERITE_LIGHT, style === 'grass' ? PALETTE.GRASS_DARK : PALETTE.EARTH_PATH);
      out.push(cap);
      break;
    }
    case 'wood': {
      const g = cylGeom(r, r * 1.04, h, seg, cx, y0, cz, PALETTE.WOOD_DARK);
      const bark = new THREE.Color().setHex(PALETTE.TRUNK), bark2 = new THREE.Color().setHex(PALETTE.TRUNK_DARK);
      const ring = new THREE.Color().setHex(PALETTE.WOOD_LIGHT), core = new THREE.Color().setHex(PALETTE.WOOD);
      paintVertices(g, (o, x, y, z, nx, ny) => {
        if (ny > 0.6) {
          const dd = Math.hypot(x - cx, z - cz) / r;
          o.copy(ring).lerp(core, 1 - dd);
        } else {
          const a = Math.atan2(z - cz, x - cx);
          o.copy(Math.floor((a + Math.PI) / (Math.PI * 2) * seg) % 2 ? bark : bark2);
        }
      });
      bakeAO(g, y0);
      out.push(g);
      break;
    }
    case 'rock': {
      const g = cylGeom(r, r * 1.05, h, Math.max(7, Math.round(seg * 0.6)), cx, y0, cz, PALETTE.ROCK, false, clamp(Math.ceil(h / 0.8), 1, 5));
      jitterPositions(g, Math.min(0.1, r * 0.08), (x, y) => [1, (y > y1 - 1e-3 || y < y0 + 1e-3) ? 0 : 1, 1], 23);
      flatNormals(g);
      const t = new THREE.Color().setHex(PALETTE.ROCK_LIGHT), s1 = new THREE.Color().setHex(PALETTE.ROCK), s2 = new THREE.Color().setHex(PALETTE.ROCK_DARK);
      paintTriangles(g, (o, f) => { if (f.ny > 0.7) o.copy(t); else o.copy(s1).lerp(s2, hash3(f.cx, f.cy, f.cz, 3) * 0.7); });
      out.push(g);
      break;
    }
    case 'pipe':
    case 'metal': {
      const base = style === 'pipe' ? PALETTE.PIPE : PALETTE.METAL;
      const dark = style === 'pipe' ? PALETTE.PIPE_DARK : PALETTE.METAL_DARK;
      const g = cylGeom(r, r, h, seg, cx, y0, cz, base);
      paintVertices(g, (o, x, y, z, nx, ny) => { o.setHex(ny > 0.6 ? (style === 'pipe' ? PALETTE.PIPE_LIGHT : PALETTE.METAL) : base); });
      bakeAO(g, y0);
      out.push(g);
      out.push(cylGeom(r + 0.06, r + 0.06, Math.min(0.12, h * 0.2), seg, cx, y1 - Math.min(0.12, h * 0.2), cz, dark));
      if (h > 1.2) out.push(cylGeom(r + 0.05, r + 0.05, 0.1, seg, cx, y0 + h * 0.4, cz, dark));
      break;
    }
    default: {
      const g = cylGeom(r, r, h, seg, cx, y0, cz, PALETTE.CONCRETE, false, h > 0.6 ? 2 : 1);
      const top = new THREE.Color().setHex(PALETTE.CONCRETE_LIGHT), side = new THREE.Color().setHex(PALETTE.CONCRETE);
      paintTriangles(g, (o, f) => { o.copy(f.ny > 0.6 ? top : side); });
      out.push(g);
      out.push(cylGeom(r + 0.04, r + 0.04, Math.min(0.08, h * 0.2), seg, cx, y1 - Math.min(0.08, h * 0.2), cz, PALETTE.CONCRETE_DARK));
      if (h > 0.5) {
        const pl = cylGeom(r + 0.03, r + 0.05, Math.min(0.16, h * 0.2), seg, cx, y0, cz, PALETTE.CONCRETE_DARK);
        bakeAO(pl, y0, 0.16, 0.75);
        out.push(pl);
      }
    }
  }
  return out;
}

function buildRamp(e, ctx) {
  const { min, max } = e;
  const up = e.up || '+x';
  const style = e.style || 'laterite';
  const col = colorsFor(style);
  const along = up[1] === 'x' ? max[0] - min[0] : max[2] - min[2];
  const rise = max[1] - min[1];
  const slopeLen = Math.hypot(along, rise);
  const period = style === 'wood' ? 0.3 : (style === 'concrete' ? 0.32 : 0.9);
  const strips = clamp(Math.round(slopeLen / period), 1, ctx.lowDetail ? 12 : 48);
  const g = wedgeGeom(min, max, up, e.thickness ?? 0.4, strips);
  const top = new THREE.Color().setHex(style === 'grass' ? PALETTE.GRASS : col.top);
  const top2 = new THREE.Color().setHex(style === 'grass' ? PALETTE.GRASS_LIGHT : (style === 'wood' ? PALETTE.WOOD : col.side));
  const side = new THREE.Color().setHex(col.side), bottom = new THREE.Color().setHex(col.bottom);
  const axisIdx = up[1] === 'x' ? 'cx' : 'cz';
  const a0 = up[1] === 'x' ? min[0] : min[2];
  const stripW = along / strips;
  paintTriangles(g, (o, f) => {
    if (f.ny > 0.3) {
      const idx = Math.floor((f[axisIdx] - a0) / stripW + 1e-4);
      const amt = style === 'wood' || style === 'concrete' ? 0.55 : 0.18;
      o.copy(top).lerp(top2, idx % 2 ? amt : 0).multiplyScalar(0.97 + hash3(idx, 1, 2) * 0.06);
    } else if (f.ny < -0.5) {
      o.copy(bottom).multiplyScalar(0.8);
    } else {
      o.copy(bottom).lerp(side, clamp((f.cy - (min[1] - 0.4)) / Math.max(0.4, rise + 0.4), 0, 1));
    }
  });
  return [g];
}

// ---------------------------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------------------------

/**
 * World-space geometries for one static entity (box | cyl | ramp). `ctx` = {rng, center:{x,z}, signs:[], lowDetail}.
 * Returns [] for the 'invisible' style.
 */
export function buildPlatformGeometry(entity, ctx = {}) {
  if (!entity || entity.style === 'invisible') return [];
  if (entity.type === 'cyl') return buildCyl(entity, ctx);
  if (entity.type === 'ramp') return buildRamp(entity, ctx);
  if (entity.type !== 'box') return [];
  const min = entity.min, max = entity.max;
  if (!(max[0] > min[0] && max[1] > min[1] && max[2] > min[2])) return [];
  const style = entity.style || 'grass';
  switch (style) {
    case 'grass': return layeredBox(min, max, STYLE_COLORS.grass, ctx, PALETTE.GRASS, PALETTE.GRASS_DARK);
    case 'laterite': return layeredBox(min, max, STYLE_COLORS.laterite, ctx, PALETTE.LATERITE_LIGHT, PALETTE.EARTH_PATH);
    case 'rock': return rockBox(min, max, ctx);
    case 'concrete': return concreteBox(min, max, ctx);
    case 'wood': return woodBox(min, max, ctx);
    case 'brick': return brickBox(min, max, ctx);
    case 'metal': return metalBox(min, max, ctx);
    case 'pipe': return pipeBox(min, max, ctx);
    case 'house_tin': return houseTin(min, max, ctx, entity);
    case 'kiosque': return kiosqueBox(min, max, ctx, entity);
    default: return concreteBox(min, max, ctx);
  }
}

/** Plain-sign variant used by platforms with a `sign` but no facade logic (all styles except buildings). */
export function buildPlatformSign(entity, ctx) {
  if (!entity || !entity.sign || entity.type !== 'box' || entity.style === 'house_tin' || entity.style === 'kiosque' || entity.style === 'invisible') return [];
  const out = [];
  const front = entity.front || pickFront(entity.min, entity.max, ctx.center);
  const f = faceFrame(entity.min, entity.max, front);
  const y = entity.max[1] - Math.min(0.35, (entity.max[1] - entity.min[1]) * 0.5);
  addSignBoard(out, ctx, f, 0, y, entity.sign, PALETTE.WOOD_DARK, PALETTE.WOOD_LIGHT, 0x3a2414);
  return out;
}

/** Merged local geometry for a box of `size` centred at the origin (movers, blocks). */
export function buildLocalBox(size, style, ctx = {}) {
  const [sx, sy, sz] = size;
  const geoms = buildPlatformGeometry({ type: 'box', min: [-sx / 2, -sy / 2, -sz / 2], max: [sx / 2, sy / 2, sz / 2], style }, ctx);
  return mergeStatic(geoms);
}

// ---------------------------------------------------------------------------------------------
// Sign text
// ---------------------------------------------------------------------------------------------

/** Draws one sign label into a canvas region. */
export function drawSignLabel(c2d, text, x, y, w, h, bgHex, fgHex) {
  c2d.save();
  const r = Math.min(h * 0.22, 18);
  c2d.fillStyle = toCss(bgHex);
  c2d.beginPath();
  if (c2d.roundRect) c2d.roundRect(x + 2, y + 2, w - 4, h - 4, r); else c2d.rect(x + 2, y + 2, w - 4, h - 4);
  c2d.fill();
  c2d.strokeStyle = 'rgba(255,255,255,0.35)';
  c2d.lineWidth = Math.max(2, h * 0.04);
  c2d.stroke();
  let size = Math.floor(h * 0.6);
  c2d.font = `700 ${size}px system-ui, "Segoe UI", Roboto, Arial, sans-serif`;
  const maxW = w * 0.9;
  const mw = c2d.measureText(text).width;
  if (mw > maxW) {
    size = Math.max(10, Math.floor(size * maxW / mw));
    c2d.font = `700 ${size}px system-ui, "Segoe UI", Roboto, Arial, sans-serif`;
  }
  c2d.fillStyle = toCss(fgHex);
  c2d.textAlign = 'center';
  c2d.textBaseline = 'middle';
  c2d.fillText(text, x + w / 2, y + h / 2 + size * 0.04);
  c2d.restore();
}

function signQuadVerts(s, u0, v0, u1, v1, pos, uvs) {
  // quad facing yaw, centred at (x, y, z), width along "right" = (cos yaw, 0, -sin yaw)
  const ax = Math.cos(s.yaw), az = -Math.sin(s.yaw);
  const hw = s.w / 2, hh = s.h / 2;
  const p = (u, v) => [s.x + ax * u, s.y + v, s.z + az * u];
  const bl = p(-hw, -hh), br = p(hw, -hh), tr = p(hw, hh), tl = p(-hw, hh);
  pos.push(...bl, ...br, ...tr, ...bl, ...tr, ...tl);
  uvs.push(u0, v0, u1, v0, u1, v1, u0, v0, u1, v1, u0, v1);
}

/** Collects sign quads and builds ONE mesh with a text atlas (one draw call for all static signs). */
export class SignBatch {
  constructor() {
    this.items = [];
    this.mesh = null;
    this.texture = null;
  }

  add(spec) {
    if (spec && spec.text) this.items.push(spec);
  }

  build() {
    if (this.items.length === 0 || typeof document === 'undefined') return null;
    const W = 512;
    const rows = this.items.map((s) => clamp(Math.round(W * s.h / Math.max(0.1, s.w)), 48, 256));
    const totalH = rows.reduce((a, b) => a + b, 0);
    const H = Math.min(4096, totalH);
    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const c2d = canvas.getContext('2d');
    const pos = [], uvs = [];
    let y = 0;
    this.items.forEach((s, i) => {
      const rh = rows[i];
      if (y + rh > H) return;
      drawSignLabel(c2d, s.text, 0, y, W, rh, s.bg ?? PALETTE.WOOD_LIGHT, s.fg ?? 0x3a2414);
      // canvas y grows downward; flipY texture: v = 1 - y/H
      signQuadVerts(s, 0, 1 - (y + rh) / H, 1, 1 - y / H, pos, uvs);
      y += rh;
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
    g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));
    g.computeBoundingSphere();
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    const mat = new THREE.MeshBasicMaterial({ map: tex, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
    mat.name = 'signs';
    this.texture = tex;
    this.mesh = new THREE.Mesh(g, mat);
    this.mesh.name = 'signs';
    this.mesh.matrixAutoUpdate = false;
    return this.mesh;
  }

  dispose() {
    if (this.mesh) {
      if (this.mesh.parent) this.mesh.parent.remove(this.mesh);
      this.mesh.geometry.dispose();
      this.mesh.material.dispose();
      this.mesh = null;
    }
    if (this.texture) { this.texture.dispose(); this.texture = null; }
    this.items.length = 0;
  }
}

/** Single sign mesh (own texture) for dynamic views; facing +Z, centred at the origin. */
export function createSignMesh(text, w, h, bgHex = PALETTE.HYDRIA_BLUE, fgHex = 0xffffff) {
  const batch = new SignBatch();
  batch.add({ x: 0, y: 0, z: 0, yaw: 0, w, h, text: String(text).slice(0, 22), bg: bgHex, fg: fgHex });
  const mesh = batch.build();
  if (mesh) mesh.matrixAutoUpdate = true;
  return { mesh, dispose: () => batch.dispose() };
}

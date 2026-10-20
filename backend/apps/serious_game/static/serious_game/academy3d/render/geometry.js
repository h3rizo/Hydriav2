// render/geometry.js — geometry helpers shared by the static world, props and characters (spec §12.3).
// Every static geometry goes through prepStatic(): non-indexed, attributes exactly position / normal / color
// (Float32, linear colour), no uv. Build-time code: small allocations are acceptable here, never per frame.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

// ---------------------------------------------------------------------------------------------
// Seeded randomness
// ---------------------------------------------------------------------------------------------

/** 32-bit string hash (FNV-1a). */
export function hashString(str) {
  let h = 0x811c9dc5;
  const s = String(str ?? '');
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** mulberry32 PRNG: returns a function giving floats in [0, 1). */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function rand() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Seeded RNG with helpers. */
export function makeRng(seed) {
  const r = mulberry32(typeof seed === 'number' ? seed : hashString(seed));
  r.range = (a, b) => a + (b - a) * r();
  r.int = (a, b) => Math.floor(a + (b - a + 1) * r());
  r.pick = (arr) => arr[Math.floor(r() * arr.length) % arr.length];
  r.sign = () => (r() < 0.5 ? -1 : 1);
  return r;
}

/** Deterministic hash of a position in [0,1): lets shared edges jitter identically. */
export function hash3(x, y, z, salt = 0) {
  const ix = Math.round(x * 1000), iy = Math.round(y * 1000), iz = Math.round(z * 1000);
  let h = Math.imul(ix, 73856093) ^ Math.imul(iy, 19349663) ^ Math.imul(iz, 83492791) ^ Math.imul(salt + 1, 2654435761);
  h = Math.imul(h ^ (h >>> 13), 0x5bd1e995);
  h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
}

// ---------------------------------------------------------------------------------------------
// Colours
// ---------------------------------------------------------------------------------------------

const _col = new THREE.Color();
const _col2 = new THREE.Color();

/** Linear THREE.Color from an sRGB hex (writes into `out` when given). */
export function lin(hex, out = new THREE.Color()) {
  return out.setHex(hex);
}

/** Mix two sRGB hexes in linear space; returns a THREE.Color. */
export function mixHex(a, b, t, out = new THREE.Color()) {
  out.setHex(a);
  _col2.setHex(b);
  return out.lerp(_col2, t);
}

function ensureColorAttr(geom) {
  const pos = geom.attributes.position;
  let col = geom.attributes.color;
  if (!col || col.itemSize !== 3 || !(col.array instanceof Float32Array) || col.count !== pos.count) {
    col = new THREE.BufferAttribute(new Float32Array(pos.count * 3).fill(1), 3);
    geom.setAttribute('color', col);
  }
  return col;
}

/** Uniform vertex colour. `color` is a hex or a THREE.Color (linear). */
export function setColor(geom, color) {
  const c = typeof color === 'number' ? _col.setHex(color) : color;
  const col = ensureColorAttr(geom);
  const a = col.array;
  for (let i = 0; i < a.length; i += 3) { a[i] = c.r; a[i + 1] = c.g; a[i + 2] = c.b; }
  col.needsUpdate = true;
  return geom;
}

/** Multiplies vertex colours by a factor (or per-vertex function (x,y,z,nx,ny,nz) => factor). */
export function shadeColors(geom, factor) {
  const col = ensureColorAttr(geom);
  const p = geom.attributes.position.array, n = geom.attributes.normal ? geom.attributes.normal.array : null, a = col.array;
  for (let i = 0; i < a.length; i += 3) {
    const f = typeof factor === 'function'
      ? factor(p[i], p[i + 1], p[i + 2], n ? n[i] : 0, n ? n[i + 1] : 1, n ? n[i + 2] : 0)
      : factor;
    a[i] *= f; a[i + 1] *= f; a[i + 2] *= f;
  }
  col.needsUpdate = true;
  return geom;
}

const _face = { nx: 0, ny: 0, nz: 0, cx: 0, cy: 0, cz: 0, index: 0 };

/**
 * Per-triangle painting on a NON-indexed geometry. painter(outColor, face) must set outColor (linear THREE.Color)
 * and may return false to keep the existing colour. face = {nx,ny,nz (face normal), cx,cy,cz (centroid), index}.
 */
export function paintTriangles(geom, painter) {
  const pos = geom.attributes.position.array;
  const col = ensureColorAttr(geom).array;
  const triCount = pos.length / 9;
  for (let t = 0; t < triCount; t++) {
    const o = t * 9;
    const ax = pos[o], ay = pos[o + 1], az = pos[o + 2];
    const bx = pos[o + 3], by = pos[o + 4], bz = pos[o + 5];
    const cx = pos[o + 6], cy = pos[o + 7], cz = pos[o + 8];
    const ux = bx - ax, uy = by - ay, uz = bz - az;
    const vx = cx - ax, vy = cy - ay, vz = cz - az;
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const len = Math.hypot(nx, ny, nz) || 1;
    _face.nx = nx / len; _face.ny = ny / len; _face.nz = nz / len;
    _face.cx = (ax + bx + cx) / 3; _face.cy = (ay + by + cy) / 3; _face.cz = (az + bz + cz) / 3;
    _face.index = t;
    if (painter(_col, _face) === false) continue;
    for (let k = 0; k < 3; k++) {
      col[o + k * 3] = _col.r; col[o + k * 3 + 1] = _col.g; col[o + k * 3 + 2] = _col.b;
    }
  }
  geom.attributes.color.needsUpdate = true;
  return geom;
}

/** Per-vertex painting. painter(outColor, x,y,z, nx,ny,nz, i) sets outColor or returns false. */
export function paintVertices(geom, painter) {
  const pos = geom.attributes.position.array;
  const nrm = geom.attributes.normal ? geom.attributes.normal.array : null;
  const col = ensureColorAttr(geom).array;
  for (let i = 0, v = 0; i < pos.length; i += 3, v++) {
    _col.setRGB(col[i], col[i + 1], col[i + 2]);
    if (painter(_col, pos[i], pos[i + 1], pos[i + 2], nrm ? nrm[i] : 0, nrm ? nrm[i + 1] : 1, nrm ? nrm[i + 2] : 0, v) === false) continue;
    col[i] = _col.r; col[i + 1] = _col.g; col[i + 2] = _col.b;
  }
  geom.attributes.color.needsUpdate = true;
  return geom;
}

/** Colour by face orientation: top (ny > 0.5), bottom (ny < -0.5), sides. Hex values. */
export function paintByNormal(geom, topHex, sideHex, bottomHex = sideHex) {
  const top = new THREE.Color().setHex(topHex), side = new THREE.Color().setHex(sideHex), bottom = new THREE.Color().setHex(bottomHex);
  return paintTriangles(geom, (out, f) => { out.copy(f.ny > 0.5 ? top : (f.ny < -0.5 ? bottom : side)); });
}

/** Vertical gradient between two hexes over [y0, y1]. */
export function paintGradientY(geom, bottomHex, topHex, y0, y1) {
  const a = new THREE.Color().setHex(bottomHex), b = new THREE.Color().setHex(topHex);
  const span = Math.max(1e-4, y1 - y0);
  return paintVertices(geom, (out, x, y) => { out.copy(a).lerp(b, Math.min(1, Math.max(0, (y - y0) / span))); });
}

/** Random per-triangle lightness jitter (±amount), deterministic by face centroid. */
export function jitterTriangleColors(geom, amount = 0.06, salt = 0) {
  const col = ensureColorAttr(geom).array;
  const pos = geom.attributes.position.array;
  for (let o = 0; o < pos.length; o += 9) {
    const f = 1 + (hash3((pos[o] + pos[o + 3] + pos[o + 6]) / 3, (pos[o + 1] + pos[o + 4] + pos[o + 7]) / 3,
      (pos[o + 2] + pos[o + 5] + pos[o + 8]) / 3, salt) * 2 - 1) * amount;
    for (let k = 0; k < 9; k++) col[o + k] *= f;
  }
  geom.attributes.color.needsUpdate = true;
  return geom;
}

/**
 * Baked ambient occlusion (spec §12.3): wall vertices (|ny| < 0.7) in the bottom `band` metres above `groundY`
 * are darkened down to `factor` at the ground.
 */
export function bakeAO(geom, groundY, band = 0.3, factor = 0.72) {
  return shadeColors(geom, (x, y, z, nx, ny) => {
    if (Math.abs(ny) >= 0.7) return 1;
    const h = y - groundY;
    if (h >= band || h < -0.01) return 1;
    return factor + (1 - factor) * Math.max(0, h / band);
  });
}

// ---------------------------------------------------------------------------------------------
// Preparation and transforms
// ---------------------------------------------------------------------------------------------

/**
 * Converts to the static layout: non-indexed, exactly position/normal/color (Float32), no groups.
 * Optionally paints a uniform colour (hex) when the geometry has no colour yet.
 */
export function prepStatic(geom, colorHex) {
  let g = geom;
  if (g.index) {
    g = geom.toNonIndexed();
    geom.dispose();
  }
  for (const name of Object.keys(g.attributes)) {
    if (name !== 'position' && name !== 'normal' && name !== 'color') g.deleteAttribute(name);
  }
  g.morphAttributes = {};
  g.clearGroups();
  if (!g.attributes.normal) g.computeVertexNormals();
  const hadColor = !!g.attributes.color && g.attributes.color.array instanceof Float32Array && g.attributes.color.itemSize === 3;
  if (!hadColor) {
    if (g.attributes.color) g.deleteAttribute('color');
    setColor(g, colorHex ?? 0xffffff);
  } else if (colorHex !== undefined) {
    setColor(g, colorHex);
  }
  return g;
}

/** Flat (faceted) normals for a non-indexed geometry. */
export function flatNormals(geom) {
  geom.computeVertexNormals();
  return geom;
}

const _m = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _e = new THREE.Euler();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();

/** Applies translate · rotate(YXZ: rx, ry, rz) · scale in place. Returns geom. */
export function tf(geom, x = 0, y = 0, z = 0, ry = 0, sx = 1, sy = sx, sz = sx, rx = 0, rz = 0) {
  _e.set(rx, ry, rz, 'YXZ');
  _q.setFromEuler(_e);
  _m.compose(_p.set(x, y, z), _q, _s.set(sx, sy, sz));
  geom.applyMatrix4(_m);
  return geom;
}

/** Applies a Matrix4 in place. */
export function applyMatrix(geom, m) {
  geom.applyMatrix4(m);
  return geom;
}

/**
 * Deterministic jitter of positions, consistent across shared corners (hash of the original position).
 * `mask(x,y,z)` returns [kx, ky, kz] multipliers or null to skip a vertex.
 */
export function jitterPositions(geom, amp, mask = null, salt = 0) {
  const p = geom.attributes.position.array;
  for (let i = 0; i < p.length; i += 3) {
    const x = p[i], y = p[i + 1], z = p[i + 2];
    const m = mask ? mask(x, y, z) : null;
    if (mask && !m) continue;
    const kx = m ? m[0] : 1, ky = m ? m[1] : 1, kz = m ? m[2] : 1;
    p[i] = x + (hash3(x, y, z, salt) * 2 - 1) * amp * kx;
    p[i + 1] = y + (hash3(x, y, z, salt + 7) * 2 - 1) * amp * ky;
    p[i + 2] = z + (hash3(x, y, z, salt + 13) * 2 - 1) * amp * kz;
  }
  geom.attributes.position.needsUpdate = true;
  return geom;
}

/** Merges prepped geometries (all non-indexed with position/normal/color) and disposes the inputs. */
export function mergeStatic(geoms, disposeInputs = true) {
  const list = geoms.filter((g) => g && g.attributes && g.attributes.position && g.attributes.position.count > 0);
  if (list.length === 0) return null;
  let out;
  if (list.length === 1) {
    out = disposeInputs ? list[0] : list[0].clone();
  } else {
    out = mergeGeometries(list, false);
    if (disposeInputs) for (const g of list) g.dispose();
  }
  if (out) {
    out.computeBoundingSphere();
    out.computeBoundingBox();
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// Primitive builders (all return prepped geometries)
// ---------------------------------------------------------------------------------------------

/** Box centred on (x, y, z). */
export function boxGeom(w, h, d, x = 0, y = 0, z = 0, hex = 0xffffff, segs = null) {
  const g = segs ? new THREE.BoxGeometry(w, h, d, segs[0], segs[1], segs[2]) : new THREE.BoxGeometry(w, h, d);
  return tf(prepStatic(g, hex), x, y, z);
}

/** Box from min/max corners. */
export function boxMinMax(x0, y0, z0, x1, y1, z1, hex = 0xffffff, segs = null) {
  return boxGeom(Math.max(1e-3, x1 - x0), Math.max(1e-3, y1 - y0), Math.max(1e-3, z1 - z0),
    (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, hex, segs);
}

/** Rounded box centred on (x, y, z). Radius is clamped so it always fits. */
export function roundedBox(w, h, d, radius = 0.1, segments = 2, x = 0, y = 0, z = 0, hex = 0xffffff) {
  const r = Math.max(0.005, Math.min(radius, w / 2 - 1e-3, h / 2 - 1e-3, d / 2 - 1e-3));
  const g = new RoundedBoxGeometry(w, h, d, segments, r);
  return tf(prepStatic(g, hex), x, y, z);
}

/** Cylinder whose base sits at y (not centred). */
export function cylGeom(rTop, rBottom, h, seg = 12, x = 0, y = 0, z = 0, hex = 0xffffff, openEnded = false, heightSeg = 1) {
  const g = new THREE.CylinderGeometry(rTop, rBottom, h, seg, heightSeg, openEnded);
  return tf(prepStatic(g, hex), x, y + h / 2, z);
}

/** Sphere centred on (x, y, z), optionally scaled. */
export function sphereGeom(r, ws = 12, hs = 8, x = 0, y = 0, z = 0, hex = 0xffffff, sx = 1, sy = sx, sz = sx) {
  const g = new THREE.SphereGeometry(r, ws, hs);
  return tf(prepStatic(g, hex), x, y, z, 0, sx, sy, sz);
}

/** Faceted icosahedron centred on (x, y, z). */
export function icoGeom(r, detail = 0, x = 0, y = 0, z = 0, hex = 0xffffff, sx = 1, sy = sx, sz = sx) {
  const g = new THREE.IcosahedronGeometry(r, detail);
  return tf(prepStatic(g, hex), x, y, z, 0, sx, sy, sz);
}

/** Capsule along Y centred on (x, y, z). */
export function capsuleGeom(r, length, capSeg = 3, radial = 10, x = 0, y = 0, z = 0, hex = 0xffffff) {
  const g = new THREE.CapsuleGeometry(r, length, capSeg, radial);
  return tf(prepStatic(g, hex), x, y, z);
}

/** Lathe from [[r, y], ...] profile. */
export function latheGeom(profile, segments = 12, hex = 0xffffff) {
  const pts = profile.map(([r, y]) => new THREE.Vector2(Math.max(0, r), y));
  return prepStatic(new THREE.LatheGeometry(pts, segments), hex);
}

/** Flat disc on the XZ plane facing +Y, centred on (x, y, z). */
export function discGeom(r, seg = 12, x = 0, y = 0, z = 0, hex = 0xffffff) {
  const g = new THREE.CircleGeometry(r, seg);
  g.rotateX(-Math.PI / 2);
  return tf(prepStatic(g, hex), x, y, z);
}

const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _up = new THREE.Vector3(0, 1, 0);

/** Cylinder (or any Y-aligned unit geometry built with base at 0 and height 1) stretched between two points. */
export function cylBetween(ax, ay, az, bx, by, bz, r, seg = 8, hex = 0xffffff, rEnd = r) {
  _a.set(ax, ay, az); _b.set(bx, by, bz);
  _dir.subVectors(_b, _a);
  const len = _dir.length();
  if (len < 1e-4) return null;
  const g = prepStatic(new THREE.CylinderGeometry(rEnd, r, len, seg, 1, false), hex);
  g.translate(0, len / 2, 0);
  _q.setFromUnitVectors(_up, _dir.normalize());
  _m.compose(_a, _q, _s.set(1, 1, 1));
  g.applyMatrix4(_m);
  return g;
}

/**
 * Axis-aligned wedge for ramps (spec §5.1): footprint min.xz..max.xz, surface from min.y on the low side to max.y
 * on the side named by `up` ('+x'|'-x'|'+z'|'-z'), bottom at min.y - thickness. The top is split into `strips`
 * bands across the slope (for stylised planks / tracks).
 */
export function wedgeGeom(min, max, up, thickness = 0.4, strips = 1) {
  const x0 = min[0], x1 = max[0], z0 = min[2], z1 = max[2];
  const yLo = min[1], yHi = max[1], yb = min[1] - thickness;
  const axis = up[1];
  const positive = up[0] !== '-';
  // surface height at (x, z)
  const hAt = (x, z) => {
    let t;
    if (axis === 'x') t = (x - x0) / Math.max(1e-4, x1 - x0);
    else t = (z - z0) / Math.max(1e-4, z1 - z0);
    if (!positive) t = 1 - t;
    return yLo + (yHi - yLo) * t;
  };
  const verts = [];
  const quad = (a, b, c, d) => { verts.push(...a, ...b, ...c, ...a, ...c, ...d); };
  const B = (x, z) => [x, yb, z];
  const T = (x, z) => [x, hAt(x, z), z];
  // top, split into strips along the slope axis
  const n = Math.max(1, Math.floor(strips));
  for (let i = 0; i < n; i++) {
    const u0 = i / n, u1 = (i + 1) / n;
    if (axis === 'x') {
      const xa = x0 + (x1 - x0) * u0, xb = x0 + (x1 - x0) * u1;
      quad(T(xa, z0), T(xa, z1), T(xb, z1), T(xb, z0));
    } else {
      const za = z0 + (z1 - z0) * u0, zb = z0 + (z1 - z0) * u1;
      quad(T(x0, za), T(x0, zb), T(x1, zb), T(x1, za));
    }
  }
  quad(B(x0, z0), B(x1, z0), B(x1, z1), B(x0, z1));          // bottom
  quad(B(x0, z0), T(x0, z0), T(x1, z0), B(x1, z0));          // -z
  quad(B(x0, z1), B(x1, z1), T(x1, z1), T(x0, z1));          // +z
  quad(B(x0, z0), B(x0, z1), T(x0, z1), T(x0, z0));          // -x
  quad(B(x1, z0), T(x1, z0), T(x1, z1), B(x1, z1));          // +x
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(verts), 3));
  g.computeVertexNormals();
  return prepStatic(g, 0xffffff);
}

/** Generic triangle soup from a flat number array (x,y,z per vertex), flat normals. */
export function soupGeom(verts, hex = 0xffffff) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(verts instanceof Float32Array ? verts : new Float32Array(verts), 3));
  g.computeVertexNormals();
  return prepStatic(g, hex);
}

/** Total triangle count of a list of geometries (debug / budget checks). */
export function triangleCount(geoms) {
  let n = 0;
  for (const g of geoms) if (g) n += (g.index ? g.index.count : g.attributes.position.count) / 3;
  return n;
}

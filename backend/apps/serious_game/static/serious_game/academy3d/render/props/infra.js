// render/props/infra.js — ouvrage views (bf, pompe, kiosque, station, chateau), valve view and usager view
// (character + water-meter post with a state lamp), plus small view helpers shared with interactives.js.
// Views place themselves at def.pos / def.yaw; the caller adds view.object3d to the scene (spec §12.5).
import * as THREE from 'three';
import { PALETTE, STATE_COLORS } from 'a3d/render/palette.js';
import {
  boxGeom, roundedBox, cylGeom, sphereGeom, latheGeom, cylBetween, prepStatic, tf, mergeStatic, paintTriangles,
  paintVertices, bakeAO, makeRng, hashString,
} from 'a3d/render/geometry.js';
import { getActiveEngine } from 'a3d/render/materials.js';
import { buildPlatformGeometry, createSignMesh } from 'a3d/render/props/platforms.js';
import { createCharacter } from 'a3d/actors/characters.js';

const DEG = Math.PI / 180;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const _wp = new THREE.Vector3();

// ---------------------------------------------------------------------------------------------
// View kit (shared with interactives.js)
// ---------------------------------------------------------------------------------------------

/** Book-keeping for one view: owned geometries / materials, effects, pop spring, progress arc, lamps. */
export class ViewKit {
  constructor(def, opts = {}) {
    this.engine = getActiveEngine();
    this.mats = this.engine ? this.engine.materials : null;
    this.def = def || {};
    this.root = new THREE.Group();
    this.root.name = opts.name || 'view';
    const pos = this.def.pos || [0, 0, 0];
    if (opts.place !== false) {
      this.root.position.set(pos[0], pos[1], pos[2]);
      this.root.rotation.y = (Number.isFinite(this.def.yaw) ? this.def.yaw : 0) * DEG;
    }
    this.inner = new THREE.Group();
    this.root.add(this.inner);
    this.noFog = !!opts.noFog;
    this._geoms = [];
    this._ownMats = [];
    this._emitters = [];
    this._outlines = [];
    this._bound = [];
    this._disposers = [];
    this._popS = 0; this._popV = 0;
    this._halo = null;
    this._progress = null;
  }

  worldMaterial() {
    if (!this.mats) return new THREE.MeshToonMaterial({ vertexColors: true });
    return this.mats.get(this.noFog ? 'worldSoftNoFog' : 'worldSoft');
  }

  /** Mesh from geometries (merged), parented to `parent` (default inner). */
  mesh(geoms, parent = this.inner, opts = {}) {
    const list = Array.isArray(geoms) ? geoms : [geoms];
    const g = mergeStatic(list);
    if (!g) return null;
    this._geoms.push(g);
    const m = new THREE.Mesh(g, opts.material || this.worldMaterial());
    m.castShadow = opts.castShadow !== false;
    m.receiveShadow = !!opts.receiveShadow;
    if (opts.name) m.name = opts.name;
    parent.add(m);
    if (opts.outline && this.mats) this._outlines.push(this.mats.addOutline(m));
    return m;
  }

  /** Unlit state lamp sphere. */
  lamp(x, y, z, r = 0.07, parent = this.inner) {
    const g = prepStatic(new THREE.SphereGeometry(r, 10, 7));
    this._geoms.push(g);
    const m = new THREE.Mesh(g, this.mats ? this.mats.lamp(STATE_COLORS.healthy) : new THREE.MeshBasicMaterial());
    m.position.set(x, y, z);
    m.castShadow = false;
    parent.add(m);
    return m;
  }

  setLamp(lampMesh, hex) {
    if (lampMesh && this.mats) lampMesh.material = this.mats.lamp(hex);
  }

  glowMaterial(hex, opacity) {
    const m = this.mats ? this.mats.createGlow(hex, opacity)
      : new THREE.MeshBasicMaterial({ color: hex, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false });
    this._ownMats.push(m);
    return m;
  }

  continuous(preset, anchor, opts) {
    if (!this.engine) return { stop() {} };
    const h = this.engine.fx.particles.addContinuous(preset, anchor, opts);
    this._emitters.push(h);
    return h;
  }

  burst(preset, local, opts) {
    if (!this.engine) return;
    this.root.updateWorldMatrix(true, true);
    _wp.set(local[0], local[1], local[2]).applyMatrix4(this.inner.matrixWorld);
    this.engine.fx.particles.emit(preset, _wp, opts);
  }

  pop(strength = 1) {
    this._popV += 2.6 * strength;
  }

  /** Ground progress arc (yellow) of radius r around the view. */
  ensureProgress(r) {
    if (this._progress) return this._progress;
    const seg = 48;
    // Positive theta keeps the winding front-facing once laid flat; segments are indexed in theta order,
    // so a draw range of n·6 indices shows the first n segments.
    const g = new THREE.RingGeometry(r, r + 0.16, seg, 1, Math.PI / 2, Math.PI * 2);
    g.rotateX(-Math.PI / 2);
    this._geoms.push(g);
    const bgG = new THREE.RingGeometry(r, r + 0.16, seg, 1);
    bgG.rotateX(-Math.PI / 2);
    this._geoms.push(bgG);
    const fill = new THREE.Mesh(g, this.glowMaterial(STATE_COLORS.repairing, 0.95));
    const bg = new THREE.Mesh(bgG, this.glowMaterial(0xffffff, 0.18));
    fill.position.y = 0.06; bg.position.y = 0.055;
    fill.renderOrder = 16; bg.renderOrder = 15;
    fill.castShadow = bg.castShadow = false;
    const grp = new THREE.Group();
    grp.add(bg, fill);
    grp.visible = false;
    this.root.add(grp);
    this._progress = { grp, fill, seg, indexPerSeg: 6 };
    return this._progress;
  }

  setProgress(t, r = 1) {
    const p = this.ensureProgress(r);
    if (t === null || t === undefined || !Number.isFinite(t)) { p.grp.visible = false; return; }
    p.grp.visible = true;
    const n = Math.round(clamp(t, 0, 1) * p.seg);
    p.fill.geometry.setDrawRange(0, n * p.indexPerSeg);
  }

  /** Expanding cyan halo ring (healthy burst). */
  halo(r = 1, hex = PALETTE.HYDRIA_CYAN) {
    if (!this._halo) {
      const g = new THREE.RingGeometry(0.82, 1.0, 40, 1);
      g.rotateX(-Math.PI / 2);
      this._geoms.push(g);
      const m = new THREE.Mesh(g, this.glowMaterial(hex, 0));
      m.renderOrder = 17;
      m.castShadow = false;
      m.position.y = 0.08;
      this.root.add(m);
      this._halo = { mesh: m, t: 1, r };
    }
    this._halo.mesh.material.color.setHex(hex);
    this._halo.t = 0;
    this._halo.r = r;
  }

  updateKit(dt) {
    // pop spring on the inner group
    if (this._popV !== 0 || this._popS !== 0) {
      let rem = Math.min(dt, 0.1);
      while (rem > 1e-5) {
        const h = Math.min(rem, 1 / 120);
        const a = -260 * this._popS - 14 * this._popV;
        this._popV += a * h;
        this._popS = clamp(this._popS + this._popV * h, -0.4, 0.4);
        rem -= h;
      }
      if (Math.abs(this._popS) < 1e-4 && Math.abs(this._popV) < 1e-3) { this._popS = 0; this._popV = 0; }
      const s = this._popS;
      this.inner.scale.set(1 - s * 0.35, 1 + s, 1 - s * 0.35);
    }
    if (this._halo && this._halo.t < 1) {
      const h = this._halo;
      h.t = Math.min(1, h.t + dt / 0.9);
      const e = 1 - Math.pow(1 - h.t, 3);
      const s = h.r * (0.6 + 1.2 * e);
      h.mesh.scale.set(s, 1, s);
      h.mesh.material.opacity = 0.85 * (1 - h.t);
      h.mesh.visible = h.t < 1;
    }
  }

  onDispose(fn) { this._disposers.push(fn); }

  dispose() {
    for (const e of this._emitters) e.stop();
    this._emitters.length = 0;
    for (const fn of this._disposers) { try { fn(); } catch (e) { console.error('[a3d]', e); } }
    if (this.mats) for (const o of this._outlines) this.mats.removeOutline(o);
    for (const g of this._geoms) g.dispose();
    for (const m of this._ownMats) m.dispose();
    this._geoms.length = 0;
    this._ownMats.length = 0;
    if (this.root.parent) this.root.parent.remove(this.root);
  }
}

// ---------------------------------------------------------------------------------------------
// Ouvrage builders (local space, facing +Z)
// ---------------------------------------------------------------------------------------------

function apron(r, h = 0.12, hex = PALETTE.CONCRETE) {
  const g = cylGeom(r, r + 0.03, h, 20, 0, 0, 0, hex);
  const top = new THREE.Color().setHex(PALETTE.CONCRETE_LIGHT), side = new THREE.Color().setHex(PALETTE.CONCRETE_DARK);
  paintTriangles(g, (o, f) => { o.copy(f.ny > 0.6 ? top : side); });
  return g;
}

function buildBf(kit) {
  const parts = [];
  parts.push(apron(0.45));
  // drain basin under the tap
  const basin = roundedBox(0.42, 0.14, 0.3, 0.04, 1, 0, 0.19, 0.22, PALETTE.CONCRETE);
  parts.push(basin);
  parts.push(boxGeom(0.34, 0.02, 0.22, 0, 0.255, 0.22, PALETTE.WATER_DEEP));
  // pillar
  const pillar = roundedBox(0.24, 0.98, 0.24, 0.05, 2, 0, 0.12 + 0.49, -0.05, 0xf3f1ec);
  parts.push(pillar);
  parts.push(roundedBox(0.26, 0.14, 0.26, 0.04, 1, 0, 0.82, -0.05, PALETTE.HYDRIA_BLUE));
  parts.push(roundedBox(0.28, 0.06, 0.28, 0.02, 1, 0, 1.12, -0.05, PALETTE.HYDRIA_BLUE_DARK));
  parts.push(sphereGeom(0.045, 8, 6, 0, 0.6, 0.075, PALETTE.HYDRIA_CYAN, 1, 1.3, 0.4));        // logo drop
  // tap arm + nozzle
  parts.push(cylBetween(0, 0.72, 0.06, 0, 0.72, 0.24, 0.035, 8, PALETTE.METAL));
  parts.push(cylGeom(0.03, 0.03, 0.12, 8, 0, 0.6, 0.24, PALETTE.METAL));
  parts.push(cylGeom(0.05, 0.05, 0.03, 8, 0, 0.77, 0.12, PALETTE.TOOLBOX_RED));              // tap knob
  kit.mesh(parts, kit.inner, { outline: true, name: 'bf' });
  const lampMesh = kit.lamp(0, 1.22, -0.05, 0.075);
  const leak = new THREE.Object3D(); leak.position.set(0.12, 0.45, -0.05); kit.inner.add(leak);
  const nozzle = new THREE.Object3D(); nozzle.position.set(0, 0.55, 0.24); kit.inner.add(nozzle);
  return { lampMesh, leak, nozzle, radius: 0.45, top: 1.3, leakDir: { x: 0.75, y: 0.6, z: 0.15 } };
}

function buildPompe(kit) {
  const parts = [];
  parts.push(apron(0.6, 0.14));
  parts.push(boxGeom(0.12, 0.03, 0.5, 0, 0.145, 0.45, PALETTE.CONCRETE_DARK));                // drain channel
  const column = cylGeom(0.085, 0.1, 0.95, 12, 0, 0.14, 0, PALETTE.HYDRIA_BLUE);
  bakeAO(column, 0.14, 0.2, 0.75);
  parts.push(column);
  parts.push(cylGeom(0.13, 0.13, 0.06, 12, 0, 0.14, 0, PALETTE.HYDRIA_BLUE_DARK));
  parts.push(roundedBox(0.24, 0.22, 0.32, 0.04, 2, 0, 1.18, -0.02, PALETTE.HYDRIA_BLUE));      // head
  parts.push(roundedBox(0.26, 0.04, 0.34, 0.02, 1, 0, 1.3, -0.02, PALETTE.HYDRIA_BLUE_DARK));
  parts.push(cylBetween(0, 0.78, 0.05, 0, 0.78, 0.36, 0.045, 10, PALETTE.HYDRIA_BLUE));        // spout
  parts.push(cylGeom(0.05, 0.05, 0.05, 10, 0, 0.71, 0.36, PALETTE.HYDRIA_BLUE_DARK));
  parts.push(sphereGeom(0.04, 8, 6, 0, 0.92, 0.095, PALETTE.HYDRIA_CYAN, 1, 1.3, 0.4));
  kit.mesh(parts, kit.inner, { outline: true, name: 'pompe' });
  // handle on its own pivot (droops when broken)
  const handlePivot = new THREE.Group();
  handlePivot.position.set(0, 1.22, -0.15);
  kit.inner.add(handlePivot);
  const hp = [];
  hp.push(boxGeom(0.05, 0.05, 0.78, 0, 0, -0.38, PALETTE.METAL_DARK));
  hp.push(cylGeom(0.04, 0.04, 0.18, 8, 0, -0.09, -0.74, PALETTE.WOOD_DARK));
  hp.push(boxGeom(0.06, 0.1, 0.06, 0, 0.02, 0.02, PALETTE.METAL));
  kit.mesh(hp, handlePivot, { outline: true, name: 'handle' });
  const lampMesh = kit.lamp(0, 1.4, -0.02, 0.07);
  const steam = new THREE.Object3D(); steam.position.set(0, 1.32, 0.05); kit.inner.add(steam);
  const nozzle = new THREE.Object3D(); nozzle.position.set(0, 0.68, 0.36); kit.inner.add(nozzle);
  return { lampMesh, handlePivot, steam, nozzle, radius: 0.6, top: 1.5 };
}

function buildKiosque(kit, def) {
  const ctx = { signs: [], lowDetail: kit.engine ? kit.engine.tier === 'low' : false };
  const box = { type: 'box', style: 'kiosque', min: [-1.5, 0, -1.5], max: [1.5, 2.6, 1.5], front: '+z', sign: (def.name || 'KIOSQUE').slice(0, 22) };
  const parts = buildPlatformGeometry(box, ctx);
  // rooftop tank at the back corner
  parts.push(cylGeom(0.42, 0.42, 0.62, 14, -0.85, 2.6, -0.85, PALETTE.HYDRIA_BLUE));
  parts.push(cylGeom(0.44, 0.44, 0.06, 14, -0.85, 3.2, -0.85, PALETTE.HYDRIA_BLUE_DARK));
  // electrical box on the side (sparks when broken)
  parts.push(roundedBox(0.36, 0.48, 0.14, 0.03, 1, 1.57, 1.3, 0.6, 0x8a96a3));
  kit.mesh(parts, kit.inner, { outline: true, name: 'kiosque' });
  for (const s of ctx.signs) {
    const sm = createSignMesh(s.text, s.w, s.h, s.bg, s.fg);
    if (sm.mesh) {
      sm.mesh.position.set(s.x, s.y, s.z);
      sm.mesh.rotation.y = s.yaw;
      kit.inner.add(sm.mesh);
      kit.onDispose(sm.dispose);
    }
  }
  const lampMesh = kit.lamp(1.1, 2.15, 1.56, 0.09);
  const sparks = new THREE.Object3D(); sparks.position.set(1.66, 1.45, 0.6); kit.inner.add(sparks);
  const leak = new THREE.Object3D(); leak.position.set(-1.5, 0.4, 1.2); kit.inner.add(leak);
  return { lampMesh, sparks, leak, radius: 1.9, top: 3.3, leakDir: { x: -0.8, y: 0.55, z: 0.1 } };
}

function buildStation(kit) {
  const ctx = { signs: [], lowDetail: kit.engine ? kit.engine.tier === 'low' : false };
  const parts = [];
  // pump house (brick, tin roof) inside the 4 × 3 × 4 footprint
  // door on the +x side so the motor and pipes in front do not block it
  parts.push(...buildPlatformGeometry({ type: 'box', style: 'house_tin', min: [-1.55, 0, -1.9], max: [1.55, 2.95, 1.2], front: '+x', roof: 'tin' }, ctx));
  // concrete slab
  const slab = boxGeom(4.0, 0.12, 4.0, 0, 0.06, 0, PALETTE.CONCRETE);
  paintTriangles(slab, (o, f) => { o.setHex(f.ny > 0.5 ? PALETTE.CONCRETE_LIGHT : PALETTE.CONCRETE_DARK); });
  parts.push(slab);
  // big blue pipes coming out of the ground on the front
  for (const x of [-1.2, 1.2]) {
    parts.push(cylBetween(x, 0.12, 1.85, x, 0.7, 1.85, 0.16, 12, PALETTE.PIPE));
    parts.push(cylBetween(x, 0.7, 1.85, x, 0.7, 1.25, 0.16, 12, PALETTE.PIPE));
    parts.push(sphereGeom(0.17, 10, 7, x, 0.7, 1.85, PALETTE.PIPE));
    parts.push(cylBetween(x, 0.7, 1.55, x, 0.7, 1.62, 0.22, 12, PALETTE.PIPE_DARK));
  }
  // pump motor (green-grey) between the pipes
  parts.push(tf(cylGeom(0.28, 0.28, 0.7, 14, 0, -0.35, 0, 0x6f8b6a), 0, 0.5, 1.6, 0, 1, 1, 1, 0, Math.PI / 2));
  parts.push(roundedBox(0.8, 0.12, 0.5, 0.03, 1, 0, 0.18, 1.6, PALETTE.METAL_DARK));
  // control panel beside the door
  parts.push(roundedBox(0.5, 0.65, 0.12, 0.03, 1, 1.0, 1.35, 1.27, 0xdfe5ea));
  parts.push(boxGeom(0.3, 0.12, 0.02, 1.0, 1.5, 1.335, 0x26323d));
  kit.mesh(parts, kit.inner, { outline: true, name: 'station' });
  const lampMesh = kit.lamp(1.0, 1.15, 1.35, 0.065);
  const sparks = new THREE.Object3D(); sparks.position.set(0, 0.85, 1.6); kit.inner.add(sparks);
  const leak = new THREE.Object3D(); leak.position.set(1.2, 0.7, 1.6); kit.inner.add(leak);
  return { lampMesh, sparks, leak, radius: 2.3, top: 3.2, leakDir: { x: 0.3, y: 0.85, z: 0.4 } };
}

/** Château dims: from params, else from explicit colliders (world space), else defaults. */
function chateauDims(def) {
  const p = def.params || {};
  const pos = def.pos || [0, 0, 0];
  let top = Number.isFinite(p.height) ? p.height : null;
  let tankR = Number.isFinite(p.tankRadius) ? p.tankRadius : null;
  let legR = Number.isFinite(p.legSpread) ? p.legSpread : null;
  if (Array.isArray(def.colliders) && def.colliders.length) {
    let maxY = -Infinity, maxR = 0, foot = 0;
    for (const c of def.colliders) {
      if (c.type === 'cyl') {
        maxY = Math.max(maxY, c.y1 - pos[1]);
        if (c.y0 - pos[1] > 2) maxR = Math.max(maxR, c.r);
        foot = Math.max(foot, Math.hypot(c.c[0] - pos[0], c.c[1] - pos[2]) + c.r);
      } else if (c.type === 'box' && c.min && c.max) {
        maxY = Math.max(maxY, c.max[1] - pos[1]);
        const hx = (c.max[0] - c.min[0]) / 2, hz = (c.max[2] - c.min[2]) / 2;
        if (c.min[1] - pos[1] > 2) maxR = Math.max(maxR, Math.max(hx, hz));
        foot = Math.max(foot, Math.max(Math.abs(c.max[0] - pos[0]), Math.abs(c.min[0] - pos[0]), Math.abs(c.max[2] - pos[2]), Math.abs(c.min[2] - pos[2])));
      }
    }
    if (top === null && Number.isFinite(maxY) && maxY > 3) top = maxY;
    if (tankR === null && maxR > 0.5) tankR = maxR;
    if (legR === null && foot > 0.5) legR = Math.min(foot, (tankR || 2.4) * 0.9);
  }
  top = top ?? 12;
  tankR = tankR ?? 2.4;
  legR = legR ?? tankR * 0.75;
  const tankH = Math.min(tankR * 1.5, top * 0.35);
  return { top, tankR, legR, tankH, tankBottom: top - tankH };
}

function buildChateau(kit, def) {
  const d = chateauDims(def);
  const parts = [];
  const legs = 4;
  for (let i = 0; i < legs; i++) {
    const a = Math.PI / 4 + i * Math.PI / 2;
    const bx = Math.cos(a) * d.legR, bz = Math.sin(a) * d.legR;
    const tx = Math.cos(a) * d.tankR * 0.6, tz = Math.sin(a) * d.tankR * 0.6;
    parts.push(cylBetween(bx, 0, bz, tx, d.tankBottom + 0.1, tz, 0.2, 8, PALETTE.CONCRETE, 0.16));
    parts.push(cylGeom(0.32, 0.36, 0.3, 8, bx, 0, bz, PALETTE.CONCRETE_DARK));
  }
  // ring beams
  for (const t of [0.33, 0.66]) {
    const y = d.tankBottom * t;
    const r = d.legR + (d.tankR * 0.6 - d.legR) * t;
    const ring = prepStatic(new THREE.TorusGeometry(r, 0.09, 5, 20), PALETTE.CONCRETE_DARK);
    parts.push(tf(ring, 0, y, 0, 0, 1, 1, 1, Math.PI / 2, 0));
  }
  // central riser pipe
  parts.push(cylGeom(0.18, 0.18, d.tankBottom, 10, 0, 0, 0, PALETTE.PIPE));
  // tank (lathe "bulb"), white with a blue band
  const R = d.tankR, H = d.tankH, b = d.tankBottom;
  const profile = [[0, b - 0.25], [R * 0.55, b - 0.2], [R * 0.92, b + H * 0.12], [R, b + H * 0.35], [R, b + H * 0.75], [R * 0.9, b + H * 0.92],
    [R * 0.45, b + H * 1.02], [0.2, b + H * 1.06], [0, b + H * 1.07]];
  const tank = latheGeom(profile, 24, 0xf3f1ec);
  const white = new THREE.Color().setHex(0xf3f1ec), blue = new THREE.Color().setHex(PALETTE.HYDRIA_BLUE), under = new THREE.Color().setHex(PALETTE.CONCRETE_DARK);
  paintVertices(tank, (o, x, y) => {
    if (y < b + H * 0.1) o.copy(under);
    else if (y > b + H * 0.42 && y < b + H * 0.6) o.copy(blue);
    else o.copy(white);
  });
  parts.push(tank);
  // gallery around the tank
  const gal = prepStatic(new THREE.TorusGeometry(R + 0.35, 0.05, 4, 32), PALETTE.METAL_DARK);
  parts.push(tf(gal, 0, b + H * 0.2 + 0.9, 0, 0, 1, 1, 1, Math.PI / 2, 0));
  parts.push(cylGeom(R + 0.45, R + 0.45, 0.1, 32, 0, b + H * 0.2, 0, PALETTE.METAL));
  // ladder on the +z side
  const lz = d.legR * 0.85;
  for (const lx of [-0.22, 0.22]) parts.push(cylBetween(lx, 0, lz, lx, b + H * 0.2, R * 0.9, 0.035, 5, PALETTE.METAL_DARK));
  const rungs = Math.floor((b + H * 0.2) / 0.35);
  for (let i = 1; i < rungs; i++) {
    const t = i / rungs;
    const y = t * (b + H * 0.2);
    const z = lz + (R * 0.9 - lz) * t;
    parts.push(cylBetween(-0.22, y, z, 0.22, y, z, 0.022, 4, PALETTE.METAL));
  }
  kit.mesh(parts, kit.inner, { outline: true, name: 'chateau' });
  // level gauge on the tank front: track + fill pivot scaled in Y
  const gaugeH = H * 0.6;
  const gy = b + H * 0.2;
  const gz = R + 0.06;
  kit.mesh([roundedBox(0.36, gaugeH + 0.1, 0.06, 0.03, 1, 0, gy + gaugeH / 2, gz, 0x26323d)], kit.inner, { name: 'gaugeTrack', castShadow: false });
  const fillPivot = new THREE.Group();
  fillPivot.position.set(0, gy + 0.05, gz + 0.04);
  kit.inner.add(fillPivot);
  const fillG = boxGeom(0.24, 1, 0.04, 0, 0.5, 0, PALETTE.HYDRIA_CYAN);
  const fill = kit.mesh([fillG], fillPivot, { name: 'gaugeFill', castShadow: false, material: kit.mats ? kit.mats.lamp(PALETTE.HYDRIA_CYAN) : undefined });
  fillPivot.scale.set(1, 0.001, 1);
  const lampMesh = kit.lamp(0, b + H * 1.07 + 0.2, 0, 0.14);
  const overflow = new THREE.Object3D(); overflow.position.set(R * 0.7, b + H * 0.95, R * 0.4); kit.inner.add(overflow);
  const leak = new THREE.Object3D(); leak.position.set(0.18, d.tankBottom * 0.5, 0); kit.inner.add(leak);
  return { lampMesh, fillPivot, gaugeH: gaugeH - 0.1, fill, overflow, leak, radius: Math.max(d.legR + 0.5, 1.5), top: b + H + 0.5,
    leakDir: { x: 1, y: 0.2, z: 0.2 } };
}

// ---------------------------------------------------------------------------------------------
// createOuvrageView
// ---------------------------------------------------------------------------------------------

/**
 * Ouvrage view (spec §12.5): {object3d, update(dt, time), dispose(), setState(state), setProgress(t|null),
 * setLevel(t) (chateau), pop(), kind, anchor (Object3D at the top, for icons)}.
 */
export function createOuvrageView(def) {
  const kind = def.kind || 'bf';
  const kit = new ViewKit(def, { name: `ouvrage:${def.id || kind}`, noFog: kind === 'chateau' });
  let parts;
  switch (kind) {
    case 'pompe': parts = buildPompe(kit); break;
    case 'kiosque': parts = buildKiosque(kit, def); break;
    case 'station': parts = buildStation(kit); break;
    case 'chateau': parts = buildChateau(kit, def); break;
    default: parts = buildBf(kit);
  }
  const anchor = new THREE.Object3D();
  anchor.position.set(0, parts.top, 0);
  kit.root.add(anchor);

  let state = null;
  let jet = null, steam = null, flow = null;
  let flowTimer = 0;
  let sparkTimer = 0;
  let level = 0, levelShown = 0;
  let progress = null;
  let handleAngle = 0;
  let t = 0;

  const stopFx = () => {
    if (jet) { jet.stop(); jet = null; }
    if (steam) { steam.stop(); steam = null; }
  };

  const view = {
    object3d: kit.root,
    kind,
    anchor,
    get state() { return state; },
    setState(s) {
      if (s === state) return;
      const prev = state;
      state = s;
      const hex = STATE_COLORS[s] ?? STATE_COLORS.healthy;
      kit.setLamp(parts.lampMesh, hex);
      stopFx();
      if (s === 'broken') {
        if (parts.leak) jet = kit.continuous('jet', parts.leak, { dir: parts.leakDir || { x: 0.6, y: 0.7, z: 0 }, rate: kind === 'bf' ? 42 : 30 });
        if (kind === 'pompe' && parts.steam) steam = kit.continuous('steam', parts.steam, { rate: 5 });
        if (kind === 'station' || kind === 'chateau') steam = kit.continuous('steam', parts.leak || anchor, { rate: 4 });
      }
      if (s === 'healthy' && prev && prev !== 'healthy') {
        kit.halo(parts.radius + 0.4);
        kit.burst('sparkle', [0, parts.top * 0.6, 0], { count: 18 });
        flowTimer = 2.2;
        kit.pop(1);
      }
    },
    setProgress(tt) {
      progress = (tt === null || tt === undefined) ? null : clamp(tt, 0, 1);
      kit.setProgress(progress, parts.radius + 0.25);
    },
    setLevel(tt) {
      level = clamp(Number(tt) || 0, 0, 1);
    },
    pop() { kit.pop(1); },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      kit.updateKit(dt);
      // lamp blink when broken
      if (parts.lampMesh) {
        const blink = state === 'broken' ? (Math.sin(t * 9) > 0 ? 1.15 : 0.85) : (state === 'repairing' ? 1 + 0.12 * Math.sin(t * 6) : 1);
        parts.lampMesh.scale.setScalar(blink);
      }
      // healthy pour after a repair
      if (flowTimer > 0) {
        flowTimer -= dt;
        if (!flow && parts.nozzle) flow = kit.continuous('jet', parts.nozzle, { dir: { x: 0, y: -1, z: 0.05 }, rate: 28, speed: 0.35 });
        if (flowTimer <= 0 && flow) { flow.stop(); flow = null; }
      }
      // pompe handle: droops when broken, wiggles when repairing, pumps after repair, rests otherwise
      if (parts.handlePivot) {
        let target = 0.18;
        if (state === 'broken') target = -0.55;
        else if (state === 'repairing') target = -0.1 + Math.sin(t * 10) * 0.12;
        else if (flowTimer > 0) target = 0.1 + Math.sin(t * 7) * 0.35;
        handleAngle += (target - handleAngle) * (1 - Math.exp(-dt * 10));
        parts.handlePivot.rotation.x = handleAngle;
        parts.handlePivot.rotation.z = state === 'broken' ? 0.12 : 0;
      }
      // sparks from electrical parts while broken / repairing
      if ((state === 'broken' || (state === 'repairing' && progress !== null)) && parts.sparks) {
        sparkTimer -= dt;
        if (sparkTimer <= 0) {
          sparkTimer = state === 'broken' ? 0.6 + Math.random() * 0.8 : 0.35;
          kit.burst('sparkle', [parts.sparks.position.x, parts.sparks.position.y, parts.sparks.position.z],
            { count: 7, colors: [0xffd166, 0xff9f43, 0xffffff], speed: 0.8 });
        }
      }
      if (state === 'repairing' && progress !== null && kind !== 'kiosque' && kind !== 'station') {
        sparkTimer -= dt;
        if (sparkTimer <= 0) { sparkTimer = 0.4; kit.burst('sparkle', [0, parts.top * 0.5, 0.3], { count: 4, colors: [0xffd166, 0xffffff], speed: 0.6 }); }
      }
      // château level gauge
      if (parts.fillPivot) {
        levelShown += (level - levelShown) * (1 - Math.exp(-dt * 3));
        parts.fillPivot.scale.y = Math.max(0.001, levelShown * parts.gaugeH);
      }
    },
    dispose() {
      stopFx();
      if (flow) { flow.stop(); flow = null; }
      kit.dispose();
    },
  };
  if (kind === 'chateau' && def.params && Number.isFinite(def.params.level)) view.setLevel(def.params.level);
  view.setState(def.state || 'healthy');
  return view;
}

// ---------------------------------------------------------------------------------------------
// createValveView
// ---------------------------------------------------------------------------------------------

/** Valve (vanne) view: {object3d, update, dispose, setProgress(t|null), setOpen(), anchor}. */
export function createValveView(def) {
  const kit = new ViewKit(def, { name: `valve:${def.id || ''}` });
  const parts = [];
  parts.push(apron(0.3, 0.1, PALETTE.CONCRETE));
  parts.push(cylGeom(0.075, 0.08, 0.55, 10, 0, 0.1, 0, PALETTE.PIPE));
  parts.push(tf(cylGeom(0.13, 0.13, 0.36, 12, 0, -0.18, 0, PALETTE.PIPE_DARK), 0, 0.5, 0, 0, 1, 1, 1, 0, Math.PI / 2));
  for (const x of [-0.2, 0.2]) parts.push(tf(cylGeom(0.17, 0.17, 0.05, 12, 0, -0.025, 0, PALETTE.PIPE_DARK), x, 0.5, 0, 0, 1, 1, 1, 0, Math.PI / 2));
  parts.push(cylGeom(0.04, 0.04, 0.3, 8, 0, 0.6, 0, PALETTE.METAL));
  kit.mesh(parts, kit.inner, { outline: true, name: 'valveBody' });
  const wheelPivot = new THREE.Group();
  wheelPivot.position.set(0, 0.9, 0);
  kit.inner.add(wheelPivot);
  const wheelParts = [];
  wheelParts.push(tf(prepStatic(new THREE.TorusGeometry(0.2, 0.03, 6, 20), 0xffffff), 0, 0, 0, 0, 1, 1, 1, Math.PI / 2, 0));
  for (let i = 0; i < 4; i++) {
    const a = i * Math.PI / 2;
    wheelParts.push(cylBetween(0, 0, 0, Math.cos(a) * 0.2, 0, Math.sin(a) * 0.2, 0.018, 5, 0xffffff));
  }
  wheelParts.push(cylGeom(0.05, 0.05, 0.06, 10, 0, -0.03, 0, 0xffffff));
  const wheelGeom = mergeStatic(wheelParts);
  // The wheel colour changes with the state: use the shared lamp-family materials? No — keep it lit (toon)
  // and swap between two vertex-coloured copies.
  const red = wheelGeom.clone();
  paintVertices(red, (o) => { o.setHex(0xd93b3b); });
  const green = wheelGeom.clone();
  paintVertices(green, (o) => { o.setHex(0x22a85a); });
  wheelGeom.dispose();
  const wheel = kit.mesh([red], wheelPivot, { outline: true, name: 'wheel' });
  kit._geoms.push(green);
  const anchor = new THREE.Object3D(); anchor.position.set(0, 1.25, 0); kit.root.add(anchor);
  const spout = new THREE.Object3D(); spout.position.set(0.24, 0.5, 0); kit.inner.add(spout);
  let open = false, angle = 0, targetAngle = 0, progress = null, gushTimer = 0, gush = null;
  return {
    object3d: kit.root,
    anchor,
    get open() { return open; },
    setProgress(t) {
      progress = (t === null || t === undefined) ? null : clamp(t, 0, 1);
      kit.setProgress(progress, 0.55);
      if (progress !== null) targetAngle = -progress * Math.PI * 4;
    },
    setOpen() {
      if (open) return;
      open = true;
      targetAngle = -Math.PI * 4;
      if (wheel) wheel.geometry = green;
      kit.halo(0.9, PALETTE.HYDRIA_CYAN);
      kit.burst('splash', [0.25, 0.55, 0], { count: 14, dir: { x: 1, y: 1, z: 0 } });
      gushTimer = 1.5;
      kit.pop(0.8);
    },
    update(dt) {
      kit.updateKit(dt);
      angle += (targetAngle - angle) * (1 - Math.exp(-dt * 8));
      wheelPivot.rotation.y = angle;
      if (gushTimer > 0) {
        gushTimer -= dt;
        if (!gush) gush = kit.continuous('jet', spout, { dir: { x: 1, y: 0.4, z: 0 }, rate: 30, speed: 0.6 });
        if (gushTimer <= 0 && gush) { gush.stop(); gush = null; }
      }
    },
    dispose() {
      if (gush) gush.stop();
      if (wheel) wheel.geometry = red;
      kit.dispose();
    },
  };
}

// ---------------------------------------------------------------------------------------------
// createUsagerView
// ---------------------------------------------------------------------------------------------

function buildMeterPost(kit, branchement) {
  const parts = [];
  const base = roundedBox(0.34, 0.1, 0.34, 0.03, 1, 0, 0.05, 0, PALETTE.CONCRETE);
  parts.push(base);
  parts.push(roundedBox(0.16, 0.78, 0.16, 0.03, 1, 0, 0.49, 0, 0xf3f1ec));
  // meter box (Hydria blue) with a dial
  parts.push(roundedBox(0.26, 0.2, 0.14, 0.03, 1, 0, 0.62, 0.06, PALETTE.HYDRIA_BLUE));
  parts.push(tf(cylGeom(0.06, 0.06, 0.02, 12, 0, 0, 0, 0xffffff), 0, 0.62, 0.135, 0, 1, 1, 1, Math.PI / 2, 0));
  if (branchement !== 'kiosque') {
    // tap + small bucket
    parts.push(cylBetween(0, 0.36, 0.08, 0, 0.36, 0.22, 0.025, 6, PALETTE.METAL));
    parts.push(cylGeom(0.022, 0.022, 0.07, 6, 0, 0.29, 0.22, PALETTE.METAL));
    const bucket = latheGeom([[0, 0.1], [0.12, 0.1], [0.14, 0.3], [0.13, 0.3], [0.11, 0.12], [0, 0.12]], 10, branchement === 'BI' ? PALETTE.JERRYCAN_YELLOW : 0x2fb5a3);
    parts.push(tf(bucket, 0, 0, 0.26));
  }
  return parts;
}

/** Usager view: character + water-meter post with state lamp. {setState, setProgress, cheer, character, anchor}. */
export function createUsagerView(def) {
  const kit = new ViewKit(def, { name: `usager:${def.id || ''}` });
  const engine = kit.engine;
  const variant = Number.isFinite(def.variant) ? def.variant : (hashString(def.id || def.name || 'u') % 8);
  const character = createCharacter('usager', { variant, tier: engine ? engine.tier : undefined });
  kit.inner.add(character.object3d);
  if (kit.mats) for (const m of [character.bodyMesh, character.headMesh]) if (m) kit._outlines.push(kit.mats.addOutline(m));
  // meter post beside the usager (to their left, slightly behind)
  const post = new THREE.Group();
  post.position.set(0.72, 0, -0.15);
  post.rotation.y = -0.35;
  kit.inner.add(post);
  kit.mesh(buildMeterPost(kit, def.branchement || 'BP'), post, { outline: true, name: 'meter' });
  const lampMesh = kit.lamp(0, 0.95, 0, 0.065, post);
  const tap = new THREE.Object3D(); tap.position.set(0, 0.27, 0.22); post.add(tap);
  const anchor = new THREE.Object3D(); anchor.position.set(0, 1.5, 0); kit.root.add(anchor);
  // static blob shadow under the usager
  let blob = null;
  if (engine && engine.fx && engine.fx.blobs) {
    blob = engine.fx.blobs.add();
    const p = def.pos || [0, 0, 0];
    blob.set(p[0], p[1], p[2], 0);
    kit.onDispose(() => blob.remove());
  }
  const rng = makeRng(hashString(def.id || 'usager'));
  let state = null, cheerTimer = 0, flowTimer = 0, flow = null, waveTimer = rng.range(1, 4);
  let t = 0;

  const poseFor = () => {
    if (cheerTimer > 0) return 'cheer';
    switch (state) {
      case 'due': return waveTimer < 1.4 ? 'wave' : 'idle';
      case 'overdue': return 'talk';
      case 'cut_off': return 'sad';
      default: return 'idle';
    }
  };

  const view = {
    object3d: kit.root,
    character,
    anchor,
    get state() { return state; },
    setState(s) {
      if (s === state) return;
      const prev = state;
      state = s;
      kit.setLamp(lampMesh, STATE_COLORS[s] ?? STATE_COLORS.due);
      if (s === 'paid' && prev) { cheerTimer = 1.6; kit.burst('coins', [0, 1.2, 0.2], { count: 8 }); }
      if (prev === 'restore_pending' && s !== 'restore_pending') flowTimer = 1.8;
      if (prev === 'cut_off' && s === 'paid') flowTimer = 0;
      if (prev) kit.pop(0.6);
    },
    setProgress(tt) {
      kit.setProgress((tt === null || tt === undefined) ? null : clamp(tt, 0, 1), 1.05);
    },
    cheer() {
      cheerTimer = 1.6;
      kit.burst('confetti', [0, 1.3, 0], { count: 16 });
    },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      kit.updateKit(dt);
      if (cheerTimer > 0) cheerTimer -= dt;
      waveTimer -= dt;
      if (waveTimer < 0) waveTimer = rng.range(3.5, 6);
      character.setPose(poseFor(), 0);
      character.update(dt);
      if (lampMesh) lampMesh.scale.setScalar(state === 'overdue' || state === 'cut_off' ? (Math.sin(t * 8) > 0 ? 1.15 : 0.85) : 1);
      if (flowTimer > 0) {
        flowTimer -= dt;
        if (!flow) flow = kit.continuous('jet', tap, { dir: { x: 0, y: -1, z: 0.1 }, rate: 24, speed: 0.3 });
        if (flowTimer <= 0 && flow) { flow.stop(); flow = null; }
      }
    },
    dispose() {
      if (flow) flow.stop();
      character.dispose();
      kit.dispose();
    },
  };
  view.setState(def.state || 'due');
  return view;
}

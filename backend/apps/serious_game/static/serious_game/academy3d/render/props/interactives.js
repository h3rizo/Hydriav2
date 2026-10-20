// render/props/interactives.js — mover, block, jump pad, checkpoint, goal, collectible field and NPC views (spec §12.5).
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';
import {
  boxGeom, roundedBox, cylGeom, sphereGeom, latheGeom, prepStatic, tf, mergeStatic, paintVertices, paintTriangles,
  hashString, makeRng,
} from 'a3d/render/geometry.js';
import { buildPlatformGeometry, buildLocalBox } from 'a3d/render/props/platforms.js';
import { ViewKit } from 'a3d/render/props/infra.js';
import { createCharacter } from 'a3d/actors/characters.js';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const _m4 = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();
const _e = new THREE.Euler();

// ---------------------------------------------------------------------------------------------
// Mover
// ---------------------------------------------------------------------------------------------

function raftGeometry(size) {
  const [sx, sy, sz] = size;
  const longX = sx >= sz;
  const len = longX ? sx : sz, wid = longX ? sz : sx;
  const r = clamp(sy / 2, 0.1, 0.22);
  const n = Math.max(2, Math.round(wid / (r * 2)));
  const step = wid / n;
  const parts = [];
  const top = sy / 2;
  for (let i = 0; i < n; i++) {
    const c = -wid / 2 + step * (i + 0.5);
    const log = prepStatic(new THREE.CylinderGeometry(r * 0.98, r, len * (0.96 + (i % 2) * 0.04), 8, 1), PALETTE.WOOD);
    const a = new THREE.Color().setHex(PALETTE.WOOD), b = new THREE.Color().setHex(PALETTE.WOOD_LIGHT), e = new THREE.Color().setHex(PALETTE.WOOD_DARK);
    paintVertices(log, (o, x, y, z, nx, ny) => { o.copy(Math.abs(ny) > 0.7 ? b : (i % 2 ? a : e)); });
    if (longX) { log.rotateZ(Math.PI / 2); log.translate(0, top - r, c); } else { log.rotateX(Math.PI / 2); log.translate(c, top - r, 0); }
    parts.push(log);
  }
  // rope bands + under ties
  for (const t of [-0.32, 0.32]) {
    const along = t * len;
    if (longX) {
      parts.push(boxGeom(0.08, r * 2 + 0.02, wid + 0.02, along, top - r, 0, 0xd9c08a));
      parts.push(boxGeom(0.14, 0.08, wid + 0.1, along, top - 2 * r - 0.03, 0, PALETTE.WOOD_DARK));
    } else {
      parts.push(boxGeom(wid + 0.02, r * 2 + 0.02, 0.08, 0, top - r, along, 0xd9c08a));
      parts.push(boxGeom(wid + 0.1, 0.08, 0.14, 0, top - 2 * r - 0.03, along, PALETTE.WOOD_DARK));
    }
  }
  return mergeStatic(parts);
}

/** Mover view: object3d positioned by P4 at the box centre. */
export function createMoverView(def) {
  const kit = new ViewKit(def, { name: `mover:${def.id || ''}`, place: false });
  const size = def.size || [2, 0.4, 2];
  const style = def.style || 'wood';
  const isRaft = style === 'wood' && size[1] <= 0.7;
  const geom = isRaft ? raftGeometry(size) : buildLocalBox(size, style, { lowDetail: kit.engine ? kit.engine.tier === 'low' : false });
  const mesh = kit.mesh([geom], kit.inner, { name: 'mover', receiveShadow: true });
  const phase = hashString(def.id || 'm') % 100;
  return {
    object3d: kit.root,
    mesh,
    update(dt, time) {
      kit.updateKit(dt);
      if (isRaft) {
        const t = (Number.isFinite(time) ? time : 0) + phase;
        kit.inner.rotation.x = Math.sin(t * 1.3) * 0.02;
        kit.inner.rotation.z = Math.sin(t * 1.1 + 1) * 0.025;
      }
    },
    dispose() { kit.dispose(); },
  };
}

// ---------------------------------------------------------------------------------------------
// Block (toggleable solid, incl. help bridges)
// ---------------------------------------------------------------------------------------------

/** Block view: geometry in world space; setT(t) offsets by offsetHidden·(1−t); setVisible(b). */
export function createBlockView(def) {
  const kit = new ViewKit(def, { name: `block:${def.id || ''}`, place: false });
  const style = def.style || 'wood';
  const ctx = { lowDetail: kit.engine ? kit.engine.tier === 'low' : false };
  const geoms = [];
  for (const s of def.shapes || []) {
    if (s.type === 'ramp') geoms.push(...buildPlatformGeometry({ type: 'ramp', min: s.min, max: s.max, up: s.up, thickness: s.thickness ?? 0.4, style }, ctx));
    else geoms.push(...buildPlatformGeometry({ type: 'box', min: s.min, max: s.max, style }, ctx));
  }
  kit.mesh(geoms, kit.inner, { name: 'block', receiveShadow: true });
  const off = def.offsetHidden || [0, -1.5, 0];
  // centre of the shapes, for effects
  const c = [0, 0, 0];
  let n = 0;
  for (const s of def.shapes || []) {
    c[0] += (s.min[0] + s.max[0]) / 2; c[1] += s.max[1]; c[2] += (s.min[2] + s.max[2]) / 2; n++;
  }
  if (n) { c[0] /= n; c[1] /= n; c[2] /= n; }
  let t = def.solidAtStart ? 1 : 0;
  const apply = () => {
    const k = 1 - t;
    kit.root.position.set(off[0] * k, off[1] * k, off[2] * k);
  };
  apply();
  kit.root.visible = !!def.solidAtStart;
  return {
    object3d: kit.root,
    setT(v) {
      const nt = clamp(Number(v) || 0, 0, 1);
      if (t === 0 && nt > 0 && kit.engine) {
        kit.engine.fx.particles.emit('sparkle', c, { count: 16, colors: [PALETTE.HYDRIA_CYAN, 0xffffff] });
      }
      t = nt;
      apply();
    },
    setVisible(b) { kit.root.visible = !!b; },
    update(dt) { kit.updateKit(dt); },
    dispose() { kit.dispose(); },
  };
}

// ---------------------------------------------------------------------------------------------
// Jump pad
// ---------------------------------------------------------------------------------------------

/** Jump pad view: {fire()}. Chevrons point toward def.target. */
export function createJumpPadView(def) {
  const kit = new ViewKit({ pos: def.pos, yaw: 0 }, { name: `pad:${def.id || ''}` });
  const r = def.r || 0.8;
  const pos = def.pos || [0, 0, 0];
  const tgt = def.target || [pos[0], pos[1], pos[2] + 1];
  const yaw = Math.atan2(tgt[0] - pos[0], tgt[2] - pos[2]);
  kit.inner.rotation.y = yaw;
  const base = [];
  base.push(cylGeom(r + 0.12, r + 0.18, 0.08, 24, 0, 0, 0, PALETTE.CONCRETE_DARK));
  // spring coil
  const coil = prepStatic(new THREE.TorusGeometry(r * 0.55, 0.035, 5, 20), PALETTE.METAL);
  for (let i = 0; i < 2; i++) base.push(tf(coil.clone(), 0, 0.1 + i * 0.05, 0, 0, 1, 1, 1, Math.PI / 2, 0));
  coil.dispose();
  kit.mesh(base, kit.inner, { name: 'padBase', receiveShadow: true });
  const top = new THREE.Group();
  top.position.y = 0.12;
  kit.inner.add(top);
  const disc = cylGeom(r, r, 0.07, 28, 0, 0, 0, PALETTE.HYDRIA_BLUE);
  paintTriangles(disc, (o, f) => { o.setHex(f.ny > 0.5 ? PALETTE.HYDRIA_BLUE_LIGHT : PALETTE.HYDRIA_BLUE_DARK); });
  const rim = cylGeom(r + 0.04, r + 0.04, 0.05, 28, 0, 0.03, 0, PALETTE.HYDRIA_CYAN);
  kit.mesh([disc, rim], top, { name: 'padTop', outline: true });
  // chevrons (unlit, bright)
  const chev = [];
  for (let i = 0; i < 3; i++) {
    const z = -r * 0.45 + i * r * 0.38;
    for (const side of [1, -1]) {
      const g = boxGeom(r * 0.42, 0.02, 0.09, 0, 0, 0, PALETTE.HYDRIA_YELLOW);
      tf(g, side * r * 0.14, 0.085, z, side * 0.75);
      chev.push(g);
    }
  }
  const chevMesh = kit.mesh(chev, top, { name: 'chevrons', castShadow: false, material: kit.mats ? kit.mats.lamp(PALETTE.HYDRIA_YELLOW) : undefined });
  let fireT = 1;
  let t = 0;
  return {
    object3d: kit.root,
    fire() {
      fireT = 0;
      kit.halo(r + 0.3, PALETTE.HYDRIA_CYAN);
      kit.burst('sparkle', [0, 0.25, 0], { count: 16 });
      kit.burst('dust', [0, 0.1, 0], { count: 8 });
    },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      kit.updateKit(dt);
      if (fireT < 1) fireT = Math.min(1, fireT + dt / 0.45);
      // compress fast then overshoot and settle
      const ft = fireT;
      const squash = ft < 0.18 ? -0.6 * (ft / 0.18) : -0.6 * Math.exp(-(ft - 0.18) * 9) * Math.cos((ft - 0.18) * 26);
      top.scale.set(1 - squash * 0.15, 1 + squash, 1 - squash * 0.15);
      top.position.y = 0.12 + squash * 0.05;
      if (chevMesh) {
        const pulse = 0.5 + 0.5 * Math.sin(t * 5);
        chevMesh.position.z = pulse * 0.06;
      }
    },
    dispose() { kit.dispose(); },
  };
}

// ---------------------------------------------------------------------------------------------
// Checkpoint
// ---------------------------------------------------------------------------------------------

function flagSegment(w, h, hex, emblem) {
  const parts = [boxGeom(w, h, 0.025, w / 2, 0, 0, hex)];
  if (emblem) parts.push(sphereGeom(0.07, 8, 6, w * 0.5, 0, 0.02, PALETTE.HYDRIA_CYAN, 1, 1.3, 0.3), sphereGeom(0.07, 8, 6, w * 0.5, 0, -0.02, PALETTE.HYDRIA_CYAN, 1, 1.3, 0.3));
  return mergeStatic(parts);
}

/** Checkpoint flag: {activate()}. */
export function createCheckpointView(def) {
  const kit = new ViewKit(def, { name: `checkpoint:${def.id || ''}` });
  const base = [];
  base.push(cylGeom(0.55, 0.62, 0.08, 18, 0, 0, 0, PALETTE.ROCK));
  base.push(cylGeom(0.38, 0.4, 0.05, 18, 0, 0.08, 0, PALETTE.CONCRETE_LIGHT));
  base.push(cylGeom(0.04, 0.05, 1.9, 8, 0, 0.1, 0, 0xf4f1ea));
  base.push(sphereGeom(0.07, 8, 6, 0, 2.03, 0, PALETTE.HYDRIA_YELLOW));
  kit.mesh(base, kit.inner, { name: 'cpBase', outline: true });
  const segW = 0.24, segH = 0.42;
  const flagRoot = new THREE.Group();
  flagRoot.position.set(0.03, 1.15, 0);
  kit.inner.add(flagRoot);
  const greyA = flagSegment(segW, segH, 0xd6dbe0, false), greyB = flagSegment(segW, segH, 0xc4cad1, false), greyC = flagSegment(segW, segH, 0xd6dbe0, false);
  const blueA = flagSegment(segW, segH, PALETTE.HYDRIA_BLUE, false), blueB = flagSegment(segW, segH, PALETTE.HYDRIA_BLUE, true), blueC = flagSegment(segW, segH, PALETTE.HYDRIA_BLUE_DARK, false);
  kit._geoms.push(blueA, blueB, blueC);
  const segs = [];
  let parent = flagRoot;
  for (const g of [greyA, greyB, greyC]) {
    const pivot = new THREE.Group();
    if (segs.length) pivot.position.x = segW;
    parent.add(pivot);
    const m = kit.mesh([g], pivot, { name: 'flag', castShadow: true });
    segs.push({ pivot, mesh: m });
    parent = pivot;
  }
  let active = false, raise = 0, t = 0;
  return {
    object3d: kit.root,
    get active() { return active; },
    activate() {
      if (active) return;
      active = true;
      segs[0].mesh.geometry = blueA; segs[1].mesh.geometry = blueB; segs[2].mesh.geometry = blueC;
      kit.halo(1.1, PALETTE.HYDRIA_CYAN);
      kit.burst('confetti', [0, 2.0, 0], { count: 28 });
      kit.burst('sparkle', [0, 1.2, 0], { count: 14 });
      kit.pop(0.7);
    },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      kit.updateKit(dt);
      const target = active ? 1 : 0;
      raise += (target - raise) * (1 - Math.exp(-dt * 4));
      flagRoot.position.y = 1.15 + raise * 0.6;
      const amp = 0.18 + raise * 0.12;
      for (let i = 0; i < segs.length; i++) segs[i].pivot.rotation.y = Math.sin(t * 4.2 - i * 0.9) * amp * (i === 0 ? 0.5 : 1);
    },
    dispose() {
      segs[0].mesh.geometry = greyA; segs[1].mesh.geometry = greyB; segs[2].mesh.geometry = greyC;
      kit.dispose();
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Goal
// ---------------------------------------------------------------------------------------------

/** Teardrop goutte geometry (tip up), height ≈ 1 at scale 1, base at y = 0. */
export function dropletGeometry(segments = 14, hex = PALETTE.HYDRIA_CYAN) {
  const prof = [];
  const n = 12;
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI;              // 0 = bottom, PI = top
    const y = 0.5 - 0.5 * Math.cos(a);        // 0..1
    const bulge = Math.sin(a) * (1 - 0.55 * (y > 0.5 ? (y - 0.5) * 2 : 0));
    const r = 0.36 * Math.pow(Math.max(0, bulge), 0.9) * (y > 0.55 ? 1 - (y - 0.55) * 1.2 : 1);
    prof.push([Math.max(0, r), y * 1.0]);
  }
  prof[prof.length - 1][0] = 0;
  const g = latheGeom(prof, segments, hex);
  const low = new THREE.Color().setHex(PALETTE.HYDRIA_BLUE), high = new THREE.Color().setHex(0xc9f6ff);
  paintVertices(g, (o, x, y, z) => { o.copy(low).lerp(high, clamp(y * 0.9 + (x + z) * 0.25, 0, 1)); });
  return g;
}

/** Goal: floating Hydria goutte on a pedestal; {setActive(b), celebrate()}. */
export function createGoalView(def) {
  const kit = new ViewKit({ pos: def.pos, yaw: 0 }, { name: `goal:${def.id || 'goal'}` });
  const ped = [];
  ped.push(cylGeom(1.45, 1.55, 0.1, 32, 0, 0, 0, PALETTE.CONCRETE_LIGHT));
  ped.push(cylGeom(1.15, 1.15, 0.03, 32, 0, 0.1, 0, PALETTE.HYDRIA_BLUE));
  ped.push(cylGeom(0.9, 0.9, 0.035, 32, 0, 0.11, 0, 0xf4f1ea));
  // small flags around
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    const x = Math.cos(a) * 1.75, z = Math.sin(a) * 1.75;
    ped.push(cylGeom(0.03, 0.03, 1.1, 5, x, 0, z, 0xf4f1ea));
    ped.push(tf(boxGeom(0.3, 0.2, 0.02, 0.15, 0, 0, PALETTE.CONFETTI[i % PALETTE.CONFETTI.length]), x, 0.98, z, -a));
  }
  kit.mesh(ped, kit.inner, { name: 'goalBase', receiveShadow: true });
  const dropPivot = new THREE.Group();
  dropPivot.position.y = 1.0;
  kit.inner.add(dropPivot);
  const dropG = dropletGeometry(18);
  dropG.translate(0, -0.5, 0);
  const greyG = dropG.clone();
  paintVertices(greyG, (o, x, y) => { o.setHex(y > 0.1 ? 0xc5ccd3 : 0x9aa3ad); });
  kit._geoms.push(dropG, greyG);
  const drop = new THREE.Mesh(greyG, kit.worldMaterial());
  drop.castShadow = true;
  drop.scale.setScalar(0.9);
  dropPivot.add(drop);
  // light column (additive) when active
  const beamG = new THREE.CylinderGeometry(0.55, 0.9, 3.2, 20, 1, true);
  beamG.translate(0, 1.6, 0);
  kit._geoms.push(beamG);
  const beam = new THREE.Mesh(beamG, kit.glowMaterial(PALETTE.HYDRIA_CYAN, 0));
  beam.renderOrder = 18;
  beam.castShadow = false;
  kit.inner.add(beam);
  let active = false, glow = 0, t = 0, celebrateT = 1, sparkleTimer = 0;
  const setDropMaterial = () => {
    if (!kit.mats) return;
    if (active) { drop.geometry = dropG; kit.mats.bind(drop, 'heroGlow'); }
    else { kit.mats.unbind(drop); drop.geometry = greyG; drop.material = kit.worldMaterial(); }
  };
  kit.onDispose(() => { if (kit.mats) kit.mats.unbind(drop); });
  const view = {
    object3d: kit.root,
    get active() { return active; },
    setActive(b) {
      const nb = !!b;
      if (nb === active) return;
      active = nb;
      setDropMaterial();
      if (active) { kit.halo(1.6, PALETTE.HYDRIA_CYAN); kit.pop(0.8); }
    },
    celebrate() {
      celebrateT = 0;
      kit.halo(2.2, PALETTE.HYDRIA_YELLOW);
      kit.burst('confetti', [0, 1.6, 0], { count: 60, speed: 1.2 });
      kit.burst('sparkle', [0, 1.2, 0], { count: 24 });
      kit.pop(1.2);
    },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      kit.updateKit(dt);
      glow += ((active ? 1 : 0) - glow) * (1 - Math.exp(-dt * 3));
      beam.material.opacity = 0.16 * glow * (0.8 + 0.2 * Math.sin(t * 3));
      beam.visible = glow > 0.01;
      const spin = active ? 1.6 : 0.4;
      dropPivot.rotation.y += dt * spin;
      if (celebrateT < 1) celebrateT = Math.min(1, celebrateT + dt / 1.2);
      const jump = celebrateT < 1 ? Math.sin(celebrateT * Math.PI) * 1.2 : 0;
      dropPivot.position.y = 1.0 + Math.sin(t * 2) * 0.12 * (0.5 + glow) + jump;
      const s = 0.9 + 0.25 * glow;
      drop.scale.setScalar(s);
      if (active) {
        sparkleTimer -= dt;
        if (sparkleTimer <= 0) { sparkleTimer = 0.5; kit.burst('sparkle', [0, dropPivot.position.y, 0], { count: 3, speed: 0.6 }); }
      }
    },
    dispose() { kit.dispose(); },
  };
  return view;
}

// ---------------------------------------------------------------------------------------------
// Collectible field (gouttes)
// ---------------------------------------------------------------------------------------------

/** Gouttes as one InstancedMesh: {hide(i), count (total), remaining, isHidden(i)}. */
export function createCollectibleField(positions) {
  const kit = new ViewKit({}, { name: 'gouttes', place: false });
  const list = Array.isArray(positions) ? positions : [];
  const n = list.length;
  const geom = dropletGeometry(kit.engine && kit.engine.tier === 'low' ? 8 : 12);
  geom.translate(0, -0.5, 0);
  geom.scale(0.34, 0.34, 0.34);
  kit._geoms.push(geom);
  const mesh = new THREE.InstancedMesh(geom, kit.mats ? kit.mats.get('heroGlow') : new THREE.MeshToonMaterial({ vertexColors: true }), Math.max(1, n));
  if (kit.mats) kit.mats.bind(mesh, 'heroGlow');
  kit.onDispose(() => { if (kit.mats) kit.mats.unbind(mesh); mesh.dispose(); });
  mesh.count = n;
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  mesh.name = 'gouttes';
  kit.root.add(mesh);
  const phase = new Float32Array(n);
  const hideT = new Float32Array(n).fill(-1);    // -1 visible, 0..1 popping, 2 hidden
  const rng = makeRng(n * 7919 + 13);
  for (let i = 0; i < n; i++) phase[i] = rng() * Math.PI * 2;
  // generous bounding sphere (instances bob a little)
  if (n) {
    const box = new THREE.Box3();
    for (const p of list) box.expandByPoint(_p.set(p[0], p[1], p[2]));
    box.expandByScalar(0.6);
    mesh.boundingSphere = box.getBoundingSphere(new THREE.Sphere());
    mesh.frustumCulled = true;
  }
  let remaining = n;
  let t = 0;
  const writeAll = () => {
    for (let i = 0; i < n; i++) {
      const p = list[i];
      const h = hideT[i];
      let s = 1;
      if (h >= 2) s = 0;
      else if (h >= 0) s = h < 0.35 ? 1 + h * 2 : Math.max(0, 1.7 * (1 - (h - 0.35) / 0.65));
      const spin = t * (h >= 0 ? 9 : 1.8) + phase[i];
      _e.set(0, spin, Math.sin(t * 1.3 + phase[i]) * 0.12, 'YXZ');
      _q.setFromEuler(_e);
      _p.set(p[0], p[1] + Math.sin(t * 2.4 + phase[i]) * 0.08 + (h >= 0 && h < 2 ? h * 0.5 : 0), p[2]);
      _m4.compose(_p, _q, _s.set(s, s, s));
      mesh.setMatrixAt(i, _m4);
    }
    if (n) {
      mesh.instanceMatrix.clearUpdateRanges();
      mesh.instanceMatrix.addUpdateRange(0, n * 16);
      mesh.instanceMatrix.needsUpdate = true;
    }
  };
  writeAll();
  return {
    object3d: kit.root,
    mesh,
    count: n,
    get remaining() { return remaining; },
    isHidden(i) { return i >= 0 && i < n && hideT[i] >= 0; },
    hide(i) {
      if (!(i >= 0 && i < n) || hideT[i] >= 0) return;
      hideT[i] = 0;
      remaining--;
      if (kit.engine) kit.engine.fx.particles.emit('sparkle', list[i], { count: 10 });
    },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      for (let i = 0; i < n; i++) {
        if (hideT[i] >= 0 && hideT[i] < 2) {
          hideT[i] += dt / 0.3;
          if (hideT[i] >= 1) hideT[i] = 2;
        }
      }
      writeAll();
    },
    dispose() { kit.dispose(); },
  };
}

// ---------------------------------------------------------------------------------------------
// NPC
// ---------------------------------------------------------------------------------------------

/** NPC view (cheffe, magasinier, caissière): {setTalking(b), character, anchor}. */
export function createNpcView(def) {
  const kit = new ViewKit(def, { name: `npc:${def.id || ''}` });
  const engine = kit.engine;
  const variant = Number.isFinite(def.variant) ? def.variant : (hashString(def.id || def.name || 'n') % 8);
  const character = createCharacter('npc', { variant, role: def.role, tier: engine ? engine.tier : undefined });
  kit.inner.add(character.object3d);
  if (kit.mats) for (const m of [character.bodyMesh, character.headMesh]) if (m) kit._outlines.push(kit.mats.addOutline(m));
  // small role prop beside the NPC (low, to the side)
  const prop = [];
  if (def.role === 'magasinier') {
    prop.push(roundedBox(0.45, 0.4, 0.4, 0.03, 1, 0.75, 0.2, -0.25, PALETTE.CARDBOARD));
    prop.push(roundedBox(0.36, 0.3, 0.34, 0.03, 1, 0.78, 0.55, -0.25, PALETTE.CARDBOARD));
    prop.push(boxGeom(0.08, 0.08, 0.01, 0.78, 0.6, -0.075, PALETTE.HYDRIA_BLUE));
  } else if (def.role === 'caissiere') {
    prop.push(cylGeom(0.2, 0.22, 0.5, 10, 0.72, 0, -0.1, PALETTE.WOOD_DARK));
    prop.push(roundedBox(0.3, 0.16, 0.22, 0.03, 1, 0.72, 0.58, -0.1, 0x3c4a5a));
    prop.push(boxGeom(0.16, 0.02, 0.1, 0.72, 0.67, -0.1, PALETTE.COIN));
  } else if (def.role === 'cheffe') {
    prop.push(cylGeom(0.035, 0.035, 1.3, 6, 0.65, 0, -0.2, 0xf4f1ea));
    prop.push(tf(boxGeom(0.4, 0.26, 0.02, 0.2, 0, 0, PALETTE.HYDRIA_BLUE), 0.65, 1.15, -0.2));
  }
  if (prop.length) kit.mesh(prop, kit.inner, { name: 'npcProp' });
  const anchor = new THREE.Object3D(); anchor.position.set(0, 1.5, 0); kit.root.add(anchor);
  if (engine && engine.fx && engine.fx.blobs) {
    const blob = engine.fx.blobs.add();
    const p = def.pos || [0, 0, 0];
    blob.set(p[0], p[1], p[2], 0);
    kit.onDispose(() => blob.remove());
  }
  const rng = makeRng(hashString(def.id || 'npc'));
  let talking = false, waveTimer = rng.range(2, 5), t = 0;
  return {
    object3d: kit.root,
    character,
    anchor,
    get talking() { return talking; },
    setTalking(b) {
      const nb = !!b;
      if (nb === talking) return;
      talking = nb;
      if (talking) kit.pop(0.4);
    },
    update(dt, time) {
      t = Number.isFinite(time) ? time : t + dt;
      kit.updateKit(dt);
      waveTimer -= dt;
      if (waveTimer < -1.4) waveTimer = rng.range(4, 8);
      const pose = talking ? 'talk' : (def.autoTalk && waveTimer < 0 ? 'wave' : 'idle');
      character.setPose(pose, 0);
      character.update(dt);
    },
    dispose() {
      character.dispose();
      kit.dispose();
    },
  };
}

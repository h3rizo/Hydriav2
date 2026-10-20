// actors/characters.js — chibi characters built from rigid parts parented to pivots (no SkinnedMesh), with
// procedural animation, pose cross-fades and squash & stretch (spec §12.5).
// Model: feet at y = 0, facing local +Z, 1.1 m tall. Character's left = +X.
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';
import {
  sphereGeom, capsuleGeom, roundedBox, cylGeom, boxGeom, latheGeom, prepStatic, tf, mergeStatic, makeRng, hashString,
} from 'a3d/render/geometry.js';
import { getActiveEngine } from 'a3d/render/materials.js';
import { QUALITY_PRESETS } from 'a3d/engine/quality.js';

export const POSE_STATES = Object.freeze(['idle', 'walk', 'run', 'jump', 'fall', 'glide', 'work', 'cheer', 'wave', 'talk', 'sad']);

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// Pivot positions (character space)
const HIP_Y = 0.36;
const LEG_X = 0.09;
const SHOULDER = [0.215, 0.6, 0];
const NECK_Y = 0.68;

// ---------------------------------------------------------------------------------------------
// Looks
// ---------------------------------------------------------------------------------------------

function lookFor(kind, opts) {
  const v = Number.isFinite(opts.variant) ? opts.variant | 0 : 0;
  const rng = makeRng(hashString(`${kind}:${opts.role || ''}:${v}`));
  const skin = PALETTE.SKIN_TONES[(v + (kind === 'technicien' ? 1 : 0)) % PALETTE.SKIN_TONES.length];
  if (kind === 'technicien') {
    return {
      skin, shirt: PALETTE.HYDRIA_YELLOW, pants: PALETTE.HYDRIA_BLUE, sleeve: PALETTE.HYDRIA_YELLOW, shoes: PALETTE.SHOE,
      hands: PALETTE.GLOVE_ORANGE, overalls: true, headwear: 'cap', capColor: PALETTE.HYDRIA_BLUE, hair: PALETTE.HAIR,
      skirt: false, pack: true, toolbox: opts.toolbox !== false, extra: null,
    };
  }
  if (kind === 'npc') {
    switch (opts.role) {
      case 'cheffe':
        return { skin, shirt: PALETTE.HYDRIA_BLUE, collar: PALETTE.HYDRIA_CYAN, pants: 0x2c3442, sleeve: PALETTE.HYDRIA_BLUE, shoes: 0x2b2420,
          hands: skin, overalls: false, headwear: opts.hat ? 'satroka' : 'bun', hair: PALETTE.HAIR, skirt: false, pack: false, toolbox: false, extra: 'clipboard' };
      case 'magasinier':
        return { skin, shirt: 0x8a96a3, pants: 0x3b4250, sleeve: 0x8a96a3, shoes: PALETTE.SHOE, hands: skin, overalls: false,
          headwear: 'cap', capColor: 0xd94f3d, hair: PALETTE.HAIR, skirt: false, pack: false, toolbox: false, extra: 'apron' };
      case 'caissiere':
        return { skin, shirt: 0xf7f4ee, pants: PALETTE.HYDRIA_BLUE_DARK, sleeve: 0xf7f4ee, shoes: 0x2b2420, hands: skin, overalls: false,
          headwear: 'bun', hair: PALETTE.HAIR, skirt: true, skirtColor: PALETTE.HYDRIA_BLUE_DARK, pack: false, toolbox: false, extra: 'pouch' };
      default: break;
    }
  }
  // usager (and generic npc)
  const cloth = PALETTE.CLOTH_TONES;
  const shirt = cloth[(v * 3 + 1) % cloth.length];
  const female = v % 2 === 1;
  const hat = opts.hat === true || (opts.hat !== false && v % 3 === 0);
  return {
    skin, shirt, sleeve: shirt, pants: female ? cloth[(v * 5 + 4) % cloth.length] : [0x3b4250, 0x5a4636, 0x2f4d6b][v % 3],
    shoes: 0x3a2a20, hands: skin, overalls: false, headwear: hat ? 'satroka' : (female ? 'bun' : 'hair'), hair: PALETTE.HAIR,
    skirt: female, skirtColor: cloth[(v * 5 + 4) % cloth.length], pack: false, toolbox: false,
    extra: v % 4 === 2 ? 'lamba' : null, lambaColor: rng() < 0.5 ? 0xf4efe6 : 0xe9d9b8,
  };
}

// ---------------------------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------------------------

// Segment budgets: technicien ≈ 2.6k triangles (high LOD) / ≈ 1k (low LOD).
function segs(hi) {
  return hi
    ? { head: [14, 10], capH: 5, ball: [8, 6], small: [6, 4], tiny: [5, 3], radial: 8, cap: 2, lathe: 12, hi: true }
    : { head: [9, 7], capH: 3, ball: [6, 4], small: [5, 3], tiny: [4, 2], radial: 6, cap: 1, lathe: 8, hi: false };
}

/** Rounded box on the high LOD, plain box on the low LOD. */
function rbox(S, w, h, d, r, x, y, z, hex) {
  return S.hi ? roundedBox(w, h, d, r, 1, x, y, z, hex) : boxGeom(w, h, d, x, y, z, hex);
}

function hemisphere(r, ws, hs, thetaLen, hex) {
  return prepStatic(new THREE.SphereGeometry(r, ws, hs, 0, Math.PI * 2, 0, thetaLen), hex);
}

function buildParts(kind, look, hi, opts) {
  const S = segs(hi);
  const P = { body: [], head: [], armL: [], armR: [], legL: [], legR: [], fins: [], tool: [], wrench: [] };

  // --- legs (relative to the hip pivots)
  for (const side of [1, -1]) {
    const arr = side > 0 ? P.legL : P.legR;
    arr.push(capsuleGeom(0.068, 0.14, S.cap, S.radial, 0, -0.15, 0, look.pants));
    arr.push(rbox(S, 0.13, 0.085, 0.2, 0.035, 0, -0.318, 0.025, look.shoes));
  }

  // --- torso (character space)
  const torsoProfile = [[0.0, 0.29], [0.15, 0.295], [0.185, 0.35], [0.198, 0.44], [0.19, 0.55], [0.165, 0.63], [0.1, 0.68], [0.0, 0.69]];
  const torso = latheGeom(torsoProfile, S.lathe, look.shirt);
  const lower = new THREE.Color().setHex(look.overalls ? look.pants : (look.skirt ? look.skirtColor : look.pants));
  const upper = new THREE.Color().setHex(look.shirt);
  const pa = torso.attributes.position.array, ca = torso.attributes.color.array;
  const split = look.overalls ? 0.47 : 0.42;
  for (let i = 0; i < pa.length; i += 3) {
    const c = pa[i + 1] < split ? lower : upper;
    ca[i] = c.r; ca[i + 1] = c.g; ca[i + 2] = c.b;
  }
  P.body.push(torso);
  P.body.push(cylGeom(0.07, 0.08, 0.06, S.radial, 0, 0.665, 0, look.skin));   // neck

  if (look.overalls) {
    P.body.push(rbox(S, 0.26, 0.17, 0.05, 0.02, 0, 0.535, 0.168, look.pants));                   // bib
    P.body.push(boxGeom(0.09, 0.06, 0.02, 0.04, 0.53, 0.196, PALETTE.HYDRIA_BLUE_DARK));           // pocket
    P.body.push(sphereGeom(0.018, S.tiny[0], S.tiny[1], 0.04, 0.535, 0.208, PALETTE.HYDRIA_CYAN, 1, 1.25, 0.5)); // logo drop
    for (const sx of [0.085, -0.085]) {
      // straps: down the bib, over the shoulder, down the back
      P.body.push(boxGeom(0.04, 0.12, 0.02, sx, 0.64, 0.155, PALETTE.HYDRIA_YELLOW_DARK));
      P.body.push(tf(boxGeom(0.04, 0.02, 0.24, 0, 0, 0, PALETTE.HYDRIA_YELLOW_DARK), sx * 1.15, 0.69, -0.005, 0, 1, 1, 1, 0, 0));
      P.body.push(sphereGeom(0.017, S.tiny[0], S.tiny[1], sx, 0.6, 0.195, PALETTE.HYDRIA_YELLOW));
    }
  }
  if (look.collar) {
    P.body.push(tf(prepStatic(new THREE.TorusGeometry(0.105, 0.025, 5, S.radial + 2), look.collar), 0, 0.655, 0.01, 0, 1, 1, 1, Math.PI / 2, 0));
  }
  if (look.extra === 'apron') {
    P.body.push(rbox(S, 0.3, 0.34, 0.03, 0.015, 0, 0.42, 0.185, 0x7a4f2e));
    P.body.push(boxGeom(0.03, 0.18, 0.015, 0.1, 0.62, 0.15, 0x7a4f2e));
    P.body.push(boxGeom(0.03, 0.18, 0.015, -0.1, 0.62, 0.15, 0x7a4f2e));
  }
  if (look.extra === 'pouch') P.body.push(rbox(S, 0.12, 0.1, 0.06, 0.02, 0.17, 0.38, 0.08, PALETTE.HYDRIA_YELLOW));
  if (look.extra === 'lamba') {
    const lam = prepStatic(new THREE.TorusGeometry(0.17, 0.055, 5, S.radial + 4), look.lambaColor);
    P.body.push(tf(lam, 0, 0.62, 0, 0, 1, 0.7, 1, Math.PI / 2 - 0.15, 0));
  }
  if (look.skirt) {
    const skirt = latheGeom([[0.0, 0.2], [0.245, 0.2], [0.215, 0.32], [0.195, 0.44], [0.0, 0.45]], S.lathe, look.skirtColor);
    P.body.push(skirt);
  }

  // --- Hydro-pack (technicien)
  if (look.pack) {
    P.body.push(rbox(S, 0.27, 0.3, 0.15, 0.06, 0, 0.5, -0.2, 0xe9f1fa));
    P.body.push(rbox(S, 0.28, 0.07, 0.16, 0.03, 0, 0.66, -0.2, PALETTE.HYDRIA_BLUE));
    P.body.push(capsuleGeom(0.038, 0.13, 1, S.radial, 0, 0.49, -0.275, PALETTE.HYDRIA_CYAN));
    for (const sx of [0.075, -0.075]) P.body.push(cylGeom(0.033, 0.04, 0.07, 6, sx, 0.31, -0.22, PALETTE.METAL_DARK, true));
    P.body.push(tf(prepStatic(new THREE.TorusGeometry(0.035, 0.012, 3, 6), PALETTE.HYDRIA_BLUE), 0.15, 0.6, -0.12, 0, 1, 1, 1, 0, Math.PI / 2));
    // glide fins (separate pivot, scaled from 0 to 1)
    for (const sx of [1, -1]) {
      const fin = sphereGeom(0.24, S.ball[0], S.ball[1], 0, 0, 0, PALETTE.HYDRIA_CYAN, 1.0, 0.16, 0.5);
      tf(fin, sx * 0.27, 0.04, 0, 0, 1, 1, 1, 0, sx * 0.25);
      P.fins.push(fin);
      P.fins.push(tf(sphereGeom(0.05, S.tiny[0], S.tiny[1], 0, 0, 0, 0xffffff, 1, 0.5, 1), sx * 0.44, 0.08, 0, 0, 1));
    }
  }

  // --- head (relative to the neck pivot)
  const HC = 0.165, HR = 0.235;
  P.head.push(sphereGeom(HR, S.head[0], S.head[1], 0, HC, 0, look.skin));
  for (const sx of [1, -1]) {
    P.head.push(sphereGeom(0.05, S.tiny[0], S.tiny[1], sx * 0.228, HC - 0.01, -0.005, look.skin, 0.55, 1, 0.8));              // ears
    P.head.push(sphereGeom(0.038, S.small[0], S.small[1], sx * 0.086, HC - 0.005, HR - 0.03, PALETTE.EYE, 0.85, 1.3, 0.5));   // eyes
    if (S.hi) P.head.push(sphereGeom(0.012, S.tiny[0], S.tiny[1], sx * 0.078, HC + 0.02, HR - 0.008, 0xffffff));             // eye shine
    P.head.push(sphereGeom(0.034, S.tiny[0], S.tiny[1], sx * 0.142, HC - 0.06, HR - 0.06, PALETTE.CHEEK, 1, 0.7, 0.35));      // cheeks
  }
  P.head.push(sphereGeom(0.024, S.tiny[0], S.tiny[1], 0, HC - 0.045, HR - 0.005, look.skin, 1, 0.85, 1));                      // nose
  P.head.push(tf(capsuleGeom(0.011, 0.045, 1, 4, 0, 0, 0, 0x9a3b3b), 0, HC - 0.095, HR - 0.025, 0, 1, 1, 1, 0, Math.PI / 2));  // smile
  switch (look.headwear) {
    case 'cap': {
      const cap = hemisphere(HR + 0.014, S.head[0], S.capH, Math.PI / 2, look.capColor);
      P.head.push(tf(cap, 0, HC + 0.02, -0.005, 0, 1, 1, 1, -0.12, 0));
      const brim = prepStatic(new THREE.CylinderGeometry(0.15, 0.15, 0.028, S.radial + 2), look.capColor === PALETTE.HYDRIA_BLUE ? PALETTE.HYDRIA_BLUE_DARK : look.capColor);
      P.head.push(tf(brim, 0, HC + 0.045, 0.19, 0, 1, 1, 1.15, 0.12, 0));
      if (look.capColor === PALETTE.HYDRIA_BLUE) {
        P.head.push(sphereGeom(0.034, S.tiny[0], S.tiny[1], 0, HC + 0.15, 0.185, PALETTE.HYDRIA_CYAN, 1, 1.25, 0.45));
      }
      P.head.push(hemisphere(HR + 0.006, S.ball[0], S.ball[1], Math.PI * 0.62, look.hair));   // hair showing at the back
      tf(P.head[P.head.length - 1], 0, HC - 0.01, -0.03, 0, 1, 1, 1, -0.9, 0);
      break;
    }
    case 'satroka': {
      P.head.push(hemisphere(HR + 0.008, S.ball[0], S.ball[1], Math.PI * 0.6, look.hair));
      tf(P.head[P.head.length - 1], 0, HC, -0.02, 0, 1, 1, 1, -0.4, 0);
      P.head.push(cylGeom(0.34, 0.34, 0.022, S.radial + 4, 0, HC + 0.13, 0, PALETTE.THATCH_LIGHT));
      P.head.push(cylGeom(0.16, 0.19, 0.13, S.radial + 2, 0, HC + 0.15, 0, PALETTE.THATCH));
      P.head.push(cylGeom(0.195, 0.195, 0.035, S.radial + 2, 0, HC + 0.16, 0, 0x7a3b2b, true));
      break;
    }
    case 'bun': {
      P.head.push(hemisphere(HR + 0.012, S.ball[0], S.ball[1], Math.PI * 0.62, look.hair));
      tf(P.head[P.head.length - 1], 0, HC + 0.005, -0.015, 0, 1, 1, 1, -0.45, 0);
      P.head.push(sphereGeom(0.085, S.ball[0], S.ball[1], 0, HC + 0.17, -0.15, look.hair));
      break;
    }
    default: {
      P.head.push(hemisphere(HR + 0.012, S.ball[0], S.ball[1], Math.PI * 0.55, look.hair));
      tf(P.head[P.head.length - 1], 0, HC + 0.005, -0.01, 0, 1, 1, 1, -0.35, 0);
    }
  }

  // --- arms (relative to the shoulder pivots)
  for (const side of [1, -1]) {
    const arr = side > 0 ? P.armL : P.armR;
    arr.push(sphereGeom(0.072, S.ball[0], S.ball[1], 0, -0.02, 0, look.sleeve));
    arr.push(capsuleGeom(0.048, 0.12, S.cap, S.radial - 1, 0, -0.13, 0, look.skin));
    arr.push(sphereGeom(look.hands === PALETTE.GLOVE_ORANGE ? 0.066 : 0.055, S.ball[0], S.ball[1], 0, -0.245, 0.01, look.hands));
  }
  if (look.extra === 'clipboard') {
    P.armL.push(boxGeom(0.16, 0.21, 0.02, 0.0, -0.26, 0.08, 0x8a5a3b));
    P.armL.push(boxGeom(0.13, 0.16, 0.025, 0.0, -0.27, 0.085, 0xffffff));
    P.armL.push(boxGeom(0.05, 0.025, 0.03, 0.0, -0.165, 0.085, PALETTE.METAL));
  }

  // --- toolbox (right hand) and wrench (work pose)
  P.tool.push(rbox(S, 0.22, 0.13, 0.1, 0.02, 0, -0.34, 0.02, PALETTE.TOOLBOX_RED));
  P.tool.push(boxGeom(0.24, 0.02, 0.11, 0, -0.29, 0.02, 0xb52a2d));
  P.tool.push(boxGeom(0.09, 0.03, 0.025, 0, -0.262, 0.02, 0x3a3a3a));
  P.tool.push(boxGeom(0.035, 0.025, 0.01, 0, -0.31, 0.073, PALETTE.HYDRIA_YELLOW));
  P.wrench.push(boxGeom(0.03, 0.2, 0.02, 0, -0.32, 0.03, PALETTE.METAL));
  P.wrench.push(tf(prepStatic(new THREE.TorusGeometry(0.035, 0.014, 4, 8, Math.PI * 1.5), PALETTE.METAL), 0, -0.43, 0.03, 0, 1, 1, 1, 0, Math.PI * 0.75));

  if (opts.mergeMode === 'legs' || opts.mergeMode === 'all') {
    // Bystanders never walk: legs merged into the body.
    for (const [arr, x] of [[P.legL, LEG_X], [P.legR, -LEG_X]]) {
      for (const g of arr) { g.translate(x, HIP_Y, 0); P.body.push(g); }
      arr.length = 0;
    }
  }
  if (opts.mergeMode === 'all') {
    // Low tier bystanders: one mesh in the rest pose (animation through the body group only).
    for (const g of P.head) { g.translate(0, NECK_Y, 0); P.body.push(g); }
    P.head.length = 0;
    for (const [arr, side] of [[P.armL, 1], [P.armR, -1]]) {
      for (const g of arr) { tf(g, side * SHOULDER[0], SHOULDER[1], SHOULDER[2], 0, 1, 1, 1, 0, side * 0.12); P.body.push(g); }
      arr.length = 0;
    }
  }
  return P;
}

// Carry items, built once per character on demand (relative to the carry pivot in front of the chest).
function buildCarry(kind) {
  switch (kind) {
    case 'receipt':
    case 'receipts':
    case 'recu':
      return mergeStatic([boxGeom(0.16, 0.2, 0.015, 0, 0, 0, PALETTE.PAPER), boxGeom(0.12, 0.012, 0.018, 0, 0.04, 0.002, 0x9aa3ad),
        boxGeom(0.12, 0.012, 0.018, 0, 0.0, 0.002, 0x9aa3ad), boxGeom(0.08, 0.012, 0.018, -0.02, -0.04, 0.002, 0x9aa3ad)]);
    case 'coins':
    case 'cash':
      return mergeStatic([cylGeom(0.07, 0.07, 0.03, 10, 0, -0.04, 0, PALETTE.COIN), cylGeom(0.07, 0.07, 0.03, 10, 0.02, -0.01, 0.01, 0xffe08a),
        cylGeom(0.07, 0.07, 0.03, 10, -0.01, 0.02, -0.01, PALETTE.COIN)]);
    case 'pipe':
    case 'tuyau':
      return mergeStatic([tf(cylGeom(0.05, 0.05, 0.5, 10, 0, -0.25, 0, PALETTE.PIPE), 0, 0, 0, 0, 1, 1, 1, 0, Math.PI / 2)]);
    default: {
      // spare-part box (bon de livraison)
      const g = roundedBox(0.3, 0.22, 0.24, 0.02, 1, 0, 0, 0, PALETTE.CARDBOARD);
      return mergeStatic([g, boxGeom(0.31, 0.04, 0.05, 0, 0.0, 0, 0xb08453), boxGeom(0.06, 0.06, 0.005, 0.07, 0.03, 0.123, PALETTE.HYDRIA_BLUE)]);
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Pose channels
// ---------------------------------------------------------------------------------------------

const CH = { ALX: 0, ALZ: 1, ARX: 2, ARZ: 3, LLX: 4, LRX: 5, HX: 6, HY: 7, LEAN: 8, HOP: 9, SWAY: 10, BREATH: 11, HZ: 12 };
const NCH = 13;

function writePose(out, state, t, phase, speed, carrying) {
  out.fill(0);
  out[CH.ALZ] = 0.12; out[CH.ARZ] = -0.12;
  switch (state) {
    case 'walk':
    case 'run': {
      const run = state === 'run';
      const amp = run ? 0.55 + 0.4 * speed : 0.35 + 0.25 * speed;
      const s = Math.sin(phase);
      out[CH.LLX] = -s * amp;
      out[CH.LRX] = s * amp;
      out[CH.ALX] = s * amp * 0.85;
      out[CH.ARX] = -s * amp * 0.85;
      out[CH.ALZ] = run ? 0.22 : 0.12;
      out[CH.ARZ] = run ? -0.22 : -0.12;
      out[CH.HOP] = Math.abs(Math.sin(phase)) * (run ? 0.06 : 0.03);
      out[CH.LEAN] = run ? 0.16 + 0.06 * speed : 0.05;
      out[CH.HX] = -out[CH.LEAN] * 0.6;
      out[CH.SWAY] = Math.cos(phase) * (run ? 0.05 : 0.03);
      break;
    }
    case 'jump':
      out[CH.ALX] = -2.1; out[CH.ALZ] = 0.55; out[CH.ARX] = -2.1; out[CH.ARZ] = -0.55;
      out[CH.LLX] = -0.75; out[CH.LRX] = 0.35; out[CH.HX] = -0.15; out[CH.LEAN] = -0.04;
      break;
    case 'fall':
      out[CH.ALX] = -2.5 + Math.sin(t * 15) * 0.35; out[CH.ALZ] = 0.8 + Math.sin(t * 13) * 0.25;
      out[CH.ARX] = -2.5 + Math.sin(t * 15 + 2) * 0.35; out[CH.ARZ] = -0.8 - Math.sin(t * 13 + 1) * 0.25;
      out[CH.LLX] = -0.35 + Math.sin(t * 12) * 0.3; out[CH.LRX] = -0.35 - Math.sin(t * 12) * 0.3;
      out[CH.HX] = 0.12;
      break;
    case 'glide':
      out[CH.ALX] = -0.2 + Math.sin(t * 6) * 0.06; out[CH.ALZ] = 1.35;
      out[CH.ARX] = -0.2 - Math.sin(t * 6) * 0.06; out[CH.ARZ] = -1.35;
      out[CH.LLX] = 0.38; out[CH.LRX] = 0.5; out[CH.LEAN] = 0.34; out[CH.HX] = -0.32;
      out[CH.SWAY] = Math.sin(t * 2.2) * 0.06;
      break;
    case 'work':
      out[CH.HOP] = -0.035; out[CH.LEAN] = 0.24; out[CH.HX] = 0.32;
      out[CH.ALX] = -1.1; out[CH.ALZ] = -0.2;
      out[CH.ARX] = -1.45 + Math.sin(t * 13) * 0.45; out[CH.ARZ] = 0.15;
      out[CH.LLX] = -0.35; out[CH.LRX] = 0.2;
      break;
    case 'cheer': {
      const w = Math.sin(t * 12);
      out[CH.ALX] = -2.65 + w * 0.12; out[CH.ALZ] = 0.4 + w * 0.2;
      out[CH.ARX] = -2.65 - w * 0.12; out[CH.ARZ] = -0.4 + w * 0.2;
      out[CH.HOP] = Math.abs(Math.sin(t * 7)) * 0.14; out[CH.HX] = -0.25;
      out[CH.LLX] = -0.1; out[CH.LRX] = 0.1;
      break;
    }
    case 'wave':
      out[CH.ARX] = -2.5; out[CH.ARZ] = -0.3 + Math.sin(t * 10) * 0.42;
      out[CH.HZ] = Math.sin(t * 2) * 0.08; out[CH.HX] = -0.05;
      out[CH.BREATH] = Math.sin(t * 2.2) * 0.015;
      break;
    case 'talk':
      out[CH.HX] = Math.sin(t * 7) * 0.07; out[CH.HY] = Math.sin(t * 1.3) * 0.12;
      out[CH.ALX] = -0.6 + Math.sin(t * 3) * 0.3; out[CH.ALZ] = 0.3 + Math.sin(t * 2.3) * 0.1;
      out[CH.ARX] = -0.35 + Math.sin(t * 2.6 + 1) * 0.2;
      out[CH.BREATH] = Math.sin(t * 2.2) * 0.015;
      break;
    case 'sad':
      out[CH.HX] = 0.45; out[CH.ALZ] = 0.05; out[CH.ARZ] = -0.05; out[CH.ALX] = -0.15; out[CH.ARX] = -0.15;
      out[CH.LEAN] = 0.08; out[CH.SWAY] = Math.sin(t * 1.2) * 0.04; out[CH.BREATH] = Math.sin(t * 1.4) * 0.02;
      break;
    default: // idle
      out[CH.ALX] = Math.sin(t * 1.1) * 0.05; out[CH.ARX] = Math.sin(t * 1.1 + 0.5) * 0.05;
      out[CH.HY] = Math.sin(t * 0.5) * 0.28 * Math.sin(t * 0.13);
      out[CH.HX] = Math.sin(t * 0.7) * 0.04;
      out[CH.BREATH] = Math.sin(t * 2.2) * 0.018;
  }
  if (carrying && state !== 'cheer' && state !== 'fall' && state !== 'glide') {
    out[CH.ALX] = -1.05; out[CH.ALZ] = -0.28; out[CH.ARX] = -1.05; out[CH.ARZ] = 0.28;
  }
}

// ---------------------------------------------------------------------------------------------
// CharacterView
// ---------------------------------------------------------------------------------------------

const _wp = new THREE.Vector3();

class CharacterView {
  constructor(kind, opts) {
    const engine = getActiveEngine();
    this.engine = engine;
    this.kind = kind;
    const tier = opts.tier || (engine ? engine.tier : 'medium');
    const preset = QUALITY_PRESETS[tier] || QUALITY_PRESETS.medium;
    this.lod = preset.charLod === 'low' ? 'low' : 'high';
    const hi = this.lod === 'high';
    this.look = lookFor(kind, opts);
    // Technicien: full rig. Bystanders: legs merged (all tiers), everything merged on the low LOD.
    this.mergeMode = kind === 'technicien' ? 'none' : (hi ? 'legs' : 'all');
    // Bystanders rely on blob shadows below the high tier (saves shadow-pass draw calls).
    this.castsShadow = kind === 'technicien' || tier === 'high';
    const parts = buildParts(kind, this.look, hi, { ...opts, mergeMode: this.mergeMode });
    this._geoms = [];
    this._meshes = [];
    const mats = engine ? engine.materials : null;
    const mk = (geoms, parent, name) => {
      const g = mergeStatic(geoms);
      if (!g) return null;
      this._geoms.push(g);
      const m = new THREE.Mesh(g);
      m.name = name;
      if (mats) mats.bind(m, 'hero'); else m.material = new THREE.MeshToonMaterial({ vertexColors: true });
      m.castShadow = this.castsShadow;
      m.receiveShadow = false;
      parent.add(m);
      this._meshes.push(m);
      return m;
    };

    this.object3d = new THREE.Group();
    this.object3d.name = `character:${kind}`;
    this.body = new THREE.Group();
    this.object3d.add(this.body);
    this.bodyMesh = mk(parts.body, this.body, 'body');
    this.head = new THREE.Group(); this.head.position.set(0, NECK_Y, 0); this.body.add(this.head);
    this.headMesh = mk(parts.head, this.head, 'head');
    this.armL = new THREE.Group(); this.armL.position.set(SHOULDER[0], SHOULDER[1], SHOULDER[2]); this.body.add(this.armL);
    this.armR = new THREE.Group(); this.armR.position.set(-SHOULDER[0], SHOULDER[1], SHOULDER[2]); this.body.add(this.armR);
    mk(parts.armL, this.armL, 'armL');
    mk(parts.armR, this.armR, 'armR');
    this.legL = new THREE.Group(); this.legL.position.set(LEG_X, HIP_Y, 0); this.body.add(this.legL);
    this.legR = new THREE.Group(); this.legR.position.set(-LEG_X, HIP_Y, 0); this.body.add(this.legR);
    mk(parts.legL, this.legL, 'legL');
    mk(parts.legR, this.legR, 'legR');
    this.fins = new THREE.Group(); this.fins.position.set(0, 0.56, -0.25); this.fins.scale.setScalar(0.001); this.fins.visible = false;
    this.body.add(this.fins);
    this.finsMesh = parts.fins.length ? mk(parts.fins, this.fins, 'fins') : null;
    this.toolMesh = this.look.toolbox ? mk(parts.tool, this.armR, 'toolbox') : null;
    this.wrenchMesh = kind === 'technicien' ? mk(parts.wrench, this.armR, 'wrench') : null;
    if (this.wrenchMesh) this.wrenchMesh.visible = false;
    if (!this.look.toolbox) for (const g of parts.tool) g.dispose();
    if (kind !== 'technicien') for (const g of parts.wrench) g.dispose();
    this.carryPivot = new THREE.Group(); this.carryPivot.position.set(0, 0.48, 0.27); this.body.add(this.carryPivot);
    this._carryMeshes = new Map();
    this.carry = null;

    this.state = 'idle';
    this.speed = 0;
    this.t = Math.random() * 10;
    this.phase = 0;
    this.stateTime = 0;
    this._from = new Float32Array(NCH);
    this._to = new Float32Array(NCH);
    this._cur = new Float32Array(NCH);
    this._blend = 1;
    this._sq = 0; this._sqV = 0;
    this._fin = 0;
    this._mistAcc = 0;
    this.object3d.userData.character = this;
  }

  /** Meshes (outlines / custom materials). */
  get meshes() { return this._meshes; }

  setPose(state, speed01 = 0) {
    const s = POSE_STATES.includes(state) ? state : 'idle';
    this.speed = clamp(speed01 || 0, 0, 1);
    if (s === this.state) return;
    this._from.set(this._cur);
    this._blend = 0;
    this.state = s;
    this.stateTime = 0;
  }

  /** Squash & stretch impulse: 'jump' stretches, 'land' squashes, 'pop' bounces. */
  squash(kind, strength = 1) {
    const k = clamp(strength, 0, 2);
    if (kind === 'jump') this._sqV += 3.2 * k;
    else if (kind === 'land') this._sqV -= 4.2 * k;
    else this._sqV += 2.8 * k;
  }

  setCarry(kind) {
    const k = kind || null;
    if (k === this.carry) return;
    this.carry = k;
    for (const m of this._carryMeshes.values()) m.visible = false;
    if (!k) return;
    let m = this._carryMeshes.get(k);
    if (!m) {
      const g = buildCarry(k);
      this._geoms.push(g);
      m = new THREE.Mesh(g);
      m.name = `carry:${k}`;
      if (this.engine) this.engine.materials.bind(m, 'hero'); else m.material = new THREE.MeshToonMaterial({ vertexColors: true });
      m.castShadow = true;
      this.carryPivot.add(m);
      this._meshes.push(m);
      this._carryMeshes.set(k, m);
    }
    m.visible = true;
  }

  update(dt) {
    if (!(dt > 0)) dt = 0;
    dt = Math.min(dt, 0.1);
    this.t += dt;
    this.stateTime += dt;
    const st = this.state;
    if (st === 'walk' || st === 'run') {
      const hz = st === 'run' ? 1.7 + 1.6 * this.speed : 1.2 + 0.9 * this.speed;
      this.phase += dt * hz * Math.PI * 2;
    } else {
      this.phase += dt * 2;
    }
    writePose(this._to, st, this.t, this.phase, this.speed, !!this.carry);
    if (this._blend < 1) this._blend = Math.min(1, this._blend + dt / 0.14);
    const w = this._blend * this._blend * (3 - 2 * this._blend);
    const c = this._cur, f = this._from, to = this._to;
    for (let i = 0; i < NCH; i++) c[i] = f[i] + (to[i] - f[i]) * w;

    this.armL.rotation.set(c[CH.ALX], 0, c[CH.ALZ]);
    this.armR.rotation.set(c[CH.ARX], 0, c[CH.ARZ]);
    this.legL.rotation.x = c[CH.LLX];
    this.legR.rotation.x = c[CH.LRX];
    this.head.rotation.set(c[CH.HX], c[CH.HY], c[CH.HZ], 'YXZ');

    // squash spring (sub-stepped for stability)
    let rem = dt;
    while (rem > 1e-5) {
      const h = Math.min(rem, 1 / 120);
      const a = -320 * this._sq - 17 * this._sqV;
      this._sqV += a * h;
      this._sq = clamp(this._sq + this._sqV * h, -0.35, 0.35);
      rem -= h;
    }
    const sq = this._sq;
    const breath = c[CH.BREATH];
    this.body.scale.set(1 - sq * 0.45 - breath * 0.3, 1 + sq + breath, 1 - sq * 0.45 - breath * 0.3);
    this.body.position.y = c[CH.HOP];
    this.body.rotation.set(c[CH.LEAN], 0, c[CH.SWAY]);

    // glide fins
    const finTarget = st === 'glide' ? 1 : 0;
    this._fin += (finTarget - this._fin) * (1 - Math.exp(-dt * 12));
    if (this.finsMesh) {
      this.fins.visible = this._fin > 0.02;
      const fs = Math.max(0.001, this._fin);
      this.fins.scale.set(fs, fs, fs);
      this.fins.rotation.z = Math.sin(this.t * 9) * 0.05 * this._fin;
    }
    if (st === 'glide' && this.engine && this.engine.fx && dt > 0 && this.object3d.visible) {
      this._mistAcc += dt * 22;
      if (this._mistAcc >= 1) {
        this.fins.updateWorldMatrix(true, false);
        while (this._mistAcc >= 1) {
          this._mistAcc -= 1;
          _wp.set(Math.random() < 0.5 ? 0.4 : -0.4, -0.05, 0).applyMatrix4(this.fins.matrixWorld);
          this.engine.fx.particles.emit('glideMist', _wp, { count: 1 });
        }
      }
    } else {
      this._mistAcc = 0;
    }

    // props in hands
    if (this.toolMesh) this.toolMesh.visible = !this.carry && st !== 'work' && st !== 'cheer' && st !== 'glide';
    if (this.wrenchMesh) this.wrenchMesh.visible = st === 'work';
  }

  setVisible(b) {
    this.object3d.visible = !!b;
  }

  dispose() {
    const mats = this.engine ? this.engine.materials : null;
    for (const m of this._meshes) {
      if (mats) {
        mats.unbind(m);
        for (const child of [...m.children]) if (child.name === 'outline') mats.removeOutline(child);
      }
    }
    for (const g of this._geoms) g.dispose();
    this._geoms.length = 0;
    this._meshes.length = 0;
    if (this.object3d.parent) this.object3d.parent.remove(this.object3d);
  }
}

/**
 * Creates a character. kind: 'technicien' | 'usager' | 'npc'.
 * opts: {variant?:number, toolbox?:boolean (technicien, default true), hat?:boolean, tier?:'low'|'medium'|'high',
 *        role?:'cheffe'|'magasinier'|'caissiere' (npc)}.
 * @returns {CharacterView} { object3d, setPose(state, speed01), squash(kind, strength), setCarry(kind|null), update(dt),
 *   setVisible(b), dispose(), meshes, bodyMesh, headMesh }
 */
export function createCharacter(kind, opts = {}) {
  const k = kind === 'usager' || kind === 'npc' ? kind : 'technicien';
  return new CharacterView(k, opts || {});
}

/** Approximate triangle count of a character (debug / budget checks). */
export function characterTriangles(view) {
  let n = 0;
  for (const m of view.meshes) n += m.geometry.attributes.position.count / 3;
  return n;
}

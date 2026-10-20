// render/StaticWorld.js — static platforms, decor and water (spec §12.3, §12.5).
// 16 m chunks: per chunk one merged worldSoft mesh and one water mesh. Foliage (grass, flowers, bushes, trees,
// ravinala) is instanced with wind sway on medium/high — ONE InstancedMesh per kind/variant for the whole level
// (instead of per chunk) so the draw count stays flat whatever the level size. On the low tier foliage is merged into
// the chunk meshes (no extra draw call, no extra program).
// The build is time-sliced (≤ 8 ms per slice). Auto-scatter (grass, flowers, stones, patches) on grass tops uses
// mulberry32(hash(seedString)).
import * as THREE from 'three';
import { buildPlatformGeometry, buildPlatformSign, SignBatch } from 'a3d/render/props/platforms.js';
import {
  buildDecor, getFoliagePrototype, FOLIAGE_CASTS_SHADOW, protoKey, scatterStone, scatterPatch, variantCount, placementMatrix,
} from 'a3d/render/props/village.js';
import { buildWaterChunkGeometry } from 'a3d/render/water.js';
import { mergeStatic, makeRng, hashString } from 'a3d/render/geometry.js';

const CHUNK = 16;
const SLICE_MS = 8;
const MERGE_BATCH = 48;

const DECOR_CLEAR_RADIUS = { ravinala: 0.6, baobab: 1.5, tree: 0.5, bush: 0.6, rock: 0.9, crate: 0.6, barrel: 0.5, cart: 1.6,
  sign: 0.5, flowers: 0.3, rice_patch: 0 };

function now() { return (globalThis.performance && performance.now) ? performance.now() : Date.now(); }
function yieldSlice() { return new Promise((r) => setTimeout(r)); }

export class StaticWorld {
  constructor(engine, seedString) {
    this.engine = engine;
    this.seed = String(seedString ?? 'hydria');
    this.platforms = [];
    this.decor = [];
    this.waters = [];
    this.group = new THREE.Group();
    this.group.name = 'staticWorld';
    this.group.matrixAutoUpdate = false;
    this.meshes = [];
    this.waterMeshes = [];
    this.instanced = [];
    this.signBatch = new SignBatch();
    this.built = false;
    this.stats = { chunks: 0, triangles: 0, instances: 0, drawables: 0 };
    this._offTier = null;
    this._disposed = false;
  }

  /** box | cyl | ramp entity with a style (spec §5.2 statics). */
  addPlatform(entity) {
    if (entity) this.platforms.push(entity);
  }

  /** decor entity {kind, pos, yaw?, scale?, variant?, points?, width?, radius?, size?, text?}. */
  addDecor(entity) {
    if (entity && entity.kind) this.decor.push(entity);
  }

  /** water {min, max, deep, flow?}. */
  addWater(def) {
    if (def && def.min && def.max) this.waters.push(def);
  }

  _chunkKey(x, z) {
    return `${Math.floor(x / CHUNK)},${Math.floor(z / CHUNK)}`;
  }

  _chunk(map, x, z) {
    const key = this._chunkKey(x, z);
    let c = map.get(key);
    if (!c) {
      c = { key, cx: Math.floor(x / CHUNK), cz: Math.floor(z / CHUNK), geoms: [] };
      map.set(key, c);
    }
    return c;
  }

  _levelCenter() {
    let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity;
    for (const p of this.platforms) {
      if (p.type === 'box' || p.type === 'ramp') {
        x0 = Math.min(x0, p.min[0]); z0 = Math.min(z0, p.min[2]); x1 = Math.max(x1, p.max[0]); z1 = Math.max(z1, p.max[2]);
      } else if (p.type === 'cyl') {
        x0 = Math.min(x0, p.c[0] - p.r); z0 = Math.min(z0, p.c[1] - p.r); x1 = Math.max(x1, p.c[0] + p.r); z1 = Math.max(z1, p.c[1] + p.r);
      }
    }
    if (!Number.isFinite(x0)) return { x: 0, z: 0 };
    return { x: (x0 + x1) / 2, z: (z0 + z1) / 2 };
  }

  async build(onProgress) {
    const engine = this.engine;
    const q = engine.quality;
    const lowDetail = engine.tier === 'low';
    const instancing = !lowDetail;
    const rng = makeRng(hashString(this.seed));
    const center = this._levelCenter();
    const chunks = new Map();
    const signs = [];
    const ctx = { rng, center, signs, lowDetail };
    const total = Math.max(1, this.platforms.length + this.decor.length);
    let done = 0;
    let slice = now();
    const tick = async (p) => {
      if (now() - slice > SLICE_MS) {
        if (onProgress) onProgress(Math.min(0.99, p));
        await yieldSlice();
        slice = now();
      }
    };
    const centerTmp = new THREE.Vector3();
    const place = (g) => {
      if (!g) return;
      if (!g.boundingBox) g.computeBoundingBox();
      g.boundingBox.getCenter(centerTmp);
      this._chunk(chunks, centerTmp.x, centerTmp.z).geoms.push(g);
    };
    const instMat = new THREE.Matrix4();
    const instances = new Map();      // level-wide: key -> {kind, variant, scatter, matrices}
    const addInstance = (kind, variant, matrix, scatter) => {
      if (!instancing) {
        // low tier: bake the prototype into the chunk geometry
        const proto = getFoliagePrototype(kind, variant, lowDetail);
        if (proto) place(proto.clone().applyMatrix4(matrix));
        return;
      }
      const key = (scatter ? 's:' : 'd:') + protoKey(kind, variant, lowDetail);
      let list = instances.get(key);
      if (!list) { list = { kind, variant, scatter, matrices: [] }; instances.set(key, list); }
      list.matrices.push(matrix.clone());
    };

    // 1. platforms
    for (const p of this.platforms) {
      if (this._disposed) return;
      const geoms = buildPlatformGeometry(p, ctx);
      for (const g of geoms) place(g);
      for (const g of buildPlatformSign(p, ctx)) place(g);
      done++;
      await tick(0.45 * done / total);
    }

    // 2. decor
    const clearZones = [];
    const paths = [];
    for (const d of this.decor) {
      if (this._disposed) return;
      const out = buildDecor(d, ctx);
      for (const g of out.geoms) place(g);
      for (const inst of out.instances) addInstance(inst.kind, inst.variant, inst.matrix, false);
      const r = DECOR_CLEAR_RADIUS[d.kind];
      if (r && d.pos) clearZones.push([d.pos[0], d.pos[2], r * (Number.isFinite(d.scale) ? d.scale : 1)]);
      if (d.kind === 'rice_patch' && d.pos) {
        const s = d.size;
        const sx = Array.isArray(s) ? s[0] : (Number.isFinite(s) ? s : 4), sz = Array.isArray(s) ? (s[1] ?? s[0]) : (Number.isFinite(s) ? s : 3);
        clearZones.push([d.pos[0], d.pos[2], Math.hypot(sx, sz) / 2]);
      }
      if ((d.kind === 'path' || d.kind === 'fence' || d.kind === 'pipe') && Array.isArray(d.points)) {
        paths.push({ points: d.points, half: d.kind === 'path' ? (d.width || 1.6) / 2 + 0.25 : 0.35 });
      }
      done++;
      await tick(0.45 * done / total);
    }

    // 3. auto-scatter on grass tops
    const density = q.foliageDensity ?? 1;
    const solids = this.platforms.filter((p) => p.type === 'box' && p.style !== 'invisible');
    const blocked = (x, z, topY, self) => {
      for (const b of solids) {
        if (b === self) continue;
        if (b.max[1] <= topY + 0.02 || b.min[1] > topY + 2.5) continue;
        if (x > b.min[0] - 0.25 && x < b.max[0] + 0.25 && z > b.min[2] - 0.25 && z < b.max[2] + 0.25) return true;
      }
      for (const w of this.waters) {
        if (x > w.min[0] - 0.3 && x < w.max[0] + 0.3 && z > w.min[2] - 0.3 && z < w.max[2] + 0.3 && w.max[1] >= topY - 0.5) return true;
      }
      for (const [cx, cz, r] of clearZones) if ((x - cx) ** 2 + (z - cz) ** 2 < r * r) return true;
      for (const path of paths) {
        const pts = path.points;
        for (let i = 0; i < pts.length - 1; i++) {
          const ax = pts[i][0], az = pts[i][2], bx = pts[i + 1][0], bz = pts[i + 1][2];
          const dx = bx - ax, dz = bz - az;
          const l2 = dx * dx + dz * dz || 1;
          const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / l2));
          const px = ax + dx * t - x, pz = az + dz * t - z;
          if (px * px + pz * pz < path.half * path.half) return true;
        }
      }
      return false;
    };
    const scatterTop = (p) => {
      let x0, z0, x1, z1, topY, isCyl = false, cx = 0, cz = 0, rr = 0;
      if (p.type === 'box') { x0 = p.min[0]; z0 = p.min[2]; x1 = p.max[0]; z1 = p.max[2]; topY = p.max[1]; }
      else { isCyl = true; cx = p.c[0]; cz = p.c[1]; rr = p.r; x0 = cx - rr; x1 = cx + rr; z0 = cz - rr; z1 = cz + rr; topY = p.y1; }
      const inset = 0.45;
      const w = x1 - x0 - inset * 2, d = z1 - z0 - inset * 2;
      if (w <= 0.2 || d <= 0.2) return;
      const area = isCyl ? Math.PI * (rr - inset) * (rr - inset) : w * d;
      const sample = () => {
        for (let k = 0; k < 6; k++) {
          const x = x0 + inset + rng() * w, z = z0 + inset + rng() * d;
          if (isCyl && (x - cx) ** 2 + (z - cz) ** 2 > (rr - inset) ** 2) continue;
          if (blocked(x, z, topY, p)) continue;
          return [x, z];
        }
        return null;
      };
      const nPatch = Math.min(70, Math.round(area / 9 * Math.max(0.5, density)));
      for (let i = 0; i < nPatch; i++) {
        const s = sample();
        if (s) place(scatterPatch(s[0], topY, s[1], rng, rng() < 0.6));
      }
      const nStone = Math.min(30, Math.round(area / 30 * density));
      for (let i = 0; i < nStone; i++) {
        const s = sample();
        if (s) place(scatterStone(s[0], topY, s[1], rng));
      }
      if (q.grass) {
        const nGrass = Math.min(600, Math.round(area * 0.75 * density));
        for (let i = 0; i < nGrass; i++) {
          const s = sample();
          if (!s) continue;
          const v = Math.floor(rng() * variantCount('grass'));
          addInstance('grass', v, placementMatrix([s[0], topY, s[1]], rng() * Math.PI * 2, 0.75 + rng() * 0.45, instMat), true);
        }
        const nFlowers = Math.min(80, Math.round(area / 12 * density));
        for (let i = 0; i < nFlowers; i++) {
          const s = sample();
          if (!s) continue;
          const v = Math.floor(rng() * Math.min(3, variantCount('flowers')));
          addInstance('flowers', v, placementMatrix([s[0], topY, s[1]], rng() * Math.PI * 2, 0.8 + rng() * 0.4, instMat), true);
        }
      }
    };
    for (const p of this.platforms) {
      if (this._disposed) return;
      if (p.style !== 'grass' || p.walkable === false) continue;
      if (p.type !== 'box' && p.type !== 'cyl') continue;
      scatterTop(p);
      await tick(0.5);
    }

    // 4. water: assign defs to the chunks they overlap
    const waterChunks = new Map();
    for (const w of this.waters) {
      const cx0 = Math.floor(w.min[0] / CHUNK), cx1 = Math.floor((w.max[0] - 1e-4) / CHUNK);
      const cz0 = Math.floor(w.min[2] / CHUNK), cz1 = Math.floor((w.max[2] - 1e-4) / CHUNK);
      for (let i = cx0; i <= cx1; i++) {
        for (let j = cz0; j <= cz1; j++) {
          const key = `${i},${j}`;
          let list = waterChunks.get(key);
          if (!list) { list = { cx: i, cz: j, defs: [] }; waterChunks.set(key, list); }
          list.defs.push(w);
        }
      }
    }

    // 6. merge chunks and create meshes
    const mats = engine.materials;
    const worldMat = mats.get('worldSoft');
    const chunkList = [...chunks.values()];
    let processed = 0;
    for (const c of chunkList) {
      if (this._disposed) return;
      let geoms = c.geoms;
      // merge in batches so a single slice never stalls for long
      while (geoms.length > MERGE_BATCH) {
        const next = [];
        for (let i = 0; i < geoms.length; i += MERGE_BATCH) {
          next.push(mergeStatic(geoms.slice(i, i + MERGE_BATCH)));
          await tick(0.6 + 0.35 * processed / Math.max(1, chunkList.length));
        }
        geoms = next.filter(Boolean);
      }
      const merged = mergeStatic(geoms);
      if (merged) {
        const mesh = new THREE.Mesh(merged, worldMat);
        mesh.name = `chunk:${c.key}`;
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.matrixAutoUpdate = false;
        this.group.add(mesh);
        this.meshes.push(mesh);
        this.stats.triangles += merged.attributes.position.count / 3;
      }
      processed++;
      await tick(0.6 + 0.35 * processed / Math.max(1, chunkList.length));
    }

    // level-wide instanced foliage (medium/high)
    for (const list of instances.values()) {
      const proto = getFoliagePrototype(list.kind, list.variant, lowDetail);
      if (!proto || list.matrices.length === 0) continue;
      const n = list.matrices.length;
      // shuffle so lowering the density later removes a random subset
      for (let i = n - 1; i > 0; i--) {
        const j = Math.floor(rng() * (i + 1));
        const t = list.matrices[i]; list.matrices[i] = list.matrices[j]; list.matrices[j] = t;
      }
      const im = new THREE.InstancedMesh(proto, mats.foliage(list.kind), n);
      for (let i = 0; i < n; i++) im.setMatrixAt(i, list.matrices[i]);
      im.instanceMatrix.needsUpdate = true;
      im.computeBoundingSphere();
      im.castShadow = !!FOLIAGE_CASTS_SHADOW[list.kind];
      im.receiveShadow = true;
      im.matrixAutoUpdate = false;
      im.name = `foliage:${list.kind}:${list.variant}${list.scatter ? ':scatter' : ''}`;
      im.userData.scatter = list.scatter;
      im.userData.kind = list.kind;
      im.userData.full = n;
      im.userData.builtDensity = density;
      this.group.add(im);
      this.instanced.push(im);
      this.stats.instances += n;
      this.stats.triangles += n * proto.attributes.position.count / 3;
      await tick(0.96);
    }

    // water meshes
    const waterMat = this.waters.length ? mats.get('water') : null;
    const step = q.waterDetail === 'low' ? 2 : 1;
    for (const wc of waterChunks.values()) {
      const g = buildWaterChunkGeometry(wc.defs, wc.cx * CHUNK, wc.cz * CHUNK, (wc.cx + 1) * CHUNK, (wc.cz + 1) * CHUNK, step);
      if (!g) continue;
      const mesh = new THREE.Mesh(g, waterMat);
      mesh.name = `water:${wc.cx},${wc.cz}`;
      mesh.castShadow = false;
      mesh.receiveShadow = false;
      mesh.matrixAutoUpdate = false;
      this.group.add(mesh);
      this.waterMeshes.push(mesh);
      await tick(0.97);
    }

    // signs (one draw call)
    for (const s of signs) this.signBatch.add(s);
    const signMesh = this.signBatch.build();
    if (signMesh) this.group.add(signMesh);

    this.stats.chunks = chunkList.length;
    this.stats.drawables = this.meshes.length + this.instanced.length + this.waterMeshes.length + (signMesh ? 1 : 0);
    this.group.updateMatrixWorld(true);
    engine.scene.add(this.group);
    if (typeof engine.addTierListener === 'function') this._offTier = engine.addTierListener((qq) => this._applyQuality(qq));
    this._applyQuality(q);
    this.built = true;
    if (onProgress) onProgress(1);
  }

  /** Runtime tier change: scale scattered foliage counts and hide grass when the tier has none. */
  _applyQuality(q) {
    for (const im of this.instanced) {
      const ud = im.userData;
      if (!ud.scatter) continue;
      const ratio = Math.min(1, Math.max(0, (q.foliageDensity ?? 1) / (ud.builtDensity || 1)));
      im.count = Math.max(0, Math.round(ud.full * ratio));
      im.visible = !!q.grass && im.count > 0;
    }
  }

  dispose() {
    this._disposed = true;
    if (this._offTier) { this._offTier(); this._offTier = null; }
    if (this.group.parent) this.group.parent.remove(this.group);
    for (const m of this.meshes) m.geometry.dispose();
    for (const m of this.waterMeshes) m.geometry.dispose();
    for (const im of this.instanced) im.dispose();      // prototypes are shared: geometry kept
    this.signBatch.dispose();
    this.meshes.length = 0;
    this.waterMeshes.length = 0;
    this.instanced.length = 0;
    this.group.clear();
  }
}

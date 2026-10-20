// fx/markers.js — BlobShadows (every tier), LandingMarker and GuideTrail (spec §12.4).
// All three draw through the shared fx-quad program (fx/IconLayer.js), one draw call each.
import * as THREE from 'three';
import { QuadBatch, createFxQuadMaterial, FX_MODE } from 'a3d/fx/IconLayer.js';
import { PALETTE } from 'a3d/render/palette.js';

// ---------------------------------------------------------------------------------------------
// Blob shadows
// ---------------------------------------------------------------------------------------------

let _blobTex = null;
/** Radial-gradient CanvasTexture 64² (spec §12.3 'blob'). */
function blobTexture() {
  if (_blobTex) return _blobTex;
  const c = document.createElement('canvas');
  c.width = 64; c.height = 64;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, 'rgba(0,0,0,1)');
  g.addColorStop(0.55, 'rgba(0,0,0,0.75)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.NoColorSpace;
  _blobTex = tex;
  return tex;
}

const BLOB_CAPACITY = 64;
const BLOB_TINT = new THREE.Color().setHex(0x2a1f2e);

export class BlobShadows {
  constructor(engine) {
    this.engine = engine;
    this.material = createFxQuadMaterial({
      mode: FX_MODE.BLOB, map: blobTexture(), polygonOffset: true, fogMix: 1, timeUniform: engine.materials.uTime,
    });
    this.batch = new QuadBatch(BLOB_CAPACITY, this.material, 5);
    this._dirty = false;
    this._count = 0;
    engine.scene.add(this.batch.mesh);
  }

  /** @returns {{set(x, groundY, z, heightAbove), setVisible(b), remove()}} */
  add() {
    const slot = this.batch.alloc();
    const self = this;
    const h = {
      slot, visible: true, x: 0, y: 0, z: 0, hgt: 0, alive: slot >= 0,
      set(x, groundY, z, heightAbove = 0) {
        h.x = x; h.y = groundY; h.z = z; h.hgt = Math.max(0, heightAbove || 0);
        self._write(h);
      },
      setVisible(b) { h.visible = !!b; self._write(h); },
      remove() {
        if (!h.alive) return;
        h.alive = false;
        self.batch.free(h.slot);
        self._dirty = true;
      },
    };
    if (slot < 0) console.warn('[a3d] BlobShadows: capacité atteinte');
    return h;
  }

  _write(h) {
    if (!h.alive) return;
    if (!h.visible || h.y === null || h.y === undefined || !Number.isFinite(h.y)) {
      this.batch.hide(h.slot);
    } else {
      const t = Math.min(1, h.hgt / 4);
      const opacity = 0.35 * (1 - t);
      const radius = 0.45 + (0.30 - 0.45) * t;
      this.batch.set(h.slot, h.x, h.y + 0.02, h.z, radius * 2, BLOB_TINT.r, BLOB_TINT.g, BLOB_TINT.b, opacity);
    }
    this._dirty = true;
  }

  update() {
    if (!this._dirty) return;
    this._dirty = false;
    this.batch.flush();
  }

  dispose() {
    this.batch.dispose();
  }
}

// ---------------------------------------------------------------------------------------------
// Landing marker
// ---------------------------------------------------------------------------------------------

const C_GROUND = new THREE.Color().setHex(PALETTE.HYDRIA_CYAN);
const C_VOID = new THREE.Color().setHex(0xf97316);

export class LandingMarker {
  constructor(engine) {
    this.engine = engine;
    this.material = createFxQuadMaterial({
      mode: FX_MODE.LANDING, blending: THREE.NormalBlending, polygonOffset: true, fogMix: 1, timeUniform: engine.materials.uTime,
    });
    this.batch = new QuadBatch(1, this.material, 14);
    this.slot = this.batch.alloc();
    this.visible = false;
    this.batch.hide(this.slot);
    this.batch.flush();
    engine.scene.add(this.batch.mesh);
  }

  /** set(x, y, z, mode 'ground'|'void') shows the marker; set(null) hides it. */
  set(x, y, z, mode = 'ground') {
    if (x === null || x === undefined || !Number.isFinite(x)) {
      if (this.visible) { this.visible = false; this.batch.hide(this.slot); this.batch.flush(); }
      return;
    }
    const isVoid = mode === 'void';
    const c = isVoid ? C_VOID : C_GROUND;
    this.visible = true;
    this.batch.set(this.slot, x, y + 0.03, z, isVoid ? 0.9 : 0.8, c.r, c.g, c.b, 0.85, isVoid ? 1 : 0, 0, 0, 0);
    this.batch.flush();
  }

  dispose() {
    this.batch.dispose();
  }
}

// ---------------------------------------------------------------------------------------------
// Guide trail
// ---------------------------------------------------------------------------------------------

const GUIDE_CAPACITY = 160;
const GUIDE_SPACING = 0.75;
const C_GUIDE = new THREE.Color().setHex(PALETTE.HYDRIA_CYAN);

export class GuideTrail {
  constructor(engine) {
    this.engine = engine;
    this.material = createFxQuadMaterial({
      mode: FX_MODE.GUIDE, blending: THREE.AdditiveBlending, fogMix: 1, timeUniform: engine.materials.uTime,
    });
    this.batch = new QuadBatch(GUIDE_CAPACITY, this.material, 13);
    this._slots = [];
    for (let i = 0; i < GUIDE_CAPACITY; i++) this._slots.push(this.batch.alloc());
    for (const s of this._slots) this.batch.hide(s);
    this.batch.flush();
    this._count = 0;
    this._alpha = 0;
    this._target = 0;
    this._lastFrame = -1;
    this._key = '';
    engine.scene.add(this.batch.mesh);
  }

  /** setPath([[x,y,z], ...]) resamples the polyline every 0.75 m; setPath(null) fades it out. */
  setPath(points) {
    if (!points || points.length < 2) { this._target = 0; return; }
    // Avoid rebuilding when the same path is set every frame.
    const a = points[0], b = points[points.length - 1];
    const key = `${points.length}|${a[0].toFixed(2)},${a[1].toFixed(2)},${a[2].toFixed(2)}|${b[0].toFixed(2)},${b[1].toFixed(2)},${b[2].toFixed(2)}`;
    this._target = 1;
    if (key === this._key && this._count > 0) return;
    this._key = key;
    let n = 0;
    let carry = 0;        // distance already walked past the last dot
    let arc = 0;
    // place a dot at the start
    const place = (x, y, z, s) => {
      if (n >= GUIDE_CAPACITY) return;
      this._pos[n * 4] = x; this._pos[n * 4 + 1] = y; this._pos[n * 4 + 2] = z; this._pos[n * 4 + 3] = s;
      n++;
    };
    if (!this._pos) this._pos = new Float32Array(GUIDE_CAPACITY * 4);
    place(a[0], a[1] + 0.18, a[2], 0);
    for (let i = 1; i < points.length && n < GUIDE_CAPACITY; i++) {
      const p = points[i - 1], q = points[i];
      const dx = q[0] - p[0], dy = q[1] - p[1], dz = q[2] - p[2];
      const len = Math.hypot(dx, dy, dz);
      if (len < 1e-4) continue;
      let d = GUIDE_SPACING - carry;
      while (d <= len && n < GUIDE_CAPACITY) {
        const t = d / len;
        place(p[0] + dx * t, p[1] + dy * t + 0.18, p[2] + dz * t, arc + d);
        d += GUIDE_SPACING;
      }
      carry = len - (d - GUIDE_SPACING);
      arc += len;
    }
    this._count = n;
    this._writeAll();
  }

  _writeAll() {
    const a = this._alpha;
    for (let i = 0; i < GUIDE_CAPACITY; i++) {
      const s = this._slots[i];
      if (i < this._count && a > 0.001) {
        const o = i * 4;
        // fade the very first dots so the trail starts softly at the player
        const fade = Math.min(1, (i + 1) / 3);
        this.batch.set(s, this._pos[o], this._pos[o + 1], this._pos[o + 2], 0.32, C_GUIDE.r, C_GUIDE.g, C_GUIDE.b,
          0.85 * a * fade, 0, this._pos[o + 3], 0, 0);
      } else {
        this.batch.hide(s);
      }
    }
    this.batch.flush();
  }

  /** Fades in / out; called once per frame by the Engine (idempotent within a frame). */
  update(dt) {
    const frame = this.engine.frame;
    if (frame === this._lastFrame) return;
    this._lastFrame = frame;
    if (Math.abs(this._alpha - this._target) < 1e-3) return;
    const k = 1 - Math.exp(-dt * 6);
    this._alpha += (this._target - this._alpha) * k;
    if (Math.abs(this._alpha - this._target) < 0.01) this._alpha = this._target;
    if (this._alpha <= 0.001 && this._target === 0) { this._count = 0; this._key = ''; }
    this._writeAll();
  }

  dispose() {
    this.batch.dispose();
  }
}

/** Disposes module-level shared textures (Engine.dispose). */
export function disposeMarkerShared() {
  if (_blobTex) { _blobTex.dispose(); _blobTex = null; }
}

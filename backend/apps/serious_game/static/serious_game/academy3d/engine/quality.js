// engine/quality.js — three-free (TF). Quality presets, WebGL2 / tier detection and the FPS governor (spec §12.2).
import { storage } from 'a3d/core/storage.js';

export const QUALITY_PRESETS = {
  low:    { label: 'Économie', pixelRatioMin: 0.6,  pixelRatioMax: 1.0, targetFps: 30, antialias: false, shadows: false, shadowType: null,
            shadowMapSize: 0, shadowHalfExtent: 0, bloom: false, envMap: false, fogNear: 25, fogFar: 70, foliageDensity: 0.4,
            grass: false, clouds: 0, waterDetail: 'low', outlines: false, particleCapacity: 256, charLod: 'low', powerPreference: 'default' },
  medium: { label: 'Standard', pixelRatioMin: 0.75, pixelRatioMax: 1.5, targetFps: 60, antialias: false, shadows: true, shadowType: 'PCF',
            shadowMapSize: 1024, shadowHalfExtent: 14, bloom: false, envMap: false, fogNear: 40, fogFar: 110, foliageDensity: 0.7,
            grass: true, clouds: 8, waterDetail: 'full', outlines: false, particleCapacity: 512, charLod: 'high', powerPreference: 'high-performance' },
  high:   { label: 'Haute', pixelRatioMin: 1.0,  pixelRatioMax: 2.0, targetFps: 60, antialias: true, shadows: true, shadowType: 'PCFSoft',
            shadowMapSize: 2048, shadowHalfExtent: 20, bloom: true, envMap: true, fogNear: 60, fogFar: 160, foliageDensity: 1.0,
            grass: true, clouds: 16, waterDetail: 'full', outlines: true, particleCapacity: 1024, charLod: 'high', powerPreference: 'high-performance' },
};

export const TIER_ORDER = Object.freeze(['low', 'medium', 'high']);

/** Next tier down, or null when already on the lowest tier. */
export function lowerTier(tier) {
  const i = TIER_ORDER.indexOf(tier);
  return i > 0 ? TIER_ORDER[i - 1] : null;
}

const LOW_GPU_RE = /SwiftShader|llvmpipe|Mali-(T\d|G(31|51|52|57))|Mali-4|Adreno \(TM\) ([1-5]\d\d|6[01]\d)|PowerVR/i;
const HIGH_GPU_RE = /NVIDIA|GeForce|Radeon|AMD|Apple M|Iris\(R\) Xe|Arc/i;
const SOFTWARE_RE = /SwiftShader|llvmpipe|softpipe|Software Rasterizer|Microsoft Basic Render/i;

function loseContext(gl) {
  try {
    const ext = gl && gl.getExtension('WEBGL_lose_context');
    if (ext) ext.loseContext();
  } catch (_) { /* ignore */ }
}

/** True when the browser can create a WebGL2 context. Never throws. */
export function hasWebGL2() {
  try {
    if (typeof document === 'undefined' || typeof WebGL2RenderingContext === 'undefined') return false;
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2');
    if (!gl) return false;
    loseContext(gl);
    return true;
  } catch (_) {
    return false;
  }
}

function isCoarsePointer() {
  try { return !!(globalThis.matchMedia && globalThis.matchMedia('(pointer: coarse)').matches); } catch (_) { return false; }
}

/**
 * Picks a quality tier for this device (spec §12.2).
 * @returns {{tier:'low'|'medium'|'high', reason:string, renderer:string, software:boolean}}
 */
export function detectTier() {
  let renderer = '';
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2');
    if (gl) {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      renderer = String((dbg && gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) || gl.getParameter(gl.RENDERER) || '');
      loseContext(gl);
    }
  } catch (_) { renderer = ''; }

  const nav = globalThis.navigator || {};
  const coarse = isCoarsePointer();
  const memory = typeof nav.deviceMemory === 'number' ? nav.deviceMemory : undefined;
  const cores = typeof nav.hardwareConcurrency === 'number' ? nav.hardwareConcurrency : undefined;
  const software = SOFTWARE_RE.test(renderer);

  // A user override from storage wins.
  const override = storage.get('quality', 'auto');
  if (override && override !== 'auto' && QUALITY_PRESETS[override]) {
    return { tier: override, reason: 'user', renderer, software };
  }
  if (software) return { tier: 'low', reason: 'software', renderer, software };
  if (LOW_GPU_RE.test(renderer)) return { tier: 'low', reason: 'low-gpu', renderer, software };
  if (coarse && ((memory ?? 4) <= 3 || (cores ?? 4) <= 4)) return { tier: 'low', reason: 'low-device', renderer, software };
  if (!coarse && HIGH_GPU_RE.test(renderer) && (memory === undefined || memory >= 8)) {
    return { tier: 'high', reason: 'high-gpu', renderer, software };
  }
  return { tier: 'medium', reason: renderer ? 'default' : 'masked', renderer, software };
}

const WINDOW_MS = 2000;
const IGNORE_MS = 4000;
const SAMPLE_CAP = 1024;

function nowMs() {
  return (globalThis.performance && performance.now) ? performance.now() : Date.now();
}

/**
 * Median-FPS governor (spec §12.2). Only ever lowers the tier; scales the pixel ratio both ways.
 * `onScale(pixelRatio)` receives the clamped pixel ratio to apply; `onTierDown()` asks for the next tier down.
 */
export class FpsGovernor {
  constructor({ preset, onScale = () => {}, onTierDown = () => {} }) {
    this.preset = preset || QUALITY_PRESETS.medium;
    this.onScale = onScale;
    this.onTierDown = onTierDown;
    this.scale = 1;
    this._buf = new Float32Array(SAMPLE_CAP);
    this._sort = new Float32Array(SAMPLE_CAP);
    this._n = 0;
    this._winStart = -1;
    this._ignoreUntil = 0;
    this._paused = false;
    this._hidden = false;
    this._slow = 0;
    this._fast = 0;
    this._floorSlow = 0;
    this.lastMedian = 0;
    this.reset();
  }

  /** Switches to another preset (after a tier change); the pixel scale restarts at 1. */
  setPreset(preset) {
    this.preset = preset;
    this.scale = 1;
    this.reset();
  }

  /** Forgets the current window and ignores the next 4 s. */
  reset() {
    this._n = 0;
    this._winStart = -1;
    this._ignoreUntil = nowMs() + IGNORE_MS;
    this._slow = 0;
    this._fast = 0;
    this._floorSlow = 0;
  }

  pause(paused) {
    paused = !!paused;
    if (paused === this._paused) return;
    this._paused = paused;
    if (!paused) this.reset();
  }

  /** Current pixel ratio = clamp(devicePixelRatio * scale, min, max). */
  get pixelRatio() {
    const dpr = (globalThis.devicePixelRatio || 1);
    const p = this.preset;
    return Math.min(p.pixelRatioMax, Math.max(p.pixelRatioMin, dpr * this.scale));
  }

  /** Feeds one rendered-frame interval (ms). */
  sample(frameIntervalMs) {
    const hidden = typeof document !== 'undefined' && document.hidden;
    if (hidden) { this._hidden = true; this._n = 0; this._winStart = -1; return; }
    if (this._hidden) { this._hidden = false; this.reset(); return; }
    if (this._paused || !(frameIntervalMs > 0) || frameIntervalMs > 1000) return;
    const t = nowMs();
    if (t < this._ignoreUntil) return;
    if (this._winStart < 0) this._winStart = t;
    if (this._n < SAMPLE_CAP) this._buf[this._n++] = frameIntervalMs;
    if (t - this._winStart >= WINDOW_MS) {
      const n = this._n;
      this._n = 0;
      this._winStart = t;
      if (n >= 3) this._evaluate(this._median(n));
    }
  }

  _median(n) {
    const s = this._sort;
    s.set(this._buf.subarray(0, n));
    const view = s.subarray(0, n);
    view.sort();
    return n % 2 ? view[(n - 1) >> 1] : 0.5 * (view[n / 2 - 1] + view[n / 2]);
  }

  _evaluate(median) {
    this.lastMedian = median;
    const p = this.preset;
    const budget = 1000 / p.targetFps;
    const dpr = (globalThis.devicePixelRatio || 1);
    if (median > budget * 1.25) {
      this._fast = 0;
      const atFloor = dpr * this.scale <= p.pixelRatioMin + 1e-3;
      if (!atFloor) {
        this._floorSlow = 0;
        if (++this._slow >= 2) {
          this._slow = 0;
          this.scale = Math.max(this.scale * 0.85, p.pixelRatioMin / dpr);
          this.onScale(this.pixelRatio);
        }
      } else if (++this._floorSlow >= 2) {
        this._floorSlow = 0;
        this._slow = 0;
        this.onTierDown();
      }
    } else if (median < budget * 0.7) {
      this._slow = 0;
      this._floorSlow = 0;
      if (++this._fast >= 5) {
        this._fast = 0;
        if (dpr * this.scale < p.pixelRatioMax - 1e-3) {
          this.scale = Math.min(this.scale * 1.1, p.pixelRatioMax / dpr);
          this.onScale(this.pixelRatio);
        }
      }
    } else {
      this._slow = 0;
      this._fast = 0;
      this._floorSlow = 0;
    }
  }
}

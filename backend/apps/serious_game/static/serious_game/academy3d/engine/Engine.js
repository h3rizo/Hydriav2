// engine/Engine.js — renderer, scene, camera, loop (fixed 60 Hz + time-based render throttle), resize, context loss,
// quality tiers and the FX singletons (spec §12.1–§12.3).
import * as THREE from 'three';
import { EV } from 'a3d/core/events.js';
import { TUNING } from 'a3d/core/tuning.js';
import { QUALITY_PRESETS, FpsGovernor, lowerTier } from 'a3d/engine/quality.js';
import { PALETTE } from 'a3d/render/palette.js';
import { MaterialFactory, setActiveEngine, getActiveEngine } from 'a3d/render/materials.js';
import { Lighting } from 'a3d/render/lighting.js';
import { Sky } from 'a3d/render/sky.js';
import { disposeWaterShared } from 'a3d/render/water.js';
import { disposePrototypes } from 'a3d/render/props/village.js';
import { Particles } from 'a3d/fx/particles.js';
import { IconLayer } from 'a3d/fx/IconLayer.js';
import { BlobShadows, LandingMarker, GuideTrail, disposeMarkerShared } from 'a3d/fx/markers.js';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function shadowMapType(q) {
  if (q.shadowType === 'PCFSoft') return THREE.PCFSoftShadowMap;
  return THREE.PCFShadowMap;
}

function isCoarse() {
  try { return !!(globalThis.matchMedia && globalThis.matchMedia('(pointer: coarse)').matches); } catch (_) { return false; }
}

function nowMs() {
  return (globalThis.performance && performance.now) ? performance.now() : Date.now();
}

export class Engine {
  /**
   * @param {{canvas:HTMLCanvasElement, container?:HTMLElement, bus?:import('a3d/core/EventBus.js').EventBus,
   *          tier?:'low'|'medium'|'high', settings?:object, debug?:boolean}} opts
   */
  constructor({ canvas, container, bus, tier = 'medium', settings = {}, debug = false }) {
    this.canvas = canvas;
    this.container = container || (canvas ? canvas.parentElement : null);
    this.bus = bus || null;
    this.settings = settings || {};
    this.debug = !!debug;
    this.tier = QUALITY_PRESETS[tier] ? tier : 'medium';
    this.quality = QUALITY_PRESETS[this.tier];

    this.scene = new THREE.Scene();
    this.scene.name = 'hydria3d';
    const cam = TUNING.camera;
    this.camera = new THREE.PerspectiveCamera(isCoarse() ? cam.fovTouch : cam.fovDesktop, 1, cam.near, cam.far);
    this.camera.rotation.order = 'YXZ';
    this.camera.position.set(0, 5, 10);
    this.scene.add(this.camera);

    this.renderer = null;
    this.materials = null;
    this.lighting = null;
    this.sky = null;
    this.post = null;
    this.governor = null;
    /** @type {{particles:Particles, icons:IconLayer, blobs:BlobShadows, landing:LandingMarker, guide:GuideTrail}|null} */
    this.fx = null;

    /** Rendered-frame counter (FX updates are idempotent per frame). */
    this.frame = 0;
    /** Game/FX clock in seconds (frozen while paused). */
    this.time = 0;
    this.width = 1;
    this.height = 1;
    this.pixelRatio = 1;
    this.paused = false;
    this.running = false;
    this.pendingTier = null;
    /**
     * Optional hook: when set, a governor tier-down is NOT applied immediately; the callback receives the next tier
     * and the owner (GameSession) applies it with setTier(tier, 'auto') at a convenient moment (spec §15.2).
     * SPEC-QUESTION: the spec does not name this hook; without it the engine applies the tier-down itself.
     * @type {((tier:string)=>void)|null}
     */
    this.onTierDownRequest = null;

    this._loop = null;
    this._env = { sky: 'matin', fogNear: null, fogFar: null };
    this._acc = 0;
    this._last = 0;
    this._lastRender = 0;
    this._raf = 0;
    this._inited = false;
    this._tierBusy = false;
    this._tierListeners = new Set();
    this._contextLost = false;
    this._wasRunning = false;
    this._statFrames = 0;
    this._statStart = 0;
    this._fps = 0;
    this._lastFov = this.camera.fov;
    this._projFrame = -1;
    this._projV = new THREE.Vector3();
    this._focus = new THREE.Vector3();
    this._tick = this._tick.bind(this);
    this._offSettings = null;
  }

  qualityFor(tier) {
    return QUALITY_PRESETS[tier] || QUALITY_PRESETS.medium;
  }

  get reducedMotion() {
    return !!(this.settings && this.settings.reducedMotion);
  }

  async init() {
    if (this._inited) return;
    const q = this.quality;
    const renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: !!(q.antialias && !q.bloom),
      alpha: false,
      stencil: false,
      depth: true,
      powerPreference: q.powerPreference || 'default',
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.setClearColor(new THREE.Color().setHex(PALETTE.SKY_HORIZON), 1);
    renderer.info.autoReset = false;
    renderer.shadowMap.enabled = !!q.shadows;
    renderer.shadowMap.type = shadowMapType(q);
    this.renderer = renderer;
    if (this.canvas && this.canvas.style) {
      this.canvas.style.display = 'block';
      this.canvas.style.width = '100%';
      this.canvas.style.height = '100%';
      this.canvas.style.touchAction = 'none';
    }

    setActiveEngine(this);
    this.materials = new MaterialFactory(this);
    await this.materials.prepare(this.tier);
    this.materials.setTier(this.tier);

    this.lighting = new Lighting(this);
    this.lighting.applyQuality(q);
    this.sky = new Sky(this);
    this.sky.applyQuality(q);
    this.sky.applyEnvironment(this._env, q);

    this.fx = {
      particles: new Particles(this, q.particleCapacity),
      icons: new IconLayer(this),
      blobs: new BlobShadows(this),
      landing: new LandingMarker(this),
      guide: new GuideTrail(this),
    };
    await this.fx.icons.init();

    this.governor = new FpsGovernor({
      preset: q,
      onScale: (pr) => this._applySize(this.width, this.height, pr),
      onTierDown: () => this._requestTierDown(),
    });

    if (q.bloom) await this._ensurePost();

    this._observeResize();
    this._resize();
    this._bindContext();
    if (this.bus) {
      this._offSettings = this.bus.on(EV.SETTINGS_CHANGED, (p) => { if (p && p.settings) this.settings = p.settings; });
    }
    this._inited = true;
    if (this.bus) this.bus.emit(EV.ENGINE_TIER, { tier: this.tier, reason: 'boot' });
  }

  // -------------------------------------------------------------------------------------------
  // Loop
  // -------------------------------------------------------------------------------------------

  /** loop = { beginFrame(dt), fixedUpdate(dt), update(dt, alpha) } */
  setLoop(loop) {
    this._loop = loop || null;
  }

  start() {
    if (this.running || !this.renderer || this._contextLost) return;
    this.running = true;
    this._last = nowMs();
    this._lastRender = 0;
    this._acc = 0;
    this._statStart = this._last;
    this._statFrames = 0;
    this._raf = requestAnimationFrame(this._tick);
  }

  stop() {
    this.running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = 0;
  }

  /** Paused: fixedUpdate skipped, update(dt, 1) still runs, render ≤ 10 fps. */
  setPaused(paused) {
    const p = !!paused;
    if (p === this.paused) return;
    this.paused = p;
    if (this.governor) this.governor.pause(p);
  }

  _tick(now) {
    if (!this.running) return;
    this._raf = requestAnimationFrame(this._tick);
    const target = this.paused ? 10 : this.quality.targetFps;
    if (this._lastRender && now - this._lastRender < 1000 / target - 3) return;   // time-based render throttle
    const interval = this._lastRender ? now - this._lastRender : 0;
    this._lastRender = now;
    const dt = clamp((now - this._last) / 1000, 0, TUNING.maxFrameDt ?? 0.1);
    this._last = now;
    this._frame(dt, interval, now);
  }

  _frame(dt, interval, now) {
    this.frame++;
    const loop = this._loop;
    try {
      if (loop && loop.beginFrame) loop.beginFrame(dt);
      let alpha = 1;
      if (!this.paused) {
        const fixed = TUNING.fixedDt || 1 / 60;
        const maxSteps = TUNING.maxStepsPerFrame || 5;
        this._acc += dt;
        let steps = 0;
        while (this._acc >= fixed && steps < maxSteps) {
          if (loop && loop.fixedUpdate) loop.fixedUpdate(fixed);
          this._acc -= fixed;
          steps++;
        }
        if (this._acc >= fixed) this._acc %= fixed;    // excess accumulator is dropped
        alpha = this._acc / fixed;
      }
      if (loop && loop.update) loop.update(dt, alpha);
    } catch (e) {
      console.error('[a3d] boucle de jeu', e);
    }
    if (!this.renderer || !this.fx) return;     // disposed from inside the loop (quit)

    const fxDt = this.paused ? 0 : dt;
    this.time += fxDt;
    this.materials.update(this.time);
    this.sky.update(dt, this.camera);
    this.lighting.update();
    if (this.camera.fov !== this._lastFov) {
      this._lastFov = this.camera.fov;
      this.fx.particles.setViewport(this.height * this.pixelRatio, this.camera.fov);
    }
    const fx = this.fx;
    fx.particles.update(fxDt);
    fx.icons.update(this.time);
    fx.guide.update(fxDt);
    fx.blobs.update();
    if (!this.paused && interval > 0) this.governor.sample(interval);
    this._render(dt);
    this._stats(now);
  }

  _render(dt) {
    const r = this.renderer;
    r.info.reset();
    if (this.post) this.post.render(dt);
    else r.render(this.scene, this.camera);
  }

  _stats(now) {
    this._statFrames++;
    const el = now - this._statStart;
    if (el >= 1000) {
      this._fps = Math.round((this._statFrames * 1000) / el);
      this._statFrames = 0;
      this._statStart = now;
      if (this.debug && this.bus) this.bus.emit(EV.ENGINE_STATS, this.getStats());
    }
  }

  getStats() {
    const info = this.renderer ? this.renderer.info : null;
    return {
      fps: this._fps,
      drawCalls: info ? info.render.calls : 0,
      triangles: info ? info.render.triangles : 0,
      tier: this.tier,
      pixelRatio: Math.round(this.pixelRatio * 100) / 100,
    };
  }

  // -------------------------------------------------------------------------------------------
  // Environment, focus, compile
  // -------------------------------------------------------------------------------------------

  /** theme: {sky:'matin'|'midi', fogNear:number|null, fogFar:number|null} (null = tier default). */
  setEnvironment({ sky = 'matin', fogNear = null, fogFar = null } = {}) {
    this._env = { sky, fogNear, fogFar };
    if (this.sky) this.sky.applyEnvironment(this._env, this.quality);
  }

  /** Shadow camera follow target (player render position). */
  setFocus(v) {
    if (!v) return;
    this._focus.set(v.x, v.y, v.z);
    if (this.lighting) this.lighting.setFocus(this._focus);
  }

  async compile() {
    const r = this.renderer;
    if (!r) return;
    try {
      this.camera.updateMatrixWorld();
      if (typeof r.compileAsync === 'function') await r.compileAsync(this.scene, this.camera);
      else r.compile(this.scene, this.camera);
    } catch (e) {
      console.warn('[a3d] compilation des shaders', e);
    }
  }

  // -------------------------------------------------------------------------------------------
  // Quality tiers
  // -------------------------------------------------------------------------------------------

  /** Called after each applied tier change with (quality, tier). Returns an unsubscribe function. */
  addTierListener(fn) {
    this._tierListeners.add(fn);
    return () => this._tierListeners.delete(fn);
  }

  _requestTierDown() {
    const next = lowerTier(this.tier);
    if (!next) return;
    this.pendingTier = next;
    if (typeof this.onTierDownRequest === 'function') this.onTierDownRequest(next);
    else this.setTier(next, 'auto');
  }

  async _ensurePost() {
    if (this.post || !this.renderer) return;
    try {
      const mod = await import('a3d/render/post.js');
      this.post = new mod.PostFX(this);
      this.post.setSize(this.width, this.height, this.pixelRatio);
    } catch (e) {
      console.warn('[a3d] post-traitement indisponible', e);
      this.post = null;
    }
  }

  /**
   * Emits ENGINE_TIER (P5 fades #a3d-fade to white over 200 ms), waits 200 ms, then rebuilds tier-dependent
   * materials, shadows, sky, particles, post and compiles. reason: 'auto' | 'user' | 'boot'.
   */
  async setTier(tier, reason = 'user') {
    if (!QUALITY_PRESETS[tier] || !this.renderer || this._tierBusy) return;
    if (tier === this.tier) return;
    this._tierBusy = true;
    try {
      if (this.bus) this.bus.emit(EV.ENGINE_TIER, { tier, reason });
      await new Promise((r) => setTimeout(r, 200));
      const q = QUALITY_PRESETS[tier];
      this.tier = tier;
      this.quality = q;
      this.pendingTier = null;
      await this.materials.prepare(tier);
      this.materials.setTier(tier);
      const r = this.renderer;
      r.shadowMap.enabled = !!q.shadows;
      r.shadowMap.type = shadowMapType(q);
      r.shadowMap.needsUpdate = true;
      this.lighting.applyQuality(q);
      this.sky.applyQuality(q);
      this.sky.applyEnvironment(this._env, q);
      this.fx.particles.setCapacity(q.particleCapacity);
      if (q.bloom && !this.post) await this._ensurePost();
      else if (!q.bloom && this.post) { this.post.dispose(); this.post = null; }
      this.governor.setPreset(q);
      this._resize();
      // shadow type / map changes alter program parameters: rebuild once
      this.scene.traverse((o) => {
        const m = o.material;
        if (!m) return;
        if (Array.isArray(m)) for (const mm of m) mm.needsUpdate = true;
        else m.needsUpdate = true;
      });
      for (const fn of this._tierListeners) {
        try { fn(q, tier); } catch (e) { console.error('[a3d] tier listener', e); }
      }
      await this.compile();
    } finally {
      this._tierBusy = false;
    }
  }

  // -------------------------------------------------------------------------------------------
  // Size, projection
  // -------------------------------------------------------------------------------------------

  _observeResize() {
    this._onWinResize = () => this._resize();
    window.addEventListener('resize', this._onWinResize);
    if (typeof ResizeObserver !== 'undefined' && this.container) {
      this._ro = new ResizeObserver(() => this._resize());
      this._ro.observe(this.container);
    }
  }

  _resize() {
    const el = this.container || this.canvas;
    if (!el) return;
    const w = Math.max(1, Math.floor(el.clientWidth || 1));
    const h = Math.max(1, Math.floor(el.clientHeight || 1));
    const pr = this.governor ? this.governor.pixelRatio
      : clamp(globalThis.devicePixelRatio || 1, this.quality.pixelRatioMin, this.quality.pixelRatioMax);
    this._applySize(w, h, pr);
  }

  _applySize(w, h, pr) {
    if (!this.renderer) return;
    this.width = w;
    this.height = h;
    this.pixelRatio = pr;
    this.renderer.setPixelRatio(pr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.post) this.post.setSize(w, h, pr);
    if (this.fx) this.fx.particles.setViewport(h * pr, this.camera.fov);
    this._lastFov = this.camera.fov;
  }

  /**
   * Projects a world point to CSS pixels relative to the container.
   * out = {x, y, visible}; visible = in front of the camera and inside the viewport.
   */
  project(pos, out = { x: 0, y: 0, visible: false }) {
    if (this._projFrame !== this.frame) {
      this._projFrame = this.frame;
      this.camera.updateMatrixWorld();
    }
    const v = this._projV.set(pos.x, pos.y, pos.z).applyMatrix4(this.camera.matrixWorldInverse);
    const inFront = v.z < -this.camera.near;
    v.applyMatrix4(this.camera.projectionMatrix);
    out.x = (v.x * 0.5 + 0.5) * this.width;
    out.y = (-v.y * 0.5 + 0.5) * this.height;
    out.visible = inFront && v.x >= -1 && v.x <= 1 && v.y >= -1 && v.y <= 1;
    return out;
  }

  // -------------------------------------------------------------------------------------------
  // Context loss
  // -------------------------------------------------------------------------------------------

  _bindContext() {
    this._onLost = (e) => {
      e.preventDefault();
      this._contextLost = true;
      this._wasRunning = this.running;
      this.stop();
      if (this.bus) this.bus.emit(EV.ENGINE_CONTEXT_LOST, {});
    };
    this._onRestored = async () => {
      this._contextLost = false;
      await this.compile();
      if (this.bus) this.bus.emit(EV.ENGINE_CONTEXT_RESTORED, {});
      if (this._wasRunning || this._loop) this.start();
    };
    this.canvas.addEventListener('webglcontextlost', this._onLost, false);
    this.canvas.addEventListener('webglcontextrestored', this._onRestored, false);
  }

  dispose() {
    this.stop();
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
    if (this._onWinResize) window.removeEventListener('resize', this._onWinResize);
    if (this.canvas && this._onLost) {
      this.canvas.removeEventListener('webglcontextlost', this._onLost);
      this.canvas.removeEventListener('webglcontextrestored', this._onRestored);
    }
    if (this._offSettings) { this._offSettings(); this._offSettings = null; }
    this._tierListeners.clear();
    if (this.fx) {
      this.fx.particles.dispose();
      this.fx.icons.dispose();
      this.fx.blobs.dispose();
      this.fx.landing.dispose();
      this.fx.guide.dispose();
      this.fx = null;
    }
    if (this.post) { this.post.dispose(); this.post = null; }
    if (this.sky) { this.sky.dispose(); this.sky = null; }
    if (this.lighting) { this.lighting.dispose(); this.lighting = null; }
    if (this.materials) { this.materials.dispose(); this.materials = null; }
    disposeWaterShared();
    disposeMarkerShared();
    disposePrototypes();
    if (this.renderer) {
      this.renderer.dispose();
      this.renderer.forceContextLoss();
      this.renderer = null;
    }
    if (getActiveEngine() === this) setActiveEngine(null);
    this._loop = null;
  }
}

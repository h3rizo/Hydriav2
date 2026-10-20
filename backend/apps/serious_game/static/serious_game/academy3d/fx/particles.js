// fx/particles.js — two pooled Points systems (additive + alpha), CPU ring buffer, presets (spec §12.4).
// No per-frame allocations: particle state lives in typed arrays; uploads use addUpdateRange.
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';

const SHAPE = { SOFT: 0, STAR: 1, SOLID: 2, COIN: 3 };

/**
 * Preset fields: pool 'add'|'alpha', count, rate (continuous, per second), life [min,max], speed [min,max],
 * pattern 'sphere'|'ring'|'cone', up (vertical bias), spread (cone half-angle, rad), gravity (m/s², +down),
 * drag (1/s), size [min,max] (m), sizeEnd (multiplier at end of life), colors [hex], alpha, shape, radius (spawn jitter).
 */
export const PARTICLE_PRESETS = Object.freeze({
  sparkle: { pool: 'add', count: 14, rate: 20, life: [0.45, 0.85], speed: [1.4, 3.2], pattern: 'sphere', up: 1.0, gravity: -1.5, drag: 2.6,
             size: [0.16, 0.3], sizeEnd: 0.1, colors: [PALETTE.HYDRIA_CYAN, PALETTE.SPARK, 0xffffff], alpha: 1, shape: SHAPE.STAR, radius: 0.15 },
  dust: { pool: 'alpha', count: 10, rate: 12, life: [0.45, 0.75], speed: [1.1, 2.3], pattern: 'ring', up: 0.45, gravity: -0.6, drag: 4.5,
          size: [0.24, 0.42], sizeEnd: 1.8, colors: [PALETTE.DUST, 0xd9b48c], alpha: 0.7, shape: SHAPE.SOFT, radius: 0.2 },
  runDust: { pool: 'alpha', count: 2, rate: 10, life: [0.3, 0.5], speed: [0.3, 0.8], pattern: 'ring', up: 0.6, gravity: -0.4, drag: 3.5,
             size: [0.14, 0.24], sizeEnd: 1.9, colors: [PALETTE.DUST], alpha: 0.5, shape: SHAPE.SOFT, radius: 0.1 },
  splash: { pool: 'alpha', count: 16, rate: 25, life: [0.5, 0.9], speed: [1.8, 3.8], pattern: 'cone', spread: 0.75, up: 1.0, gravity: 12, drag: 0.6,
            size: [0.09, 0.18], sizeEnd: 0.6, colors: [0xffffff, 0xbfefff, PALETTE.WATER_SHALLOW], alpha: 0.95, shape: SHAPE.SOLID, radius: 0.25 },
  confetti: { pool: 'alpha', count: 40, rate: 30, life: [1.3, 2.2], speed: [3.0, 6.0], pattern: 'cone', spread: 0.6, up: 1.0, gravity: 5.5, drag: 1.7,
              size: [0.11, 0.17], sizeEnd: 0.8, colors: PALETTE.CONFETTI, alpha: 1, shape: SHAPE.SOLID, radius: 0.3 },
  steam: { pool: 'alpha', count: 1, rate: 6, life: [1.0, 1.7], speed: [0.2, 0.5], pattern: 'cone', spread: 0.35, up: 1.0, gravity: -0.9, drag: 0.6,
           size: [0.22, 0.36], sizeEnd: 3.2, colors: [PALETTE.STEAM, 0xe8f1f6], alpha: 0.42, shape: SHAPE.SOFT, radius: 0.08 },
  coins: { pool: 'alpha', count: 8, rate: 10, life: [0.7, 1.0], speed: [1.4, 2.6], pattern: 'cone', spread: 0.5, up: 1.0, gravity: 14, drag: 0.4,
           size: [0.17, 0.23], sizeEnd: 0.9, colors: [PALETTE.COIN, 0xffe08a], alpha: 1, shape: SHAPE.COIN, radius: 0.15 },
  jet: { pool: 'alpha', count: 1, rate: 42, life: [0.42, 0.66], speed: [3.4, 4.4], pattern: 'cone', spread: 0.12, up: 0.0, gravity: 9.5, drag: 0.3,
         size: [0.1, 0.17], sizeEnd: 1.6, colors: [0xffffff, 0xbfefff, PALETTE.WATER_SHALLOW], alpha: 0.9, shape: SHAPE.SOLID, radius: 0.03 },
  glideMist: { pool: 'add', count: 1, rate: 28, life: [0.3, 0.5], speed: [0.2, 0.6], pattern: 'sphere', up: 0.0, gravity: -0.4, drag: 2.0,
               size: [0.18, 0.28], sizeEnd: 2.0, colors: [0xbff4ff, 0xffffff], alpha: 0.35, shape: SHAPE.SOFT, radius: 0.08 },
});

const VERT = /* glsl */`
attribute vec4 aColor;
attribute vec2 aSize;
uniform float uScale;
varying vec4 vColor;
varying float vShape;
varying float vFogDepth;
void main() {
  vColor = aColor;
  vShape = aSize.y;
  vec4 mv = modelViewMatrix * vec4( position, 1.0 );
  gl_Position = projectionMatrix * mv;
  gl_PointSize = clamp( aSize.x * uScale / max( 0.1, -mv.z ), 0.0, 256.0 );
  vFogDepth = -mv.z;
}`;

const FRAG = /* glsl */`
uniform vec3 fogColor;
uniform float fogNear;
uniform float fogFar;
varying vec4 vColor;
varying float vShape;
varying float vFogDepth;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = length( c ) * 2.0;
  vec3 col = vColor.rgb;
  float a;
  if ( vShape < 0.5 ) {
    a = 1.0 - smoothstep( 0.3, 1.0, d );
  } else if ( vShape < 1.5 ) {
    float star = max( 0.0, 1.0 - abs( c.x * c.y ) * 90.0 ) * ( 1.0 - smoothstep( 0.55, 1.0, d ) );
    float core = 1.0 - smoothstep( 0.0, 0.45, d );
    a = max( star, core );
    col = mix( col, vec3( 1.0 ), core * 0.6 );
  } else if ( vShape < 2.5 ) {
    a = 1.0 - smoothstep( 0.78, 1.0, d );
    col += 0.18 * ( 1.0 - smoothstep( 0.0, 0.5, length( c - vec2( -0.15, -0.15 ) ) * 2.0 ) );
  } else {
    a = 1.0 - smoothstep( 0.82, 1.0, d );
    col *= mix( 1.0, 0.7, smoothstep( 0.55, 0.7, d ) );
    col += 0.3 * ( 1.0 - smoothstep( 0.0, 0.4, length( c - vec2( -0.14, -0.14 ) ) * 2.0 ) );
  }
  a *= vColor.a;
  #ifdef USE_FOG
    a *= 1.0 - smoothstep( fogNear, fogFar, vFogDepth );
  #endif
  gl_FragColor = vec4( col, clamp( a, 0.0, 1.0 ) );
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

const _c = new THREE.Color();

class Pool {
  constructor(capacity, blending, scaleUniform) {
    this.capacity = Math.max(8, capacity | 0);
    const n = this.capacity;
    this.pos = new Float32Array(n * 3);
    this.vel = new Float32Array(n * 3);
    this.age = new Float32Array(n);
    this.life = new Float32Array(n);
    this.size0 = new Float32Array(n);
    this.size1 = new Float32Array(n);
    this.rgba = new Float32Array(n * 4);
    this.grav = new Float32Array(n);
    this.drag = new Float32Array(n);
    this.shape = new Float32Array(n);
    this.next = 0;
    this.high = 0;
    this.live = 0;
    const g = new THREE.BufferGeometry();
    this.aPos = new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage);
    this.aCol = new THREE.BufferAttribute(new Float32Array(n * 4), 4).setUsage(THREE.DynamicDrawUsage);
    this.aSize = new THREE.BufferAttribute(new Float32Array(n * 2), 2).setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('position', this.aPos);
    g.setAttribute('aColor', this.aCol);
    g.setAttribute('aSize', this.aSize);
    g.setDrawRange(0, 0);
    this.geometry = g;
    this._attrs = [this.aPos, this.aCol, this.aSize];
    this.material = new THREE.ShaderMaterial({
      uniforms: { ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog), uScale: scaleUniform },
      vertexShader: VERT,
      fragmentShader: FRAG,
      transparent: true,
      depthWrite: false,
      blending,
      fog: true,
    });
    this.material.name = blending === THREE.AdditiveBlending ? 'particlesAdd' : 'particlesAlpha';
    this.points = new THREE.Points(g, this.material);
    this.points.frustumCulled = false;
    this.points.matrixAutoUpdate = false;
    this.points.renderOrder = blending === THREE.AdditiveBlending ? 22 : 21;
  }

  spawn(x, y, z, vx, vy, vz, life, s0, s1, r, g, b, a, grav, drag, shape) {
    const i = this.next;
    this.next = (this.next + 1) % this.capacity;
    if (i + 1 > this.high) this.high = i + 1;
    const i3 = i * 3, i4 = i * 4;
    this.pos[i3] = x; this.pos[i3 + 1] = y; this.pos[i3 + 2] = z;
    this.vel[i3] = vx; this.vel[i3 + 1] = vy; this.vel[i3 + 2] = vz;
    this.age[i] = 0; this.life[i] = life;
    this.size0[i] = s0; this.size1[i] = s1;
    this.rgba[i4] = r; this.rgba[i4 + 1] = g; this.rgba[i4 + 2] = b; this.rgba[i4 + 3] = a;
    this.grav[i] = grav; this.drag[i] = drag; this.shape[i] = shape;
  }

  update(dt) {
    const n = this.high;
    if (n === 0) return;
    const P = this.aPos.array, C = this.aCol.array, S = this.aSize.array;
    let live = 0;
    for (let i = 0; i < n; i++) {
      const life = this.life[i];
      let age = this.age[i];
      const i3 = i * 3, i4 = i * 4, i2 = i * 2;
      if (life <= 0 || age >= life) {
        S[i2] = 0; C[i4 + 3] = 0;
        continue;
      }
      age += dt;
      this.age[i] = age;
      if (age >= life) { this.life[i] = 0; S[i2] = 0; C[i4 + 3] = 0; continue; }
      live++;
      const damp = Math.max(0, 1 - this.drag[i] * dt);
      let vx = this.vel[i3] * damp, vy = (this.vel[i3 + 1] - this.grav[i] * dt) * damp, vz = this.vel[i3 + 2] * damp;
      this.vel[i3] = vx; this.vel[i3 + 1] = vy; this.vel[i3 + 2] = vz;
      const px = this.pos[i3] + vx * dt, py = this.pos[i3 + 1] + vy * dt, pz = this.pos[i3 + 2] + vz * dt;
      this.pos[i3] = px; this.pos[i3 + 1] = py; this.pos[i3 + 2] = pz;
      const t = age / life;
      const pop = t < 0.08 ? 0.4 + 0.6 * (t / 0.08) : 1;
      const size = (this.size0[i] + (this.size1[i] - this.size0[i]) * t) * pop;
      const fade = t < 0.6 ? 1 : 1 - (t - 0.6) / 0.4;
      P[i3] = px; P[i3 + 1] = py; P[i3 + 2] = pz;
      C[i4] = this.rgba[i4]; C[i4 + 1] = this.rgba[i4 + 1]; C[i4 + 2] = this.rgba[i4 + 2]; C[i4 + 3] = this.rgba[i4 + 3] * fade;
      S[i2] = size; S[i2 + 1] = this.shape[i];
    }
    this.live = live;
    if (live === 0) {
      this.high = 0;
      this.next = 0;
      this.geometry.setDrawRange(0, 0);
      return;
    }
    this.geometry.setDrawRange(0, n);
    for (let k = 0; k < 3; k++) {
      const a = this._attrs[k];
      a.clearUpdateRanges();
      a.addUpdateRange(0, n * a.itemSize);
      a.needsUpdate = true;
    }
  }

  dispose() {
    if (this.points.parent) this.points.parent.remove(this.points);
    this.geometry.dispose();
    this.material.dispose();
  }
}

const _wp = new THREE.Vector3();
const _wd = new THREE.Vector3();
const _off = new THREE.Vector3();
const _base = new THREE.Vector3();
const _tmp = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _yAxis = new THREE.Vector3(0, 1, 0);

export class Particles {
  constructor(engine, capacity) {
    this.engine = engine;
    this.uScale = { value: 600 };
    this._emitters = [];
    this._lastFrame = -1;
    this.setCapacity(capacity || 512);
  }

  /** (Re)allocates both pools; live particles are dropped. */
  setCapacity(capacity) {
    const cap = Math.max(32, capacity | 0);
    if (this.add) this.add.dispose();
    if (this.alpha) this.alpha.dispose();
    this.capacity = cap;
    this.add = new Pool(Math.round(cap * 0.4), THREE.AdditiveBlending, this.uScale);
    this.alpha = new Pool(cap - Math.round(cap * 0.4), THREE.NormalBlending, this.uScale);
    this.engine.scene.add(this.alpha.points, this.add.points);
  }

  /** Pixels per metre at distance 1: drawingBufferHeight / (2 tan(fov/2)). Called on resize. */
  setViewport(drawingBufferHeight, fovDeg) {
    this.uScale.value = drawingBufferHeight / (2 * Math.tan(THREE.MathUtils.degToRad(fovDeg) / 2));
  }

  _countScale() {
    const s = this.engine.settings;
    return s && s.reducedMotion ? 0.5 : 1;
  }

  /**
   * One-shot burst. `pos` = {x,y,z} | [x,y,z]. opts: count, color (hex), colors, scale, speed (multiplier),
   * dir ({x,y,z}, used by 'cone'), spread, life (multiplier), gravity.
   */
  emit(preset, pos, opts = {}) {
    const p = PARTICLE_PRESETS[preset];
    if (!p || !pos) return;
    const x = Array.isArray(pos) ? pos[0] : pos.x, y = Array.isArray(pos) ? pos[1] : pos.y, z = Array.isArray(pos) ? pos[2] : pos.z;
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return;
    const n = Math.max(1, Math.round((opts.count ?? p.count) * this._countScale()));
    if (opts.dir) _base.set(opts.dir.x ?? opts.dir[0] ?? 0, opts.dir.y ?? opts.dir[1] ?? 1, opts.dir.z ?? opts.dir[2] ?? 0);
    else _base.set(0, 1, 0);
    if (_base.lengthSq() < 1e-8) _base.set(0, 1, 0);
    _base.normalize();
    for (let i = 0; i < n; i++) this._spawn(p, x, y, z, _base, opts);
  }

  _spawn(p, x, y, z, dir, opts) {
    const pool = p.pool === 'add' ? this.add : this.alpha;
    const rnd = Math.random;
    const spMul = opts.speed ?? 1;
    const speed = (p.speed[0] + (p.speed[1] - p.speed[0]) * rnd()) * spMul;
    let vx, vy, vz;
    if (p.pattern === 'sphere') {
      const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2, s = Math.sqrt(1 - u * u);
      vx = s * Math.cos(th); vy = u; vz = s * Math.sin(th);
      vy += p.up;
      const l = Math.hypot(vx, vy, vz) || 1;
      vx = vx / l * speed; vy = vy / l * speed; vz = vz / l * speed;
    } else if (p.pattern === 'ring') {
      const th = rnd() * Math.PI * 2;
      vx = Math.cos(th) * speed; vz = Math.sin(th) * speed; vy = p.up * speed * (0.6 + 0.4 * rnd());
    } else {
      // cone around dir
      const spread = opts.spread ?? p.spread ?? 0.5;
      const a = rnd() * spread, th = rnd() * Math.PI * 2;
      _tmp.set(Math.sin(a) * Math.cos(th), Math.cos(a), Math.sin(a) * Math.sin(th));
      _q.setFromUnitVectors(_yAxis, dir);
      _tmp.applyQuaternion(_q);
      vx = _tmp.x * speed; vy = _tmp.y * speed; vz = _tmp.z * speed;
    }
    const rad = p.radius || 0;
    const ox = (rnd() * 2 - 1) * rad, oy = (rnd() * 2 - 1) * rad * 0.5, oz = (rnd() * 2 - 1) * rad;
    const lifeMul = opts.life ?? 1;
    const life = (p.life[0] + (p.life[1] - p.life[0]) * rnd()) * lifeMul;
    const scale = opts.scale ?? 1;
    const s0 = (p.size[0] + (p.size[1] - p.size[0]) * rnd()) * scale;
    const colors = opts.colors || p.colors;
    _c.setHex(opts.color ?? colors[Math.floor(rnd() * colors.length) % colors.length]);
    pool.spawn(x + ox, y + oy, z + oz, vx, vy, vz, life, s0, s0 * p.sizeEnd,
      _c.r, _c.g, _c.b, opts.alpha ?? p.alpha, opts.gravity ?? p.gravity, p.drag, p.shape);
  }

  /**
   * Continuous emitter attached to an Object3D. opts: rate (per second), offset ({x,y,z} local), dir ({x,y,z} local),
   * plus emit() options. Returns {stop()}.
   */
  addContinuous(preset, anchor, opts = {}) {
    const p = PARTICLE_PRESETS[preset];
    const em = { preset: p, anchor, opts, rate: opts.rate ?? (p ? p.rate : 10), acc: 0, alive: !!p };
    const ofs = opts.offset;
    em.offset = ofs ? new THREE.Vector3(ofs.x ?? ofs[0] ?? 0, ofs.y ?? ofs[1] ?? 0, ofs.z ?? ofs[2] ?? 0) : null;
    const d = opts.dir;
    em.dir = d ? new THREE.Vector3(d.x ?? d[0] ?? 0, d.y ?? d[1] ?? 1, d.z ?? d[2] ?? 0).normalize() : new THREE.Vector3(0, 1, 0);
    if (em.alive) this._emitters.push(em);
    return { stop: () => { em.alive = false; } };
  }

  /** Simulates both pools and continuous emitters; called by the Engine each frame (idempotent per frame). */
  update(dt) {
    const frame = this.engine.frame;
    if (frame === this._lastFrame) return;
    this._lastFrame = frame;
    if (dt > 0 && this._emitters.length) {
      const scale = this._countScale();
      for (let i = this._emitters.length - 1; i >= 0; i--) {
        const em = this._emitters[i];
        if (!em.alive) { this._emitters.splice(i, 1); continue; }
        const a = em.anchor;
        if (!a || !a.parent || !a.visible) { em.acc = 0; continue; }
        em.acc += em.rate * scale * dt;
        if (em.acc < 1) continue;
        a.updateWorldMatrix(true, false);
        _wp.setFromMatrixPosition(a.matrixWorld);
        if (em.offset) { _off.copy(em.offset).applyMatrix4(a.matrixWorld); _wp.copy(_off); }
        _wd.copy(em.dir).transformDirection(a.matrixWorld);
        while (em.acc >= 1) {
          em.acc -= 1;
          this._spawn(em.preset, _wp.x, _wp.y, _wp.z, _wd, em.opts);
        }
      }
    }
    this.add.update(dt);
    this.alpha.update(dt);
  }

  /** Total live particles (debug). */
  get liveCount() {
    return this.add.live + this.alpha.live;
  }

  clear() {
    this._emitters.length = 0;
    this.add.life.fill(0);
    this.add.update(0);
    this.alpha.life.fill(0);
    this.alpha.update(0);
  }

  dispose() {
    this._emitters.length = 0;
    this.add.dispose();
    this.alpha.dispose();
  }
}

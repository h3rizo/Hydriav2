// fx/IconLayer.js — icon atlas (Font Awesome when loaded, canvas paths otherwise), instanced billboards and
// ground rings (spec §12.4). Also exports QuadBatch / createFxQuadMaterial, the single "fx quad" program shared
// by icons, rings, blob shadows, the landing marker and the guide trail (fx/markers.js).
import * as THREE from 'three';

// ---------------------------------------------------------------------------------------------
// Shared fx-quad program
// ---------------------------------------------------------------------------------------------

export const FX_MODE = Object.freeze({ ICON: 0, RING: 1, BLOB: 2, LANDING: 3, GUIDE: 4 });

const FX_VERT = /* glsl */`
attribute vec4 aOffset;   // xyz centre, w size (m)
attribute vec4 aColor;    // rgb linear, a opacity
attribute vec4 aParams;   // mode-specific
uniform float uTime;
uniform float uMode;
varying vec2 vUv;
varying vec4 vColor;
varying vec4 vParams;
varying float vFogDepth;
void main() {
  vUv = uv;
  vColor = aColor;
  vParams = aParams;
  vec3 c = aOffset.xyz;
  float size = aOffset.w;
  vec4 mv;
  if ( uMode < 0.5 ) {
    // icon billboard: bob + pulse
    float ph = aParams.z;
    c.y += sin( uTime * 2.2 + ph ) * 0.07;
    size *= 1.0 + 0.05 * sin( uTime * 3.6 + ph ) + aParams.w * 0.25 * max( 0.0, sin( uTime * 7.0 + ph ) );
    mv = viewMatrix * vec4( c, 1.0 );
    mv.xy += position.xy * size;
  } else if ( uMode > 3.5 ) {
    // guide dot billboard
    mv = viewMatrix * vec4( c, 1.0 );
    mv.xy += position.xy * size;
  } else {
    // flat on the ground (XZ)
    vec3 w = c + vec3( position.x * size, 0.0, -position.y * size );
    mv = viewMatrix * vec4( w, 1.0 );
  }
  vFogDepth = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

const FX_FRAG = /* glsl */`
uniform float uTime;
uniform float uMode;
uniform float uFogMix;
uniform sampler2D uMap;
uniform vec2 uGrid;
uniform vec3 fogColor;
uniform float fogNear;
uniform float fogFar;
varying vec2 vUv;
varying vec4 vColor;
varying vec4 vParams;
varying float vFogDepth;
void main() {
  vec2 c = vUv - 0.5;
  float d = length( c ) * 2.0;
  vec3 col = vColor.rgb;
  float alpha = vColor.a;
  if ( uMode < 0.5 ) {
    // ICON: white disc, tinted rim, tinted glyph from the atlas
    float disc = 1.0 - smoothstep( 0.90, 1.0, d );
    float rim = smoothstep( 0.72, 0.80, d );
    float cell = vParams.x;
    float cx = mod( cell, uGrid.x );
    float cy = floor( cell / uGrid.x );
    vec2 guv = ( vUv - 0.5 ) * 1.18 + 0.5;
    vec2 auv = vec2( ( cx + clamp( guv.x, 0.0, 1.0 ) ) / uGrid.x, ( uGrid.y - cy - 1.0 + clamp( guv.y, 0.0, 1.0 ) ) / uGrid.y );
    float glyph = texture2D( uMap, auv ).a * ( 1.0 - rim );
    vec3 base = mix( vec3( 1.0 ), vColor.rgb, rim );
    col = mix( base, vColor.rgb * 0.82, glyph );
    float shade = 1.0 - 0.10 * smoothstep( 0.2, 0.9, length( c - vec2( -0.12, 0.14 ) ) * 2.0 );
    col *= shade;
    alpha *= disc;
  } else if ( uMode < 1.5 ) {
    // RING: pulsing ring + soft fill + expanding wave
    float r = 0.84 + 0.05 * sin( uTime * 3.0 + vParams.z );
    float ring = 1.0 - smoothstep( 0.0, 0.09, abs( d - r ) );
    float fill = ( 1.0 - smoothstep( 0.0, 0.95, d ) ) * 0.16;
    float w = fract( uTime * 0.55 + vParams.z * 0.13 );
    float wave = ( 1.0 - smoothstep( 0.0, 0.07, abs( d - w ) ) ) * ( 1.0 - w ) * 0.7;
    alpha *= ( ring + fill + wave ) * step( d, 1.0 );
  } else if ( uMode < 2.5 ) {
    // BLOB: radial gradient texture
    alpha *= texture2D( uMap, vUv ).a;
  } else if ( uMode < 3.5 ) {
    // LANDING: ring + centre dot (ground) or warning cross (void)
    float pulse = 0.85 + 0.15 * sin( uTime * 8.0 );
    float ring = 1.0 - smoothstep( 0.0, 0.10, abs( d - 0.78 ) );
    float shape;
    if ( vParams.x < 0.5 ) {
      float dotc = 1.0 - smoothstep( 0.16, 0.24, d );
      shape = max( ring, dotc );
    } else {
      vec2 q = vec2( c.x + c.y, c.x - c.y ) * 0.7071;
      float cross = ( 1.0 - smoothstep( 0.04, 0.07, min( abs( q.x ), abs( q.y ) ) ) ) * step( d, 0.62 );
      shape = max( ring * 0.8, cross );
    }
    alpha *= shape * pulse;
  } else {
    // GUIDE: glowing dot with a wave flowing toward the path end
    float core = 1.0 - smoothstep( 0.25, 0.5, d );
    float glow = ( 1.0 - smoothstep( 0.0, 1.0, d ) ) * 0.45;
    float flow = 0.35 + 0.65 * pow( 0.5 + 0.5 * sin( vParams.y * 1.4 - uTime * 4.5 ), 3.0 );
    alpha *= ( core + glow ) * flow;
    col = mix( col, vec3( 1.0 ), core * 0.5 );
  }
  #ifdef USE_FOG
    float fogF = smoothstep( fogNear, fogFar, vFogDepth ) * uFogMix;
    if ( uMode < 0.5 ) col = mix( col, fogColor, fogF ); else alpha *= 1.0 - fogF;
  #endif
  gl_FragColor = vec4( col, clamp( alpha, 0.0, 1.0 ) );
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

let _blank = null;
function blankTexture() {
  if (!_blank) {
    _blank = new THREE.DataTexture(new Uint8Array([255, 255, 255, 0]), 1, 1, THREE.RGBAFormat);
    _blank.needsUpdate = true;
  }
  return _blank;
}

/**
 * Material for one fx-quad batch. All modes share one GLSL program (mode = uniform, toneMapped:false, fog on).
 * @param {{mode:number, map?:THREE.Texture, grid?:[number,number], blending?:number, fogMix?:number,
 *          depthTest?:boolean, polygonOffset?:boolean, timeUniform?:{value:number}}} opts
 */
export function createFxQuadMaterial(opts) {
  const uniforms = {
    ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
    uTime: opts.timeUniform || { value: 0 },
    uMode: { value: opts.mode },
    uFogMix: { value: opts.fogMix ?? 1 },
    uMap: { value: opts.map || blankTexture() },
    uGrid: { value: new THREE.Vector2(opts.grid ? opts.grid[0] : 1, opts.grid ? opts.grid[1] : 1) },
  };
  const m = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: FX_VERT,
    fragmentShader: FX_FRAG,
    transparent: true,
    depthWrite: false,
    depthTest: opts.depthTest ?? true,
    blending: opts.blending ?? THREE.NormalBlending,
    fog: true,
    toneMapped: false,
  });
  if (opts.polygonOffset) {
    m.polygonOffset = true;
    m.polygonOffsetFactor = -1;
    m.polygonOffsetUnits = -1;
  }
  m.name = 'fxquad';
  return m;
}


/**
 * Fixed-capacity instanced quad batch with a free list. Slots are written with set() and uploaded by flush().
 * Freed slots get opacity 0 / size 0. One draw call for the whole batch.
 */
export class QuadBatch {
  constructor(capacity, material, renderOrder = 10) {
    this.capacity = capacity;
    const g = new THREE.InstancedBufferGeometry();
    const q = new THREE.PlaneGeometry(1, 1);   // own copy: disposing one batch never frees another's buffers
    g.index = q.index;
    g.setAttribute('position', q.attributes.position);
    g.setAttribute('uv', q.attributes.uv);
    this.offset = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    this.color = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    this.params = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    this._attrs = [this.offset, this.color, this.params];
    for (const a of this._attrs) a.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('aOffset', this.offset);
    g.setAttribute('aColor', this.color);
    g.setAttribute('aParams', this.params);
    g.instanceCount = 0;
    this.geometry = g;
    this.material = material;
    this.mesh = new THREE.Mesh(g, material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = renderOrder;
    this.mesh.matrixAutoUpdate = false;
    this.mesh.castShadow = false;
    this.mesh.receiveShadow = false;
    this._free = [];
    for (let i = capacity - 1; i >= 0; i--) this._free.push(i);
    this._used = new Uint8Array(capacity);
    this._high = 0;
  }

  alloc() {
    const i = this._free.pop();
    if (i === undefined) return -1;
    this._used[i] = 1;
    if (i + 1 > this._high) this._high = i + 1;
    return i;
  }

  free(i) {
    if (i < 0 || i >= this.capacity || !this._used[i]) return;
    this._used[i] = 0;
    this.offset.array[i * 4 + 3] = 0;
    this.color.array[i * 4 + 3] = 0;
    this._free.push(i);
    while (this._high > 0 && !this._used[this._high - 1]) this._high--;
  }

  set(i, x, y, z, size, r, g, b, a, p0 = 0, p1 = 0, p2 = 0, p3 = 0) {
    const o = i * 4;
    const off = this.offset.array, col = this.color.array, par = this.params.array;
    off[o] = x; off[o + 1] = y; off[o + 2] = z; off[o + 3] = size;
    col[o] = r; col[o + 1] = g; col[o + 2] = b; col[o + 3] = a;
    par[o] = p0; par[o + 1] = p1; par[o + 2] = p2; par[o + 3] = p3;
  }

  hide(i) {
    const o = i * 4;
    this.offset.array[o + 3] = 0;
    this.color.array[o + 3] = 0;
  }

  flush() {
    const n = this._high;
    this.geometry.instanceCount = n;
    if (n === 0) return;
    for (let k = 0; k < 3; k++) {
      const a = this._attrs[k];
      a.clearUpdateRanges();
      a.addUpdateRange(0, n * 4);
      a.needsUpdate = true;
    }
  }

  dispose() {
    if (this.mesh.parent) this.mesh.parent.remove(this.mesh);
    this.geometry.dispose();
    this.material.dispose();
  }
}

// ---------------------------------------------------------------------------------------------
// Icon atlas
// ---------------------------------------------------------------------------------------------

export const ICON_KEYS = Object.freeze(['wrench', 'hourglass', 'check', 'coins', 'faucet_off', 'droplet', 'valve',
  'box', 'receipt', 'speech', 'flag', 'star', 'question', 'lock']);

// Font Awesome 6/5 Free Solid code points (null = always drawn with canvas paths).
const FA_GLYPHS = {
  wrench: '', hourglass: '', check: '', coins: '', faucet_off: '', droplet: '',
  valve: null, box: '', receipt: '', speech: '', flag: '', star: '', question: '', lock: '',
};

const CELL = 128;
const GRID = 4;

function drawFallback(ctx, key) {
  // All shapes drawn in a 100×100 box centred at the origin, white fill.
  ctx.fillStyle = '#fff';
  ctx.strokeStyle = '#fff';
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const rr = (x, y, w, h, r) => { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h); ctx.fill(); };
  switch (key) {
    case 'wrench': {
      ctx.save(); ctx.rotate(-Math.PI / 4);
      rr(-9, -10, 18, 58, 8);
      ctx.beginPath(); ctx.arc(0, -26, 22, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = 'destination-out';
      rr(-8, -52, 16, 28, 3);
      ctx.restore();
      break;
    }
    case 'hourglass':
      rr(-30, -46, 60, 10, 4); rr(-30, 36, 60, 10, 4);
      ctx.beginPath(); ctx.moveTo(-24, -36); ctx.lineTo(24, -36); ctx.lineTo(4, 0); ctx.lineTo(24, 36); ctx.lineTo(-24, 36); ctx.lineTo(-4, 0); ctx.closePath(); ctx.fill();
      break;
    case 'check':
      ctx.lineWidth = 16; ctx.beginPath(); ctx.moveTo(-34, 2); ctx.lineTo(-10, 26); ctx.lineTo(36, -24); ctx.stroke();
      break;
    case 'coins':
      for (const [x, y] of [[-14, 10], [14, -6], [-2, -22]]) {
        ctx.beginPath(); ctx.ellipse(x, y, 22, 22, 0, 0, Math.PI * 2); ctx.fill();
      }
      break;
    case 'faucet_off':
    case 'droplet': {
      ctx.beginPath(); ctx.moveTo(0, -44);
      ctx.bezierCurveTo(14, -20, 30, -2, 30, 16); ctx.arc(0, 16, 30, 0, Math.PI, false);
      ctx.bezierCurveTo(-30, -2, -14, -20, 0, -44); ctx.fill();
      if (key === 'faucet_off') {
        ctx.globalCompositeOperation = 'destination-out'; ctx.lineWidth = 18;
        ctx.beginPath(); ctx.moveTo(-40, -40); ctx.lineTo(40, 40); ctx.stroke();
        ctx.globalCompositeOperation = 'source-over'; ctx.lineWidth = 9;
        ctx.beginPath(); ctx.moveTo(-40, -40); ctx.lineTo(40, 40); ctx.stroke();
      }
      break;
    }
    case 'valve':
      ctx.lineWidth = 10;
      ctx.beginPath(); ctx.arc(0, -4, 32, 0, Math.PI * 2); ctx.stroke();
      for (let i = 0; i < 4; i++) {
        const a = i * Math.PI / 2 + Math.PI / 4;
        ctx.beginPath(); ctx.moveTo(0, -4); ctx.lineTo(Math.cos(a) * 32, -4 + Math.sin(a) * 32); ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(0, -4, 9, 0, Math.PI * 2); ctx.fill();
      rr(-6, 28, 12, 18, 3);
      break;
    case 'box':
      ctx.beginPath(); ctx.moveTo(0, -40); ctx.lineTo(38, -22); ctx.lineTo(38, 24); ctx.lineTo(0, 42); ctx.lineTo(-38, 24); ctx.lineTo(-38, -22); ctx.closePath(); ctx.fill();
      ctx.globalCompositeOperation = 'destination-out'; ctx.lineWidth = 5;
      ctx.beginPath(); ctx.moveTo(-38, -22); ctx.lineTo(0, -4); ctx.lineTo(38, -22); ctx.moveTo(0, -4); ctx.lineTo(0, 42); ctx.stroke();
      break;
    case 'receipt':
      ctx.beginPath(); ctx.moveTo(-30, -44); ctx.lineTo(30, -44); ctx.lineTo(30, 44);
      for (let i = 0; i < 6; i++) ctx.lineTo(30 - (i + 0.5) * 10, i % 2 ? 44 : 36);
      ctx.lineTo(-30, 44); ctx.closePath(); ctx.fill();
      ctx.globalCompositeOperation = 'destination-out';
      for (let i = 0; i < 4; i++) rr(-20, -32 + i * 16, i === 3 ? 22 : 40, 6, 3);
      break;
    case 'speech':
      ctx.beginPath(); ctx.ellipse(0, -6, 44, 34, 0, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(-24, 18); ctx.lineTo(-34, 44); ctx.lineTo(-2, 24); ctx.closePath(); ctx.fill();
      break;
    case 'flag':
      rr(-34, -44, 9, 90, 4);
      ctx.beginPath(); ctx.moveTo(-26, -40); ctx.bezierCurveTo(0, -52, 14, -26, 40, -36); ctx.lineTo(40, 6); ctx.bezierCurveTo(14, 16, 0, -10, -26, 2); ctx.closePath(); ctx.fill();
      break;
    case 'star': {
      ctx.beginPath();
      for (let i = 0; i < 10; i++) {
        const r = i % 2 ? 20 : 46;
        const a = -Math.PI / 2 + i * Math.PI / 5;
        ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r + 4);
      }
      ctx.closePath(); ctx.fill();
      break;
    }
    case 'question':
      ctx.lineWidth = 15;
      ctx.beginPath(); ctx.arc(0, -16, 22, Math.PI * 1.05, Math.PI * 2.25); ctx.lineTo(0, 14); ctx.stroke();
      ctx.beginPath(); ctx.arc(0, 36, 9, 0, Math.PI * 2); ctx.fill();
      break;
    case 'lock':
      ctx.lineWidth = 11;
      ctx.beginPath(); ctx.arc(0, -14, 20, Math.PI, 0); ctx.lineTo(20, 0); ctx.moveTo(-20, 0); ctx.lineTo(-20, -14); ctx.stroke();
      rr(-34, -2, 68, 46, 8);
      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath(); ctx.arc(0, 16, 7, 0, Math.PI * 2); ctx.fill(); rr(-3, 18, 6, 14, 2);
      break;
    default:
      ctx.beginPath(); ctx.arc(0, 0, 30, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalCompositeOperation = 'source-over';
}

async function fontAwesomeFamily() {
  if (typeof document === 'undefined' || !document.fonts || !document.fonts.load) return null;
  const families = ['Font Awesome 6 Free', 'Font Awesome 5 Free'];
  const attempt = (async () => {
    for (const fam of families) {
      try {
        // load() resolves with the matching faces; an empty list means the family is not declared on the page
        // (document.fonts.check() would wrongly report true in that case).
        const faces = await document.fonts.load(`900 48px "${fam}"`, '');
        if (faces && faces.length) return fam;
      } catch (_) { /* try next */ }
    }
    return null;
  })();
  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), 1500));
  return Promise.race([attempt, timeout]);
}

function buildAtlasCanvas(faFamily) {
  const canvas = document.createElement('canvas');
  canvas.width = CELL * GRID;
  canvas.height = CELL * GRID;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ICON_KEYS.forEach((key, idx) => {
    const cx = (idx % GRID) * CELL + CELL / 2;
    const cy = Math.floor(idx / GRID) * CELL + CELL / 2;
    ctx.save();
    ctx.translate(cx, cy);
    const glyph = FA_GLYPHS[key];
    if (faFamily && glyph) {
      ctx.fillStyle = '#fff';
      ctx.font = `900 64px "${faFamily}"`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(glyph, 0, 2);
      if (key === 'faucet_off') {
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 9; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(-36, -36); ctx.lineTo(36, 36); ctx.stroke();
      }
    } else {
      ctx.scale(0.7, 0.7);
      drawFallback(ctx, key);
    }
    ctx.restore();
  });
  return canvas;
}

// ---------------------------------------------------------------------------------------------
// IconLayer
// ---------------------------------------------------------------------------------------------

const ICON_CAPACITY = 64;
const RING_CAPACITY = 48;
const ICON_SIZE = 0.62;
const _wp = new THREE.Vector3();
const _tint = new THREE.Color();

export class IconLayer {
  constructor(engine) {
    this.engine = engine;
    const time = engine.materials.uTime;
    this.texture = null;
    this.iconMat = createFxQuadMaterial({ mode: FX_MODE.ICON, grid: [GRID, GRID], fogMix: 0.35, timeUniform: time });
    this.ringMat = createFxQuadMaterial({ mode: FX_MODE.RING, blending: THREE.AdditiveBlending, fogMix: 1, timeUniform: time, polygonOffset: true });
    this.icons = new QuadBatch(ICON_CAPACITY, this.iconMat, 30);
    this.rings = new QuadBatch(RING_CAPACITY, this.ringMat, 12);
    this._iconHandles = new Set();
    this._ringHandles = new Set();
    this._lastFrame = -1;
    engine.scene.add(this.rings.mesh, this.icons.mesh);
    this.ready = false;
  }

  async init() {
    let family = null;
    try { family = await fontAwesomeFamily(); } catch (_) { family = null; }
    try {
      const canvas = buildAtlasCanvas(family);
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.NoColorSpace;
      tex.minFilter = THREE.LinearMipmapLinearFilter;
      tex.magFilter = THREE.LinearFilter;
      tex.generateMipmaps = true;
      tex.anisotropy = 2;
      this.texture = tex;
      this.iconMat.uniforms.uMap.value = tex;
      this.fontAwesome = !!family;
    } catch (e) {
      console.warn('[a3d] atlas d’icônes indisponible', e);
    }
    this.ready = true;
  }

  /** Floating icon above `anchor` (Object3D). Returns {set(icon, tint), setVisible(b), remove()}. */
  add(anchor, offsetY, icon, tint) {
    const slot = this.icons.alloc();
    const h = {
      anchor, offsetY: offsetY || 0, cell: Math.max(0, ICON_KEYS.indexOf(icon)), visible: true, slot,
      r: 1, g: 1, b: 1, phase: Math.random() * 6.283, attention: 0,
      set: (newIcon, newTint) => {
        if (newIcon) h.cell = Math.max(0, ICON_KEYS.indexOf(newIcon));
        if (newTint !== undefined && newTint !== null) { _tint.setHex(newTint); h.r = _tint.r; h.g = _tint.g; h.b = _tint.b; }
        h.attention = newIcon === 'wrench' || newIcon === 'question' ? 1 : 0;
      },
      setVisible: (b) => { h.visible = !!b; },
      remove: () => {
        if (!this._iconHandles.has(h)) return;
        this._iconHandles.delete(h);
        if (h.slot >= 0) this.icons.free(h.slot);
      },
    };
    h.set(icon, tint ?? 0xffffff);
    if (slot >= 0) this._iconHandles.add(h);
    else console.warn('[a3d] IconLayer: capacité d’icônes atteinte');
    return h;
  }

  /** Pulsing ring on the ground under `anchor`. Returns {set(tint), setVisible(b), remove()}. */
  addRing(anchor, radius, tint) {
    const slot = this.rings.alloc();
    const h = {
      anchor, radius: radius || 1, visible: true, slot, r: 1, g: 1, b: 1, phase: Math.random() * 6.283,
      set: (newTint) => { _tint.setHex(newTint); h.r = _tint.r; h.g = _tint.g; h.b = _tint.b; },
      setVisible: (b) => { h.visible = !!b; },
      remove: () => {
        if (!this._ringHandles.has(h)) return;
        this._ringHandles.delete(h);
        if (h.slot >= 0) this.rings.free(h.slot);
      },
    };
    h.set(tint ?? 0xffffff);
    if (slot >= 0) this._ringHandles.add(h);
    else console.warn('[a3d] IconLayer: capacité d’anneaux atteinte');
    return h;
  }

  /** Called once per frame by the Engine (idempotent within a frame). */
  update(time) {
    const frame = this.engine.frame;
    if (frame === this._lastFrame) return;
    this._lastFrame = frame;
    for (const h of this._iconHandles) {
      const a = h.anchor;
      if (!h.visible || !a || !a.visible) { this.icons.hide(h.slot); continue; }
      a.updateWorldMatrix(true, false);
      _wp.setFromMatrixPosition(a.matrixWorld);
      this.icons.set(h.slot, _wp.x, _wp.y + h.offsetY, _wp.z, ICON_SIZE, h.r, h.g, h.b, 1, h.cell, 0, h.phase, h.attention);
    }
    for (const h of this._ringHandles) {
      const a = h.anchor;
      if (!h.visible || !a || !a.visible) { this.rings.hide(h.slot); continue; }
      a.updateWorldMatrix(true, false);
      _wp.setFromMatrixPosition(a.matrixWorld);
      this.rings.set(h.slot, _wp.x, _wp.y + 0.04, _wp.z, h.radius * 2, h.r, h.g, h.b, 0.9, 0, 0, h.phase, 0);
    }
    this.icons.flush();
    this.rings.flush();
  }

  dispose() {
    this._iconHandles.clear();
    this._ringHandles.clear();
    this.icons.dispose();
    this.rings.dispose();
    if (this.texture) this.texture.dispose();
  }
}

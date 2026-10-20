// render/materials.js — MaterialFactory: shared materials, toon gradient ramp, rim injection (spec §12.3).
// Program economy (low tier ≤ 10 programs): the world, props, characters and (low/medium) hero all share ONE
// toon program ('soft-rim'); rim strength and emissive are uniforms, so per-use material instances reuse it.
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';
import { createWaterMaterial } from 'a3d/render/water.js';

// ---------------------------------------------------------------------------------------------
// Active engine (views are created with only their level definition, spec §12.5)
// ---------------------------------------------------------------------------------------------

let _activeEngine = null;
/** Registers the engine used by view factories (`create*View`, `createCharacter`). Called by Engine.init(). */
export function setActiveEngine(engine) { _activeEngine = engine; }
/** @returns {import('a3d/engine/Engine.js').Engine|null} */
export function getActiveEngine() { return _activeEngine; }

// ---------------------------------------------------------------------------------------------
// Toon ramp
// ---------------------------------------------------------------------------------------------

const RAMP = [70, 95, 130, 170, 205, 230, 245, 255];
let _gradient = null;

/** 8-px toon ramp with LinearFilter (shared). */
export function getGradientMap() {
  if (_gradient) return _gradient;
  const data = new Uint8Array(RAMP.length * 4);
  for (let i = 0; i < RAMP.length; i++) {
    data[i * 4] = RAMP[i]; data[i * 4 + 1] = RAMP[i]; data[i * 4 + 2] = RAMP[i]; data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, RAMP.length, 1, THREE.RGBAFormat);
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.colorSpace = THREE.NoColorSpace;
  tex.needsUpdate = true;
  _gradient = tex;
  return tex;
}

// ---------------------------------------------------------------------------------------------
// Shader injections
// ---------------------------------------------------------------------------------------------

const RIM_PARS = '#include <common>\nuniform vec3 uRimColor;\nuniform float uRimStrength;';
const RIM_FRAG = `{
  vec3 rimView = normalize( vViewPosition );
  float rimF = pow( 1.0 - clamp( dot( normal, rimView ), 0.0, 1.0 ), 3.0 ) * uRimStrength;
  outgoingLight += uRimColor * rimF;
}
#include <opaque_fragment>`;

const WIND_PARS = '#include <common>\nuniform float uTime;\nuniform float uWind;';
const WIND_VERTEX = `#include <begin_vertex>
#ifdef USE_INSTANCING
  float windH = max( transformed.y, 0.0 );
  vec2 windP = vec2( instanceMatrix[3][0], instanceMatrix[3][2] );
  float windS = sin( uTime * 1.6 + windP.x * 0.37 + windP.y * 0.29 ) + 0.35 * sin( uTime * 3.1 + windP.x * 0.9 );
  transformed.x += windS * uWind * windH * windH;
  transformed.z += windS * uWind * 0.5 * windH * windH;
#endif`;

/**
 * Adds the stylised rim term (`pow(1−N·V, 3)·strength`, colour #FFF6E0) to a toon/standard material.
 * `vertexPatch(shader)` may further edit the vertex shader; `key` must be unique per injected code variant.
 */
function withRim(mat, strength, key, vertexPatch = null, extraUniforms = null) {
  const uRimColor = { value: new THREE.Color().setHex(PALETTE.RIM) };
  const uRimStrength = { value: strength };
  mat.userData.uRimStrength = uRimStrength;
  mat.userData.uRimColor = uRimColor;
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uRimColor = uRimColor;
    shader.uniforms.uRimStrength = uRimStrength;
    if (extraUniforms) Object.assign(shader.uniforms, extraUniforms);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', RIM_PARS)
      .replace('#include <opaque_fragment>', RIM_FRAG);
    if (vertexPatch) vertexPatch(shader);
  };
  mat.customProgramCacheKey = () => key;
  return mat;
}

function toon(params = {}) {
  return new THREE.MeshToonMaterial({ vertexColors: true, gradientMap: getGradientMap(), ...params });
}

// ---------------------------------------------------------------------------------------------
// MaterialFactory
// ---------------------------------------------------------------------------------------------

/** Wind amplitudes per foliage kind (metres of sway per m² of local height, see WIND_VERTEX). */
export const WIND = Object.freeze({ grass: 0.55, flowers: 0.45, bush: 0.05, tree: 0.012, ravinala: 0.011, default: 0.02 });

export class MaterialFactory {
  constructor(engine) {
    this.engine = engine;
    this.tier = engine ? engine.tier : 'medium';
    /** Shared clock uniform (seconds of game time) used by water, foliage and fx shaders. */
    this.uTime = { value: 0 };
    this._cache = new Map();
    this._lamps = new Map();
    this._foliage = new Map();
    this._bound = new Map();     // mesh -> key (tier-dependent materials)
    this._outlines = new Set();
    this._envMap = null;
    this._envPromise = null;
  }

  /** Loads tier-only resources (RoomEnvironment PMREM on high). Safe to call repeatedly. */
  async prepare(tier) {
    const preset = this.engine && this.engine.qualityFor ? this.engine.qualityFor(tier) : null;
    const wantsEnv = preset ? !!preset.envMap : tier === 'high';
    if (!wantsEnv || this._envMap || !this.engine || !this.engine.renderer) return;
    if (!this._envPromise) {
      this._envPromise = import('three/addons/environments/RoomEnvironment.js').then(({ RoomEnvironment }) => {
        const pmrem = new THREE.PMREMGenerator(this.engine.renderer);
        const room = new RoomEnvironment();
        this._envMap = pmrem.fromScene(room, 0.04).texture;
        if (typeof room.dispose === 'function') room.dispose();
        pmrem.dispose();
      }).catch((e) => { console.warn('[a3d] RoomEnvironment indisponible', e); });
    }
    await this._envPromise;
  }

  /**
   * Shared material by key. Keys: 'worldSoft', 'worldSoftNoFog', 'hero', 'heroGlow', 'cloud', 'water', 'outline'.
   * 'hero' / 'heroGlow' depend on the tier: use bind(mesh, key) so they follow tier changes.
   */
  get(key) {
    const k = this._resolveKey(key);
    let m = this._cache.get(k);
    if (!m) {
      m = this._create(k);
      this._cache.set(k, m);
    }
    return m;
  }

  _useStandardHero() {
    return this.tier === 'high';
  }

  _resolveKey(key) {
    if (key === 'hero' || key === 'heroGlow') return key + (this._useStandardHero() ? ':std' : ':toon');
    return key;
  }

  _create(k) {
    switch (k) {
      case 'worldSoft':
        return withRim(toon(), 0.35, 'soft-rim');
      case 'worldSoftNoFog':
        return withRim(toon({ fog: false }), 0.35, 'soft-rim');
      case 'hero:toon':
        return withRim(toon(), 0.5, 'soft-rim');
      case 'heroGlow:toon': {
        const m = withRim(toon({ emissive: new THREE.Color().setHex(PALETTE.HYDRIA_CYAN), emissiveIntensity: 1.6 }), 0.5, 'soft-rim');
        return m;
      }
      case 'hero:std':
        return withRim(new THREE.MeshStandardMaterial({
          vertexColors: true, roughness: 0.45, metalness: 0.0,
          envMap: this._envMap || null, envMapIntensity: 0.4,
        }), 0.3, 'std-rim');
      case 'heroGlow:std':
        return withRim(new THREE.MeshStandardMaterial({
          vertexColors: true, roughness: 0.3, metalness: 0.0,
          emissive: new THREE.Color().setHex(PALETTE.HYDRIA_CYAN), emissiveIntensity: 1.6,
          envMap: this._envMap || null, envMapIntensity: 0.4,
        }), 0.3, 'std-rim');
      case 'cloud':
        return withRim(toon({ fog: false }), 0.25, 'cloud', (shader) => {
          // Drawn just in front of the far plane: behind the whole world, in front of the sky dome.
          shader.vertexShader = shader.vertexShader.replace('#include <project_vertex>',
            '#include <project_vertex>\n\tgl_Position.z = gl_Position.w * 0.99995;');
        });
      case 'water':
        return createWaterMaterial(this.uTime, this.engine && this.engine.quality ? this.engine.quality.waterDetail : 'full');
      case 'outline': {
        const uOutline = { value: 0.022 };
        const m = new THREE.MeshBasicMaterial({ color: new THREE.Color().setHex(PALETTE.OUTLINE), side: THREE.BackSide });
        m.userData.uOutline = uOutline;
        m.onBeforeCompile = (shader) => {
          shader.uniforms.uOutline = uOutline;
          shader.vertexShader = shader.vertexShader
            .replace('#include <common>', '#include <common>\nuniform float uOutline;')
            .replace('#include <begin_vertex>', '#include <begin_vertex>\n\ttransformed += normalize( normal ) * uOutline;');
        };
        m.customProgramCacheKey = () => 'outline';
        return m;
      }
      default:
        console.warn('[a3d] material inconnu', k);
        return this.get('worldSoft');
    }
  }

  /** Instanced foliage material with wind sway (one per amplitude; all share one program). */
  foliage(kind = 'default') {
    const amp = WIND[kind] ?? WIND.default;
    let m = this._foliage.get(amp);
    if (!m) {
      const uWind = { value: amp };
      m = withRim(toon(), 0.3, 'soft-rim-wind', (shader) => {
        shader.vertexShader = shader.vertexShader
          .replace('#include <common>', WIND_PARS)
          .replace('#include <begin_vertex>', WIND_VERTEX);
      }, { uTime: this.uTime, uWind });
      m.userData.uWind = uWind;
      this._foliage.set(amp, m);
    }
    return m;
  }

  /** Unlit state lamp (toneMapped:false, spec §12.3), cached per colour. */
  lamp(hex) {
    let m = this._lamps.get(hex);
    if (!m) {
      m = new THREE.MeshBasicMaterial({ color: new THREE.Color().setHex(hex), toneMapped: false });
      this._lamps.set(hex, m);
    }
    return m;
  }

  /** New additive glow material (halos, progress arcs). Same program as lamps; owned by the caller. */
  createGlow(hex, opacity = 0.6) {
    return new THREE.MeshBasicMaterial({
      color: new THREE.Color().setHex(hex), transparent: true, opacity, blending: THREE.AdditiveBlending,
      depthWrite: false, toneMapped: false,
    });
  }

  /** Assigns a tier-dependent material ('hero', 'heroGlow') and keeps it in sync on tier changes. */
  bind(mesh, key) {
    mesh.material = this.get(key);
    this._bound.set(mesh, key);
    return mesh;
  }

  unbind(mesh) {
    this._bound.delete(mesh);
  }

  /** Inverted-hull outline child (visible on the high tier only, interactives only). */
  addOutline(mesh) {
    const o = new THREE.Mesh(mesh.geometry, this.get('outline'));
    o.castShadow = false;
    o.receiveShadow = false;
    o.raycast = () => {};
    o.visible = this.tier === 'high';
    o.name = 'outline';
    mesh.add(o);
    this._outlines.add(o);
    return o;
  }

  removeOutline(o) {
    if (!o) return;
    this._outlines.delete(o);
    if (o.parent) o.parent.remove(o);
  }

  /** Applies a new tier: swaps bound hero materials, water detail, outline visibility. */
  setTier(tier) {
    this.tier = tier;
    for (const [mesh, key] of this._bound) mesh.material = this.get(key);
    for (const o of this._outlines) o.visible = tier === 'high';
    const water = this._cache.get('water');
    if (water) {
      const low = this.engine && this.engine.quality ? this.engine.quality.waterDetail === 'low' : tier === 'low';
      const has = Object.prototype.hasOwnProperty.call(water.defines, 'WATER_LOW');
      if (low !== has) {
        if (low) water.defines.WATER_LOW = ''; else delete water.defines.WATER_LOW;
        water.needsUpdate = true;
      }
    }
    for (const k of ['hero:std', 'heroGlow:std']) {
      const m = this._cache.get(k);
      if (m && this._envMap && m.envMap !== this._envMap) { m.envMap = this._envMap; m.needsUpdate = true; }
    }
  }

  /** Per-frame shared uniforms. */
  update(time) {
    this.uTime.value = time;
  }

  dispose() {
    for (const m of this._cache.values()) m.dispose();
    for (const m of this._lamps.values()) m.dispose();
    for (const m of this._foliage.values()) m.dispose();
    this._cache.clear();
    this._lamps.clear();
    this._foliage.clear();
    this._bound.clear();
    this._outlines.clear();
    if (this._envMap) { this._envMap.dispose(); this._envMap = null; }
    if (_gradient) { _gradient.dispose(); _gradient = null; }
  }
}

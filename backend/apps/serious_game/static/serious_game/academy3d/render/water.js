// render/water.js — stylised OPAQUE water (spec §12.4): shore gradient, two scrolled noise samples, foam band,
// fake sun glint and fresnel toward the horizon colour. Low tier: one sample, no glint.
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';
import { mulberry32 } from 'a3d/render/geometry.js';
import { SUN_DIR } from 'a3d/render/lighting.js';

let _noise = null;

/** 128² tileable value-noise CanvasTexture (seeded, NoColorSpace, repeat wrapping). */
export function getWaterNoise() {
  if (_noise) return _noise;
  const N = 128, G = 16;
  const rand = mulberry32(0x5eed1234);
  const grid = new Float32Array(G * G);
  for (let i = 0; i < grid.length; i++) grid[i] = rand();
  const grid2 = new Float32Array(32 * 32);
  for (let i = 0; i < grid2.length; i++) grid2[i] = rand();
  const sample = (g, size, x, y) => {
    const x0 = Math.floor(x), y0 = Math.floor(y);
    const fx = x - x0, fy = y - y0;
    const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const at = (i, j) => g[((j % size + size) % size) * size + ((i % size + size) % size)];
    const a = at(x0, y0), b = at(x0 + 1, y0), c = at(x0, y0 + 1), d = at(x0 + 1, y0 + 1);
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
  };
  let data;
  let canvas = null;
  try {
    canvas = document.createElement('canvas');
    canvas.width = N; canvas.height = N;
  } catch (_) { canvas = null; }
  const ctx = canvas ? canvas.getContext('2d') : null;
  const img = ctx ? ctx.createImageData(N, N) : { data: new Uint8ClampedArray(N * N * 4) };
  data = img.data;
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const v = 0.62 * sample(grid, G, (x / N) * G, (y / N) * G) + 0.38 * sample(grid2, 32, (x / N) * 32, (y / N) * 32);
      const o = (y * N + x) * 4;
      const b = Math.round(Math.min(1, Math.max(0, v)) * 255);
      data[o] = b; data[o + 1] = b; data[o + 2] = b; data[o + 3] = 255;
    }
  }
  let tex;
  if (ctx) {
    ctx.putImageData(img, 0, 0);
    tex = new THREE.CanvasTexture(canvas);
  } else {
    tex = new THREE.DataTexture(new Uint8Array(data.buffer), N, N, THREE.RGBAFormat);
    tex.needsUpdate = true;
  }
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.NoColorSpace;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = true;
  _noise = tex;
  return tex;
}

const WATER_VERT = /* glsl */`
attribute float aShore;
attribute vec2 aFlow;
attribute float aSide;
varying vec3 vWorld;
varying float vShore;
varying vec2 vFlow;
varying float vSide;
#include <common>
#include <fog_pars_vertex>
void main() {
  vec4 worldPos = modelMatrix * vec4( position, 1.0 );
  vWorld = worldPos.xyz;
  vShore = aShore;
  vFlow = aFlow;
  vSide = aSide;
  vec4 mvPosition = viewMatrix * worldPos;
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}`;

const WATER_FRAG = /* glsl */`
uniform float uTime;
uniform sampler2D uNoise;
uniform vec3 uShallow;
uniform vec3 uDeep;
uniform vec3 uFoam;
uniform vec3 uHorizon;
uniform vec3 uSunDir;
varying vec3 vWorld;
varying float vShore;
varying vec2 vFlow;
varying float vSide;
#include <common>
#include <fog_pars_fragment>
void main() {
  float shore = clamp( vShore, 0.0, 1.0 );
  vec3 col = mix( uShallow, uDeep, smoothstep( 0.0, 0.7, shore ) );
  vec2 uv = vWorld.xz * 0.07;
  vec2 drift = vFlow * uTime * 0.09;
  float n1 = texture2D( uNoise, uv + drift + vec2( uTime * 0.011, uTime * 0.007 ) ).r;
  #ifdef WATER_LOW
    float n2 = n1;
    float n = n1;
  #else
    float n2 = texture2D( uNoise, uv * 1.73 + drift * 1.3 + vec2( -uTime * 0.009, uTime * 0.013 ) ).r;
    float n = 0.5 * ( n1 + n2 );
  #endif
  // soft caustic ribbons
  float band = smoothstep( 0.60, 0.66, n ) * ( 1.0 - smoothstep( 0.66, 0.74, n ) );
  col += band * 0.16 * ( 0.4 + 0.6 * shore );
  // foam band at the shore, breathing with the noise
  float foamEdge = 0.16 + 0.05 * sin( uTime * 1.7 + n * 6.2831 );
  float foam = 1.0 - smoothstep( foamEdge * 0.55, foamEdge, shore + ( n - 0.5 ) * 0.14 );
  col = mix( col, uFoam, foam * 0.92 );
  // fresnel toward the horizon colour
  vec3 V = normalize( cameraPosition - vWorld );
  float fres = pow( 1.0 - clamp( V.y, 0.0, 1.0 ), 4.0 );
  col = mix( col, uHorizon, fres * 0.5 );
  #ifndef WATER_LOW
    vec3 N = normalize( vec3( ( n1 - 0.5 ) * 0.45, 1.0, ( n2 - 0.5 ) * 0.45 ) );
    vec3 R = reflect( -V, N );
    float glint = pow( max( dot( R, uSunDir ), 0.0 ), 140.0 );
    col += glint * 1.1 * ( 1.0 - foam );
  #endif
  if ( vSide > 0.5 ) col = uDeep * ( 0.62 + 0.18 * n );
  gl_FragColor = vec4( col, 1.0 );
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}`;

/** Opaque stylised water material. `timeUniform` is the shared {value} clock. */
export function createWaterMaterial(timeUniform, detail = 'full') {
  const uniforms = {
    ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
    uTime: timeUniform || { value: 0 },
    uNoise: { value: getWaterNoise() },
    uShallow: { value: new THREE.Color().setHex(PALETTE.WATER_SHALLOW) },
    uDeep: { value: new THREE.Color().setHex(PALETTE.WATER_DEEP) },
    uFoam: { value: new THREE.Color().setHex(PALETTE.WATER_FOAM) },
    uHorizon: { value: new THREE.Color().setHex(PALETTE.SKY_HORIZON) },
    uSunDir: { value: SUN_DIR.clone() },
  };
  const mat = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: WATER_VERT,
    fragmentShader: WATER_FRAG,
    fog: true,
    defines: detail === 'low' ? { WATER_LOW: '' } : {},
  });
  mat.name = 'water';
  return mat;
}

/**
 * Builds the water surface (+ outward side skirts) of every water def overlapping the chunk rect
 * [x0, x1] × [z0, z1]. Defs: {min:[x,y,z], max:[x,y,z], deep, flow?:[fx,fz]}. Surface y = max.y.
 * @returns {THREE.BufferGeometry|null} attributes position, aShore, aFlow, aSide (non-indexed).
 */
export function buildWaterChunkGeometry(defs, x0, z0, x1, z1, step = 1) {
  const pos = [], shore = [], flow = [], side = [];
  const SHORE_W = 2;
  for (const w of defs) {
    const wx0 = w.min[0], wz0 = w.min[2], wx1 = w.max[0], wz1 = w.max[2];
    const cx0 = Math.max(wx0, x0), cz0 = Math.max(wz0, z0), cx1 = Math.min(wx1, x1), cz1 = Math.min(wz1, z1);
    if (cx1 - cx0 <= 1e-4 || cz1 - cz0 <= 1e-4) continue;
    const y = w.max[1];
    const fx = w.flow ? w.flow[0] : 0, fz = w.flow ? w.flow[1] : 0;
    const sh = (x, z) => Math.min(1, Math.min(x - wx0, wx1 - x, z - wz0, wz1 - z) / SHORE_W);
    const nx = Math.max(1, Math.ceil((cx1 - cx0) / step)), nz = Math.max(1, Math.ceil((cz1 - cz0) / step));
    const push = (x, z) => { pos.push(x, y, z); shore.push(Math.max(0, sh(x, z))); flow.push(fx, fz); side.push(0); };
    for (let j = 0; j < nz; j++) {
      const za = cz0 + (cz1 - cz0) * (j / nz), zb = cz0 + (cz1 - cz0) * ((j + 1) / nz);
      for (let i = 0; i < nx; i++) {
        const xa = cx0 + (cx1 - cx0) * (i / nx), xb = cx0 + (cx1 - cx0) * ((i + 1) / nx);
        // CCW seen from above (+Y)
        push(xa, za); push(xa, zb); push(xb, zb);
        push(xa, za); push(xb, zb); push(xb, za);
      }
    }
    // Side skirts where the original rect edge lies inside this chunk.
    const yb = Math.min(w.min[1], y - 0.2);
    const skirt = (ax, az, bx, bz) => {
      const v = [[ax, y, az], [ax, yb, az], [bx, yb, bz], [ax, y, az], [bx, yb, bz], [bx, y, bz]];
      for (const p of v) { pos.push(p[0], p[1], p[2]); shore.push(1); flow.push(fx, fz); side.push(1); }
    };
    if (wz0 >= z0 && wz0 < z1) skirt(cx1, wz0, cx0, wz0);      // -z face, outward normal -z
    if (wz1 > z0 && wz1 <= z1) skirt(cx0, wz1, cx1, wz1);      // +z face
    if (wx0 >= x0 && wx0 < x1) skirt(wx0, cz0, wx0, cz1);      // -x face
    if (wx1 > x0 && wx1 <= x1) skirt(wx1, cz1, wx1, cz0);      // +x face
  }
  if (pos.length === 0) return null;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  g.setAttribute('aShore', new THREE.BufferAttribute(new Float32Array(shore), 1));
  g.setAttribute('aFlow', new THREE.BufferAttribute(new Float32Array(flow), 2));
  g.setAttribute('aSide', new THREE.BufferAttribute(new Float32Array(side), 1));
  g.computeBoundingSphere();
  g.computeBoundingBox();
  return g;
}

/** Disposes the shared noise texture (Engine.dispose). */
export function disposeWaterShared() {
  if (_noise) { _noise.dispose(); _noise = null; }
}

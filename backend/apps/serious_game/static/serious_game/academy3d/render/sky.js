// render/sky.js — gradient sky dome with sun disk + halo, instanced soft clouds, fog setup (spec §12.3).
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';
import { SUN_DIR } from 'a3d/render/lighting.js';
import { icoGeom, mergeStatic, paintVertices, tf, makeRng } from 'a3d/render/geometry.js';

const SKY_VERT = /* glsl */`
varying vec3 vDir;
void main() {
  vDir = position;
  vec4 mvPosition = modelViewMatrix * vec4( position, 1.0 );
  gl_Position = projectionMatrix * mvPosition;
  gl_Position.z = gl_Position.w;
}`;

const SKY_FRAG = /* glsl */`
uniform vec3 uZenith;
uniform vec3 uHorizon;
uniform vec3 uGround;
uniform vec3 uSunColor;
uniform vec3 uSunDir;
varying vec3 vDir;
void main() {
  vec3 d = normalize( vDir );
  float h = d.y;
  vec3 col;
  if ( h >= 0.0 ) {
    col = mix( uHorizon, uZenith, pow( clamp( h, 0.0, 1.0 ), 0.55 ) );
  } else {
    col = mix( uHorizon, uGround, smoothstep( 0.0, 0.22, -h ) );
  }
  float sd = max( dot( d, uSunDir ), 0.0 );
  col += uSunColor * ( pow( sd, 6.0 ) * 0.10 + pow( sd, 48.0 ) * 0.28 );
  float disk = smoothstep( 0.99905, 0.99950, sd );
  col = mix( col, uSunColor * 1.5, disk );
  gl_FragColor = vec4( col, 1.0 );
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

const THEMES = {
  matin: { zenith: PALETTE.SKY_ZENITH, horizon: PALETTE.SKY_HORIZON, ground: PALETTE.SKY_GROUND, sun: PALETTE.SUN_DISK },
  midi: { zenith: PALETTE.SKY_ZENITH_MIDI, horizon: PALETTE.SKY_HORIZON, ground: PALETTE.SKY_GROUND, sun: PALETTE.SUN_DISK },
};

const MAX_CLOUDS = 16;

function buildCloudGeometry() {
  const rng = makeRng('hydria-clouds');
  const parts = [];
  const puffs = [[0, 0, 0, 1.0], [0.9, -0.1, 0.2, 0.75], [-0.85, -0.12, -0.1, 0.8], [0.35, 0.35, -0.2, 0.7], [-0.3, 0.3, 0.25, 0.65], [1.55, -0.25, -0.1, 0.5], [-1.5, -0.25, 0.1, 0.52]];
  for (const [x, y, z, r] of puffs) {
    parts.push(icoGeom(r * rng.range(0.92, 1.08), 1, x, y, z, PALETTE.CLOUD));
  }
  const g = mergeStatic(parts);
  tf(g, 0, 0, 0, 0, 1, 0.62, 0.8);
  const shade = new THREE.Color().setHex(PALETTE.CLOUD_SHADE);
  const white = new THREE.Color().setHex(PALETTE.CLOUD);
  paintVertices(g, (out, x, y) => { out.copy(shade).lerp(white, Math.min(1, Math.max(0, (y + 0.35) / 0.55))); });
  g.computeBoundingSphere();
  return g;
}

export class Sky {
  constructor(engine) {
    this.engine = engine;
    this.uniforms = {
      uZenith: { value: new THREE.Color().setHex(THEMES.matin.zenith) },
      uHorizon: { value: new THREE.Color().setHex(THEMES.matin.horizon) },
      uGround: { value: new THREE.Color().setHex(THEMES.matin.ground) },
      uSunColor: { value: new THREE.Color().setHex(THEMES.matin.sun) },
      uSunDir: { value: SUN_DIR.clone() },
    };
    this.material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: SKY_VERT,
      fragmentShader: SKY_FRAG,
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
    });
    this.material.name = 'sky';
    this.dome = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), this.material);
    this.dome.renderOrder = 1000;
    this.dome.frustumCulled = false;
    this.dome.matrixAutoUpdate = true;
    this.dome.name = 'sky';
    engine.scene.add(this.dome);

    // Clouds: a ring of merged icospheres around the camera, drawn just in front of the far plane.
    this.cloudGeom = buildCloudGeometry();
    this.clouds = new THREE.InstancedMesh(this.cloudGeom, engine.materials.get('cloud'), MAX_CLOUDS);
    this.clouds.frustumCulled = false;
    this.clouds.castShadow = false;
    this.clouds.receiveShadow = false;
    this.clouds.renderOrder = 999;
    this.clouds.count = 0;
    this.clouds.name = 'clouds';
    const rng = makeRng('hydria-cloud-ring');
    this._cloudData = [];
    for (let i = 0; i < MAX_CLOUDS; i++) {
      this._cloudData.push({
        angle: (i / MAX_CLOUDS) * Math.PI * 2 + rng.range(-0.15, 0.15),
        radius: rng.range(180, 290),
        y: rng.range(60, 90),
        scale: rng.range(10, 19),
        yaw: rng.range(0, Math.PI * 2),
      });
    }
    this._m = new THREE.Matrix4();
    this._q = new THREE.Quaternion();
    this._p = new THREE.Vector3();
    this._s = new THREE.Vector3();
    this._yAxis = new THREE.Vector3(0, 1, 0);
    engine.scene.add(this.clouds);
    this.theme = 'matin';
  }

  setTheme(theme) {
    const t = THEMES[theme] || THEMES.matin;
    this.theme = THEMES[theme] ? theme : 'matin';
    this.uniforms.uZenith.value.setHex(t.zenith);
    this.uniforms.uHorizon.value.setHex(t.horizon);
    this.uniforms.uGround.value.setHex(t.ground);
    this.uniforms.uSunColor.value.setHex(t.sun);
  }

  /** Fog + camera far from the theme values or the tier defaults (spec §12.3). */
  applyEnvironment(env, quality) {
    const near = (env && Number.isFinite(env.fogNear)) ? env.fogNear : quality.fogNear;
    const far = Math.max(near + 1, (env && Number.isFinite(env.fogFar)) ? env.fogFar : quality.fogFar);
    const scene = this.engine.scene;
    if (!scene.fog) scene.fog = new THREE.Fog(new THREE.Color().setHex(PALETTE.FOG), near, far);
    scene.fog.near = near;
    scene.fog.far = far;
    const cam = this.engine.camera;
    cam.far = Math.max(120, far + 10);
    cam.updateProjectionMatrix();
    this.setTheme(env && env.sky ? env.sky : 'matin');
  }

  applyQuality(q) {
    this.clouds.count = Math.min(MAX_CLOUDS, q.clouds | 0);
    this.clouds.visible = this.clouds.count > 0;
  }

  update(dt, camera) {
    this.dome.position.copy(camera.position);
    const n = this.clouds.count;
    if (n <= 0) return;
    const cx = camera.position.x, cz = camera.position.z;
    for (let i = 0; i < n; i++) {
      const c = this._cloudData[i];
      c.angle += (0.6 / c.radius) * dt;   // 0.6 m/s drift along the ring
      this._p.set(cx + Math.cos(c.angle) * c.radius, c.y, cz + Math.sin(c.angle) * c.radius);
      this._q.setFromAxisAngle(this._yAxis, c.yaw);
      this._s.set(c.scale, c.scale, c.scale);
      this._m.compose(this._p, this._q, this._s);
      this.clouds.setMatrixAt(i, this._m);
    }
    this.clouds.instanceMatrix.addUpdateRange(0, n * 16);
    this.clouds.instanceMatrix.needsUpdate = true;
  }

  dispose() {
    const scene = this.engine.scene;
    scene.remove(this.dome, this.clouds);
    this.dome.geometry.dispose();
    this.material.dispose();
    this.cloudGeom.dispose();
    this.clouds.dispose();
  }
}

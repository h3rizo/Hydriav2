// render/lighting.js — hemisphere light + one fixed sun; on medium/high the ortho shadow camera follows the
// focus point with texel snapping (spec §12.3).
import * as THREE from 'three';
import { PALETTE } from 'a3d/render/palette.js';

const SUN_ELEVATION_DEG = 50;
const SUN_AZIMUTH_DEG = 135;
const SUN_DISTANCE = 40;

/** Unit vector pointing TOWARD the sun (azimuth measured from +Z toward +X). */
export const SUN_DIR = (() => {
  const el = THREE.MathUtils.degToRad(SUN_ELEVATION_DEG);
  const az = THREE.MathUtils.degToRad(SUN_AZIMUTH_DEG);
  return new THREE.Vector3(Math.cos(el) * Math.sin(az), Math.sin(el), Math.cos(el) * Math.cos(az)).normalize();
})();

export class Lighting {
  constructor(engine) {
    this.engine = engine;
    this.hemi = new THREE.HemisphereLight(new THREE.Color().setHex(PALETTE.HEMI_SKY), new THREE.Color().setHex(PALETTE.HEMI_GROUND), 1.3);
    this.sun = new THREE.DirectionalLight(new THREE.Color().setHex(PALETTE.SUN), 3.0);
    this.sun.position.copy(SUN_DIR).multiplyScalar(SUN_DISTANCE);
    this.sun.target.position.set(0, 0, 0);
    const sh = this.sun.shadow;
    sh.bias = -0.0005;
    sh.normalBias = 0.02;
    sh.camera.near = 1;
    sh.camera.far = 80;
    this._focus = new THREE.Vector3();
    this._snapped = new THREE.Vector3();
    // Light-space basis matching the shadow camera's lookAt(target) with up = +Y.
    this._right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), SUN_DIR).normalize();
    this._up = new THREE.Vector3().crossVectors(SUN_DIR, this._right).normalize();
    this._halfExtent = 0;
    this._mapSize = 0;
    engine.scene.add(this.hemi, this.sun, this.sun.target);
  }

  applyQuality(q) {
    const sun = this.sun;
    sun.castShadow = !!q.shadows;
    if (q.shadows) {
      const half = q.shadowHalfExtent || 14;
      const cam = sun.shadow.camera;
      cam.left = -half; cam.right = half; cam.top = half; cam.bottom = -half;
      cam.near = 1; cam.far = 80;
      cam.updateProjectionMatrix();
      if (this._mapSize !== q.shadowMapSize) {
        sun.shadow.mapSize.set(q.shadowMapSize, q.shadowMapSize);
        if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
        this._mapSize = q.shadowMapSize;
      }
      this._halfExtent = half;
      sun.shadow.needsUpdate = true;
    } else {
      if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
      this._mapSize = 0;
      this._halfExtent = 0;
    }
    this._place();
  }

  /** Shadow camera follow target (usually the player's render position). */
  setFocus(v) {
    if (!v) return;
    this._focus.set(v.x, v.y, v.z);
  }

  _place() {
    const f = this._focus;
    if (this._halfExtent > 0 && this._mapSize > 0) {
      // Texel snapping: quantise the focus in the light's right/up plane so shadows do not shimmer.
      const texel = (2 * this._halfExtent) / this._mapSize;
      const r = Math.round(f.dot(this._right) / texel) * texel;
      const u = Math.round(f.dot(this._up) / texel) * texel;
      const d = f.dot(SUN_DIR);
      this._snapped.copy(this._right).multiplyScalar(r)
        .addScaledVector(this._up, u)
        .addScaledVector(SUN_DIR, d);
    } else {
      this._snapped.copy(f);
    }
    this.sun.target.position.copy(this._snapped);
    this.sun.position.copy(this._snapped).addScaledVector(SUN_DIR, SUN_DISTANCE);
    this.sun.target.updateMatrixWorld();
  }

  update() {
    this._place();
  }

  dispose() {
    if (this.sun.shadow.map) this.sun.shadow.map.dispose();
    this.sun.dispose();
    this.hemi.dispose();
    this.engine.scene.remove(this.hemi, this.sun, this.sun.target);
  }
}

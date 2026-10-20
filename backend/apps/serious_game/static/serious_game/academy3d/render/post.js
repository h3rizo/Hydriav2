// render/post.js — high tier only, loaded with a dynamic import (spec §12.3): EffectComposer with a 4× MSAA
// half-float target, half-resolution bloom, and OutputPass applying tone mapping + sRGB.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

export class PostFX {
  constructor(engine) {
    this.engine = engine;
    const { renderer, scene, camera } = engine;
    const size = renderer.getSize(new THREE.Vector2());
    const pr = renderer.getPixelRatio();
    this.target = new THREE.WebGLRenderTarget(Math.max(1, size.x * pr), Math.max(1, size.y * pr), {
      type: THREE.HalfFloatType,
      samples: 4,
    });
    this.composer = new EffectComposer(renderer, this.target);
    this.renderPass = new RenderPass(scene, camera);
    // UnrealBloomPass already runs its bright/blur chain at half the composer resolution.
    this.bloom = new UnrealBloomPass(new THREE.Vector2(Math.max(1, size.x * pr), Math.max(1, size.y * pr)), 0.35, 0.45, 0.86);
    this.output = new OutputPass();
    this.composer.addPass(this.renderPass);
    this.composer.addPass(this.bloom);
    this.composer.addPass(this.output);
    this.setSize(size.x, size.y, pr);
  }

  setSize(width, height, pixelRatio) {
    this.composer.setPixelRatio(pixelRatio);
    this.composer.setSize(width, height);   // also resizes the bloom pass (internally half resolution)
  }

  render(dt) {
    this.composer.render(dt);
  }

  dispose() {
    this.bloom.dispose();
    this.output.dispose();
    this.composer.dispose();
    this.target.dispose();
  }
}

export async function createPost(engine) {
  return new PostFX(engine);
}

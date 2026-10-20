// render/props/index.js — re-exports every create*View factory (spec §12.5) and the platform / decor builders.
export { createOuvrageView, createValveView, createUsagerView, ViewKit } from 'a3d/render/props/infra.js';
export {
  createMoverView, createBlockView, createJumpPadView, createCheckpointView, createGoalView, createCollectibleField,
  createNpcView, dropletGeometry,
} from 'a3d/render/props/interactives.js';
export {
  buildPlatformGeometry, buildPlatformSign, buildLocalBox, createSignMesh, SignBatch, BOX_STYLES, faceFrame, pickFront,
} from 'a3d/render/props/platforms.js';
export { buildDecor, DECOR_KINDS, FOLIAGE_KINDS, getFoliagePrototype } from 'a3d/render/props/village.js';
export { createCharacter } from 'a3d/actors/characters.js';

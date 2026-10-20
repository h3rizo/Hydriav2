# Hydria Quest 3D: implementation spec v1 (shared contract)

> **Status:** binding contract for 5 parallel work packages (P1–P5). Every package owns a disjoint set of files (§16). When this document says MUST, it is a contract other packages rely on. If something is ambiguous, follow the most literal reading of this document and leave a `// SPEC-QUESTION:` comment. Never silently change a signature.
>
> **Product:** "Hydria Quest 3D" (already linked as `/serious-game/jeu-3d/` in `templates/planning/base.html` and `templates/planning/includes/planning_sidebar.html`). It is a bright, stylized 3D platformer for the staff of a water utility. Hero: **Koto, technicien Hydria**, wearing a backpack "Hydro-pack". All UI text is French.

---

## 0. Merged decisions (read first)

| Topic | Decision | Source |
|---|---|---|
| Controller feel | Three verbs only: **Se déplacer, Sauter (maintenir = planer), Agir**. Coyote and buffer windows of 150 ms, variable jump height, no double jump. A fall never makes you lose. | beginner |
| Character scale | Chibi capsule: **r = 0.35 m, h = 1.1 m**. Jump 1.7 m, gravity 30 going up and 45 going down. One `core/tuning.js` is the only source of truth. | beginner (the learning proposal's 1.6 m / g = 24 is rejected) |
| Collision | **Authored primitives only**: AABB boxes, vertical cylinders, axis-aligned ramps, volumes. No mesh raycasts and no physics library. | judges |
| Camera | Height follows the **last ground touched**. Diorama camera zones. Never auto-rotate when walking toward the camera. 90°/s angular cap. No occluder fading: levels are designed so nothing occludes, plus a pull-in. | beginner + judges |
| Rendering | Shared vertex-coloured toon material with a rim term. Neutral tone mapping. Hemisphere light + 1 sun. Chunk-merged statics. Blob shadow on every tier. Opaque water. 3 tiers with a median-FPS governor that only steps down. **WebGL2 required**, with a fallback to the 2D Phaser simulation. | visual + judges |
| Learning | One level = one real business gesture. The quiz is a DOM modal shown **at the moment of the gesture**. A wrong answer never blocks. Each level ends with a 3-rule fiche réflexe. Repair statuses, bon de livraison, receipts returned to the caissière. | learning |
| State colours | Exact Phaser colours: facility healthy `0x22c55e`, repairing `0xfacc15`, broken `0xef4444`; usager due `0xeab308` (**yellow, not green**), overdue `0xf97316`, cut_off `0xef4444`, restore_pending `0x38bdf8`. New 3D-only state: `paid` uses `0x22c55e`. | GameState/GameScene |
| Timers | Soft only: they cost points or a star, never cause a failure. Paused during quiz, dialogue, falls and menus. Business pressure and platforming never happen in the same section. | judges |
| Anti-farming | Server-side `GameRun` created at start with a question snapshot. Answers are graded by the **server** (a POST per answer); expected answers are never sent while online. XP only for **newly earned star bits**, plus a 30 XP/day practice cap. Score feeds records only, never XP. | learning + judges |
| Cut from v1 | Ghosts, time trial, gold drops, bounce tech, express-repair notch, autoAction, gameSpeed, rotating discs, crumbling tiles, conveyors, pushing cart, offline queue (except one pending result slot), trainer dashboard UI, outlines below the high tier, `SkinnedMesh`. | judges |
| Key change | **Espace = Sauter**. Agir moves to **E / Entrée**. The controls sheet says so: « Nouveau : Espace sert à sauter, E à agir ». | beginner |

---

## 1. Scope v1

**4 levels**, each 3–6 min, 12 stars in total:

| # | id | Title (FR) | Gesture taught | New mechanics | Quiz slots (module) | Gouttes |
|---|---|---|---|---|---|---|
| 0 | `L0_premier_jour` | Premier jour au village | Move, act, jump, safe fall, collect a payment, remise en eau | jump pad | q1 (`usage_intro`, vrai/faux preferred) | 30 |
| 1 | `L1_pompe_panne` | La pompe en panne | Full repair chain: signalée → planifiée (bon de livraison) → en cours → terminée → validée | raft (mover), valve → bridge, NPC give | q1 (`stocks_livraisons`), q2 (`planning_validation`) | 40 |
| 2 | `L2_tournee` | Tournée d'encaissement | Usager priorities, payment, remise en eau after payment, receipts to the caissière | rooftops, **glide** (unlocked), valve restore, soft overdue timer | q1 (`encaissements`), q2 (`encaissements`), q3 (`releves_facturation`) | 40 |
| 3 | `L3_chateau` | Journée chargée au château d'eau | Prioritising simultaneous breakdowns, château filling via valves | scheduled soft breakdowns on a flat hub, a gated 2.5D scaffold climb, vertical lift | q1 (`dashboards_controles`), q2 (`data_villages_ouvrages`), q3 (`dashboards_controles`) | 50 |

**In v1:**
- **Assist profiles:** `debutant`, `occasionnel`, `joueur`, chosen by one onboarding question.
- **Input devices:** keyboard + mouse, gamepad (standard mapping), and touch (floating joystick plus SAUTER and AGIR buttons).
- **Quality tiers:** Économie, Standard and Haute, with automatic detection and a governor.
- **Screens:** start, onboarding, level select, loading, HUD, pause with settings, quiz modal, dialogue, help-bridge offer, level complete with fiche réflexe and optional TTS.
- **Backend:** GameRun and GameLevelBest models, three APIs, XP, and badges.

---

## 2. Global conventions

### 2.1 Units and axes

- Units are meters and seconds. World space is right-handed with **Y up**. Every `pos` in level data is the **feet / base** position, so `y` is the top of the supporting surface.
- **Facing yaw convention, used everywhere in level data:** yaw is in degrees. `yaw = 0` faces **+Z** and `yaw = 90` faces **+X**. The direction vector for yaw θ (radians) is `(sin θ, 0, cos θ)`.
- **Character and prop models** are built facing local +Z. Setting `object3d.rotation.y = θ` makes them face `(sin θ, 0, cos θ)`.
- **Camera yaw ψ** is `camera.rotation.y` with Euler order `'YXZ'`. The camera looks along `(−sin ψ, 0, −cos ψ)`, and screen-right is `(cos ψ, 0, −sin ψ)`. For a facing yaw θ, the camera placed *behind* the character has `ψ = θ + π`.
- **Stick to world:** `move = right·mx + fwd·my`, with `fwd = (−sin ψ, 0, −cos ψ)`, `right = (cos ψ, 0, −sin ψ)`, `mx` positive to the right, and `my` positive forward/up.

### 2.2 Modules

- Every game JS file is an ES module under `backend/apps/serious_game/static/serious_game/academy3d/`.
- **All intra-game imports use bare specifiers `a3d/<path>.js`.** For example: `import { EventBus } from 'a3d/core/EventBus.js'`. Relative imports (`./x.js`) are **forbidden**: the import map adds a per-file `?v=<hash>` for cache busting, and relative imports would bypass it.
- Three.js is imported as `import * as THREE from 'three'`. Addons are imported as `'three/addons/<path>.js'` (pinned **three@0.170.0**, §14.6).
- **Three-free modules** must not import `'three'`, directly or transitively, because `main.js` imports them before the WebGL2 check:
  - `main.js`
  - `core/*`
  - `ui/*`
  - `audio/*`
  - `net/*`
  - `levels/*`
  - `gameplay/states.js`
  - `render/palette.js`
  - `engine/quality.js`

### 2.3 Performance rules

These apply to every package:
- No per-frame allocations in the hot path: pool `THREE.Vector3`, `Matrix4` and plain objects.
- No `Sprite` objects, no point or spot lights, no `MeshPhysicalMaterial`, no `alphaTest` or `discard` on world materials, no SSAO, and no reflections.

### 2.4 DOM rules

The page shell loads the Tailwind Play CDN, whose MutationObserver watches `class` attributes and `childList`. Game DOM therefore follows these rules:
- Use only `a3d-*` classes, defined in `academy3d.css`. No Tailwind utilities in dynamically created game DOM.
- Update text by setting `Text.nodeValue` on pre-created text nodes. Never use `innerHTML` or `textContent` per frame.
- Move elements with `style.transform`.
- Toggle visibility with the `hidden` attribute.
- Change classes only on discrete state changes, at most a few times per second.

### 2.5 Language and strings

- All visible strings are French, UTF-8, with accents.
- Code identifiers are English.
- Money is formatted with `n.toLocaleString('fr-FR') + ' Ar'`.

### 2.6 Storage

- Use `localStorage` only through `core/storage.js` (try/catch, prefix `hydria3d:v1:`). The game must work when storage throws.

---

## 3. File layout and ownership

The JS root is `backend/apps/serious_game/static/serious_game/academy3d/`. The P column gives the owner. "TF" means three-free.

| Path | P | Purpose |
|---|---|---|
| `main.js` | P5 | TF. `boot(rootEl)`: reads the bootstrap, checks WebGL2, shows screens, lazy-imports `app/GameSession.js` |
| `app/GameSession.js` | P5 | Wires engine, collision, player, camera, input, level runtime and UI for one level run; owns the frame order and the pause model |
| `core/EventBus.js` | P5 | TF. Tiny synchronous pub/sub (code in §4.1) |
| `core/events.js` | P5 | TF. `EV` event-name constants (exact content in §4.2) |
| `core/storage.js` | P5 | TF. Safe `localStorage` wrapper |
| `core/assists.js` | P5 | TF. Assist profiles, settings defaults, `resolveAssists()` |
| `core/tuning.js` | P3 | TF. `TUNING` constants (exact content in §4.3) |
| `engine/Engine.js` | P2 | Renderer, scene, camera, loop (fixed 60 Hz + render throttle), resize, context loss, FX singletons |
| `engine/quality.js` | P2 | TF. `QUALITY_PRESETS`, `detectTier()`, `FpsGovernor` |
| `render/palette.js` | P2 | TF. `PALETTE`, `STATE_COLORS`, `STYLE_COLORS` |
| `render/materials.js` | P2 | `MaterialFactory` (shared materials, gradient ramp, rim injection) |
| `render/geometry.js` | P2 | Geometry helpers: `prepStatic`, colourising, rounded box, wedge |
| `render/lighting.js` | P2 | Hemisphere light + sun, shadow camera follow with texel snapping |
| `render/sky.js` | P2 | Sky dome, clouds, fog setup |
| `render/water.js` | P2 | Stylized opaque water material and mesh builder |
| `render/post.js` | P2 | High tier only, dynamic import: EffectComposer + half-res bloom + OutputPass |
| `render/StaticWorld.js` | P2 | Static platforms, decor and water; chunk merging; per-chunk instancing |
| `render/props/index.js` | P2 | Re-exports all `create*View` factories |
| `render/props/platforms.js` | P2 | Box, cylinder and ramp visual geometry per style (incl. `house_tin`, `kiosque`) |
| `render/props/village.js` | P2 | Decor kinds (ravinala, baobab, tree, bush, rock, flowers, fence, path, pipe, rice_patch, cart, crate, barrel, sign) |
| `render/props/infra.js` | P2 | Ouvrage views (`bf`, `pompe`, `kiosque`, `station`, `chateau`) and valve view |
| `render/props/interactives.js` | P2 | Mover, block, jump pad, checkpoint, goal and collectible-field views |
| `actors/characters.js` | P2 | `createCharacter()` (technicien, usager, npc), rigid-part rig, procedural animation |
| `fx/particles.js` | P2 | Two pooled `Points` systems and emitter presets |
| `fx/IconLayer.js` | P2 | Icon atlas (FontAwesome + canvas fallback), instanced billboards, ground rings |
| `fx/markers.js` | P2 | `BlobShadows`, `LandingMarker`, `GuideTrail` |
| `physics/CollisionWorld.js` | P3 | Primitive collision world, broadphase, queries |
| `physics/debugDraw.js` | P3 | `?debug=1` wireframes of colliders, volumes and camera zones |
| `player/Player.js` | P3 | Kinematic controller, abilities, assists, respawn, launch, auto-walk |
| `player/SafeGround.js` | P3 | Safe-position ring buffer |
| `player/prediction.js` | P3 | Ballistic landing prediction, landing assist, ledge magnet helpers |
| `camera/CameraRig.js` | P3 | Follow camera, zones, recentre, orbit, occlusion pull-in, shake |
| `input/InputManager.js` | P3 | Unified `InputState`, latching, device detection, vibration |
| `input/keyboard.js` | P3 | Keyboard + mouse source |
| `input/gamepad.js` | P3 | Gamepad source |
| `input/touch.js` | P3 | Touch joystick and buttons (creates DOM inside `#a3d-touch`) |
| `gameplay/states.js` | P4 | TF. `FACILITY_STATE`, `CITIZEN_STATE` |
| `gameplay/LevelBuilder.js` | P4 | Builds a `LevelRuntime` from level data (collision + visuals + entities) |
| `gameplay/LevelRuntime.js` | P4 | Per-frame gameplay: movers, blocks, triggers, collectibles, checkpoints, interactions |
| `gameplay/Mission.js` | P4 | Objectives, business states, timers, scoring, satisfaction, stars, hints, process track, run summary |
| `gameplay/Interactions.js` | P4 | Nearby-interaction selection, action progress, quiz gating, NPC scripts |
| `gameplay/entities.js` | P4 | Runtime entity classes |
| `levels/index.js` | P4 | TF. `LEVELS`, `getLevel(n)` |
| `levels/helpers.js` | P4 | TF. `box`, `cyl`, `ramp`, `line`, `padArc` |
| `levels/L0_premier_jour.js` … `levels/L3_chateau.js` | P4 | TF. Level data (§6) |
| `ui/dom.js` | P5 | TF. DOM helpers (`h()`, text-node handles) |
| `ui/strings.js` | P5 | TF. All French UI strings |
| `ui/glyphs.js` | P5 | TF. Device glyph substitution for `{move}`, `{jump}`, `{act}`, `{cam}`, `{pause}` |
| `ui/Screens.js` | P5 | Start, onboarding, level select, loading, level complete, fallback panels |
| `ui/Hud.js` | P5 | HUD (objective, process track, counters, satisfaction, feed, compass, pause button, fullscreen) |
| `ui/Prompts.js` | P5 | Action bubble in the world, bottom action line, hint bubbles, help-bridge offer |
| `ui/QuizModal.js` | P5 | Quiz modal with server grading |
| `ui/Dialogue.js` | P5 | NPC dialogue panel |
| `ui/PauseMenu.js` | P5 | Pause, Aides, Options, Commandes |
| `ui/WorldLabels.js` | P5 | Name labels for the 4 nearest entities |
| `ui/Toasts.js` | P5 | Floating "+10", money and satisfaction toasts |
| `audio/Audio.js` | P5 | WebAudio synthesized SFX and ambience |
| `audio/Speech.js` | P5 | Optional fr-FR TTS (feature-detected) |
| `net/ApiClient.js` | P5 | Fetch wrapper (CSRF, timeouts, retries, pending-result slot) |
| `backend/apps/serious_game/static/serious_game/css/academy3d.css` | P5 | All game CSS, including the touch-control styles for P3's DOM |
| Django files | P1 | See §14 and §16 |

---

## 4. Shared core contracts

### 4.1 `core/EventBus.js` (exact code)

```js
export class EventBus {
  constructor() { this._m = new Map(); }
  on(type, fn) { let s = this._m.get(type); if (!s) { s = new Set(); this._m.set(type, s); } s.add(fn); return () => s.delete(fn); }
  once(type, fn) { const off = this.on(type, (p) => { off(); fn(p); }); return off; }
  off(type, fn) { const s = this._m.get(type); if (s) s.delete(fn); }
  emit(type, payload = {}) {
    const s = this._m.get(type); if (!s) return;
    for (const fn of [...s]) { try { fn(payload); } catch (e) { console.error('[a3d]', type, e); } }
  }
  clear() { this._m.clear(); }
}
```

- Dispatch is synchronous.
- Payloads are plain objects. Listeners must not mutate them.
- One bus per page, created in `main.js` and passed to every constructor as `bus`.

### 4.2 `core/events.js` (exact names and payloads)

```js
export const EV = Object.freeze({
  // --- Player (P3 emits) ---
  PLAYER_JUMP: 'player:jump',          // {x,y,z, kind:'normal'|'pad'}
  PLAYER_LAND: 'player:land',          // {x,y,z, fallHeight:number, heavy:boolean}  heavy = fallHeight > 3
  PLAYER_GLIDE: 'player:glide',        // {active:boolean}
  PLAYER_FALL: 'player:fall',          // {reason:'void'|'water'|'bounds', x,y,z, lastSafe:[x,y,z]}
  PLAYER_RESPAWN: 'player:respawn',    // {x,y,z, reason}
  PLAYER_STEP: 'player:step',          // {x,z, surface:string}  one per stride, for audio
  INPUT_DEVICE: 'input:device',        // {device:'kbm'|'pad'|'touch'}
  CAMERA_ZONE: 'camera:zone',          // {id:string|null}
  FX_SHAKE: 'fx:shake',                // {amp:number, ms:number}  (CameraRig listens)
  // --- Level / gameplay (P4 emits) ---
  LEVEL_READY: 'level:ready',          // {levelIndex, title}
  LEVEL_START: 'level:start',          // {levelIndex}
  LEVEL_COMPLETE: 'level:complete',    // {summary: RunSummary}
  OBJECTIVE_CHANGED: 'objective:changed', // {index, total, id, text, targetId:string|null}
  OBJECTIVE_DONE: 'objective:done',    // {id}
  PROCESS_CHANGED: 'process:changed',  // {title, steps:string[], current:number}  current = -1 means none
  INTERACTION_CHANGED: 'interaction:changed', // {hint: InteractionHint|null}
  ACTION_START: 'action:start',        // {id, kind, durationMs, label}
  ACTION_PROGRESS: 'action:progress',  // {id, t}  0..1, at most 30 Hz
  ACTION_CANCEL: 'action:cancel',      // {id}
  ACTION_DONE: 'action:done',          // {id, kind}
  OUVRAGE_STATE: 'ouvrage:state',      // {id, name, state}
  OUVRAGE_BROKEN: 'ouvrage:broken',    // {id, name}
  OUVRAGE_REPAIRED: 'ouvrage:repaired',// {id, name, onTime:boolean}
  OUVRAGE_MISSED: 'ouvrage:missed',    // {id, name}
  OUVRAGE_RESOLVED: 'ouvrage:resolved',// {id, name, how:'repaired'|'missed'}
  USAGER_STATE: 'usager:state',        // {id, name, state}
  USAGER_PAID: 'usager:paid',          // {id, name, stateBefore:'due'|'overdue'|'cut_off', amount, onTime:boolean}
  USAGER_RESTORED: 'usager:restored',  // {id, name}
  VALVE_OPENED: 'valve:opened',        // {id}
  ITEM_RECEIVED: 'item:received',      // {kind, count, total, from}
  ITEM_DELIVERED: 'item:delivered',    // {kind, count, to}
  NPC_TALK: 'npc:talk',                // {npcId, name, role, stepId, lines:string[]}  (P5 Dialogue opens)
  NPC_STEP: 'npc:step',                // {npcId, stepId}  (after dialogue closed + quiz + effects)
  GOUTTE_COLLECTED: 'goutte:collected',// {index, count, total, x,y,z}
  CHECKPOINT_REACHED: 'checkpoint:reached', // {id, x,y,z}
  GOAL_REACHED: 'goal:reached',        // {id}
  TRIGGER_ENTER: 'trigger:enter',      // {id}
  TRIGGER_EXIT: 'trigger:exit',        // {id}
  SCORE_CHANGED: 'score:changed',      // {score, delta, reason, x?,y?,z?}
  SATISFACTION_CHANGED: 'satisfaction:changed', // {value, delta}
  INVENTORY_CHANGED: 'inventory:changed', // {items:{[kind]:count}}
  MISSION_TICK: 'mission:tick',        // {elapsedS, brokenCount, missed}  1 Hz
  FEED: 'feed:message',                // {text, tone:'info'|'warn'|'success'}
  HINT_SHOW: 'hint:show',              // {id, text, anchorId:string|null, durationMs:number|null}
  HINT_HIDE: 'hint:hide',              // {id}
  HELP_OFFER: 'help:offer',            // {bridgeId}
  QUIZ_REQUEST: 'quiz:request',        // {slot, title}
  // --- UI (P5 emits) ---
  QUIZ_DONE: 'quiz:done',              // {slot, skipped, firstTryCorrect, attempts:string[], solved, offlineGraded}
  DIALOGUE_CLOSED: 'dialogue:closed',  // {npcId, stepId}
  HELP_ACCEPTED: 'help:accepted',      // {bridgeId}
  HELP_DECLINED: 'help:declined',      // {bridgeId}
  GAME_PAUSE: 'game:pause',            // {reason}
  GAME_RESUME: 'game:resume',          // {reason}
  SETTINGS_CHANGED: 'settings:changed',// {settings, assists}
  // --- Engine (P2 emits) ---
  ENGINE_TIER: 'engine:tier',          // {tier, reason:'auto'|'user'|'boot'}
  ENGINE_CONTEXT_LOST: 'engine:contextlost',      // {}
  ENGINE_CONTEXT_RESTORED: 'engine:contextrestored', // {}
  ENGINE_STATS: 'engine:stats',        // {fps, drawCalls, triangles, tier, pixelRatio}  1 Hz, only when debug
});
```

**Shared typedefs**, documented in JSDoc in `core/events.js`:

```js
/** @typedef {{targetId:string, kind:'repair'|'collect'|'restore'|'valve'|'talk'|'blocked',
 *   label:string, icon:IconKey, anchor:{x:number,y:number,z:number}, enabled:boolean, reason?:string}} InteractionHint */
/** @typedef {'wrench'|'hourglass'|'check'|'coins'|'faucet_off'|'droplet'|'valve'|'box'|'receipt'|'speech'|'flag'|'star'|'question'|'lock'} IconKey */
/** @typedef {{levelIndex:number, completed:boolean, durationMs:number, gouttes:number, gouttesTotal:number,
 *   falls:number, helpBridges:number, helpBridgeIds:string[],
 *   events:{repairs:number, missed_breakdowns:number, payments_due:number, payments_overdue:number,
 *           payments_cutoff:number, restores:number, on_time_payments:number, receipts_delivered:number, valves:number},
 *   segments:Array<{cp:string, t_ms:number, falls:number, help_bridge:boolean}>,
 *   scoreClient:number, satisfactionMin:number|null, quizFirstTry:number, quizCount:number,
 *   starsClient:[boolean,boolean,boolean]}} RunSummary */
```

### 4.3 `core/tuning.js` (exact values; P3 owns, everyone reads)

```js
export const TUNING = Object.freeze({
  fixedDt: 1 / 60, maxStepsPerFrame: 5, maxFrameDt: 0.1,
  capsule: { radius: 0.35, height: 1.1, centerY: 0.55 },
  move: { runSpeed: 6.0, walkSpeed: 2.6, stickWalkThreshold: 0.5, stickDeadzone: 0.12,
          groundAccel: 35, groundDecel: 45, airAccel: 20, airDecel: 4,
          turnVisualDegPerSec: 900, shallowWaterFactor: 0.6, maxSubstep: 0.25 },
  jump: { heightMax: 1.7, cutVelocity: 5.7, gravityUp: 30, gravityDown: 45,
          terminalVelocity: 20, coyoteMs: 150, bufferMs: 150 },          // v0 = sqrt(2*30*1.7) = 10.10 m/s
  glide: { fallSpeed: 1.6, maxHSpeed: 5.0, durationS: 0.8 },
  ground: { stepUp: 0.35, snapDown: 0.3, supportExpand: 0.15, maxSlopeDeg: 40, ceilingCornerNudge: 0.2 },
  safety: { sampleS: 0.25, minGroundedS: 0.3, ringSize: 8, lookbackSamples: 4, respawnEdgeMargin: 1.0,
            safeEdgeDrop: 1.0, safeEdgeHoldS: 0.5, safeEdgeInset: 0.1,
            fallFadeMs: 250, respawnInvulnMs: 1000 },
  ledge: { maxBelow: 0.35, maxDist: 0.5, hoistS: 0.12, inset: 0.3 },
  landingAssist: { fort: 1.2, leger: 0.5, off: 0, coneRadius: 1.0, cancelDot: -0.5 },
  landingMarker: { stepS: 0.05, horizonS: 1.5 },
  pad: { gravity: 30, defaultApexAbove: 2.0, defaultLockMs: 600 },
  interact: { radius: 1.6, maxDy: 1.5, autoWalkMaxMs: 400, autoWalkStop: 0.15, workSpotOffset: 0.8,
              cancelHoldS: 0.3, cancelStick: 0.5 },
  pickup: { goutteRadius: 0.9, checkpointRadius: 1.2, goalRadius: 1.5, padRadiusDefault: 0.8 },
  actionMs: { repair: 3000, collect: 1600, restore: 1400, valve: 1500 },
  camera: { distance: { proche: 5.5, normal: 8, loin: 12 }, pitchDeg: 25, pitchMinDeg: 10, pitchMaxDeg: 55,
            targetHeight: 1.2, fovDesktop: 50, fovTouch: 60, lookAhead: 1.2, lookAheadTauS: 0.4,
            halfLifeH: 0.10, halfLifeV: 0.25, groundLockUp: 2.5, groundLockDown: 1.0,
            recenterDelayS: 1.5, recenterAfterManualS: 3.0, recenterDegPerSec: 45, recenterForwardDot: 0.3,
            towardCameraDot: -0.2, maxAutoDegPerSec: 90, zoneBlendS: 0.8, zoneBlendReducedS: 1.2,
            moveFrameHoldS: 0.6, mouseDegPerPx: 0.2, padDegPerSec: 140, touchDegPerPx: 0.25,
            occlusionMin: 1.5, pullInHalfLife: 0.05, pushOutHalfLife: 0.4, near: 0.1, far: 300,
            shakeMaxAmp: 0.08 },
  input: { padDeadzone: 0.18, padCamDeadzone: 0.20, doubleTapMs: 300,
           touchStick: { baseR: 64, knobR: 28, maxTravel: 56, deadzone: 0.10, zoneW: 0.45, zoneH: 0.70,
                         ghostLeft: 120, ghostBottom: 110 },
           touchButtons: { jump: { d: 96, right: 84, bottom: 84 }, act: { d: 80, right: 210, bottom: 72 } } },
  help: { falls: 3, windowS: 90 },
  score: { goutte: 5, repair: 22, payDue: 14, payOverdue: 6, restore: 10, missed: -18,
           quiz: [20, 8, 2], levelComplete: 50 },
  satisfaction: { repair: 7, payDue: 3, payOverdue: 2, restore: 5, broken: -3, missed: -12, overdue: -5 },
});
```

**Derived level-design rules.** All level data in §6 respects these:

| Rule | Value |
|---|---|
| Full jump airtime (same height) | 0.61 s |
| Full jump reach at run speed | 3.7 m |
| Comfortable horizontal gap | ≤ 2.6 m (L0 ≤ 1.5 m, L1 ≤ 2.0 m) |
| Upward step | ≤ 1.2 m with a gap ≤ 1.6 m; ≤ 1.0 m with a gap ≤ 2.0 m |
| Steps up to 0.35 m | walkable without jumping |
| Glide gap (glide levels only) | ≤ 5.5 m, always with a help bridge |
| Minimum platform width | 2.0 m (L0–L1), 1.6 m after that |
| Headroom over a take-off spot | ≥ 2.9 m (no stacked platforms with less) |

### 4.4 `core/assists.js` (P5; read by P3 and P4)

```js
export const ASSIST_PROFILES = Object.freeze({
  debutant:    { guidePath: true,    objectiveArrow: true,  landingAssist: 'fort',  landingMarker: true,
                 safeEdges: true,    infiniteGlide: true,   relaxedTimers: true,   pauseTimersOnFall: true, offerHelpBridge: true },
  occasionnel: { guidePath: 'early', objectiveArrow: true,  landingAssist: 'leger', landingMarker: 'early',
                 safeEdges: 'early2',infiniteGlide: false,  relaxedTimers: false,  pauseTimersOnFall: true, offerHelpBridge: true },
  joueur:      { guidePath: false,   objectiveArrow: false, landingAssist: 'off',   landingMarker: false,
                 safeEdges: false,   infiniteGlide: false,  relaxedTimers: false,  pauseTimersOnFall: false, offerHelpBridge: true },
});
// 'early' = levelIndex <= 1 ; 'early2' = levelIndex <= 2
export const DEFAULT_SETTINGS = Object.freeze({
  reducedMotion: null,      // null => matchMedia('(prefers-reduced-motion: reduce)')
  leftHanded: false, vibration: true, cameraDistance: 'normal', invertY: false,
  quality: 'auto', volume: 0.8, tts: true, bigText: false, shake: false,
});
/** @returns {{profile:string, guidePath:boolean, objectiveArrow:boolean, landingAssist:'fort'|'leger'|'off',
 *  landingMarker:boolean, safeEdges:boolean, infiniteGlide:boolean, relaxedTimers:boolean,
 *  pauseTimersOnFall:boolean, offerHelpBridge:boolean}} */
export function resolveAssists(state /* {profile, overrides:{}} */, levelIndex) { /* profile + overrides, then early rules */ }
export function loadAssistState(bootstrapDefault) { /* storage 'assists' or null => onboarding needed */ }
export function saveAssistState(state) {}
export function loadSettings() {}   // merged with DEFAULT_SETTINGS; reducedMotion resolved to boolean
export function saveSettings(s) {}
export function assistsUsedList(resolved) { /* ['profile:debutant','landingAssist:fort','safeEdges',...] */ }
```

- `relaxedTimers` multiplies `deadlineS` and `overdueAtS` by **1.5**.
- Assists never change XP and never remove stars.

### 4.5 `core/storage.js` and `gameplay/states.js`

```js
// core/storage.js — keys are prefixed 'hydria3d:v1:'
export const storage = { get(key, fallback = null) {}, set(key, value) {}, remove(key) {} }; // JSON, try/catch, never throws
// keys used: 'assists' {profile, overrides}, 'settings', 'quality' ('auto'|'low'|'medium'|'high'),
//            'best' {"0":{"m":mask,"s":score,"t":ms}}, 'pending' (one ResultPayload), 'hintsSeen' {id:count}
```

```js
// gameplay/states.js
export const FACILITY_STATE = Object.freeze({ HEALTHY: 'healthy', BROKEN: 'broken', REPAIRING: 'repairing' });
export const CITIZEN_STATE = Object.freeze({ DUE: 'due', OVERDUE: 'overdue', CUT_OFF: 'cut_off',
                                             RESTORE_PENDING: 'restore_pending', PAID: 'paid' });
```

---

## 5. Level data format (schema)

Each level file is `levels/Lx_*.js`. It contains `export default { ... }` and may only import from `a3d/levels/helpers.js`.

### 5.1 Helpers (`levels/helpers.js`, exact semantics)

```js
export const box  = (min, max, style = 'grass', extra = {}) => ({ type: 'box', min, max, style, ...extra });
export const cyl  = (cx, cz, r, y0, y1, style = 'concrete', extra = {}) => ({ type: 'cyl', c: [cx, cz], r, y0, y1, style, ...extra });
// ramp: footprint min.xz..max.xz. Surface height = min.y at the low side and max.y at the side named by `up`.
// The solid wedge spans from (min.y - thickness) to the surface.
export const ramp = (min, max, up, style = 'laterite', extra = {}) => ({ type: 'ramp', min, max, up, thickness: 0.4, style, ...extra });
// line: n >= 2 points from a to b inclusive, p_i = a + (b - a) * i / (n - 1)
export function line(a, b, n) {}
// padArc: n points on the exact jump-pad trajectory (same formula as Player.launch), at times t_i = T*(i+1)/(n+1).
// g = TUNING.pad.gravity (30); apexY = max(a.y, b.y) + apexAbove; vy0 = sqrt(2g(apexY - a.y));
// T = vy0/g + sqrt(2(apexY - b.y)/g); x/z linear in t; y = a.y + vy0*t - g*t*t/2; then +0.55 (player centre).
export function padArc(a, b, apexAbove, n) {}
```

### 5.2 Top-level object

```js
{
  id: 'L1_pompe_panne', index: 1, title: 'La pompe en panne', place: 'Andranomena',
  description: string,               // level-select card, ≤ 140 characters
  durationLabel: '≈ 5 min',
  theme: { sky: 'matin' | 'midi', fogNear: number|null, fogFar: number|null }, // null = tier default
  abilities: { glide: boolean },
  hud: { satisfaction: boolean, receipts: boolean, missionTimer: boolean },
  satisfactionStart: 80,
  spawn: { pos: [x,y,z], yaw: deg },
  killY: -8,
  bounds: { min: [x, z], max: [x, z] },          // hard clamp of the player's x/z (acts as invisible walls)
  parTimeS: number, minTimeS: number,            // must equal the server LEVELS values
  stars: { s3: 'quiz_first_try'|'tournee_a_l_heure'|'service_exemplaire', s3Label: string },
  quizSlots: [{ slot: 'q1', module: 'usage_intro', intro: string }],  // informative; the server decides the questions
  ficheReflexe: [string, string, string],
  statics: [box|cyl|ramp],     // extra on any: {walkable?: true, solid?: true, sign?: string, cameraIgnore?: bool, id?: string}
  waters: [{ min, max, deep: boolean, flow?: [fx, fz] }],   // surface y = max.y
  decor: [{ kind, pos, yaw?, scale?, variant?, points?, width?, radius?, size?, text?, collider? }],
  movers: [{ id, size: [sx,sy,sz], path: [[x,y,z], ...] /* box centres */, speed, pauseS, mode: 'pingpong', phase: 0..1, style }],
  blocks: [{ id, shapes: [{type:'box', min, max} | {type:'ramp', min, max, up, thickness}], style,
             solidAtStart: boolean, offsetHidden: [dx,dy,dz], animMs }],
  jumpPads: [{ id, pos, r, target: [x,y,z], apexAbove, lockMs }],
  checkpoints: [{ id, pos, yaw }],
  ouvrages: [{ id, kind: 'bf'|'pompe'|'kiosque'|'station'|'chateau', name, pos, yaw, state: 'healthy'|'broken',
               interactive?: true, requiresItem?: string, quizSlot?: string, repairMs?: number,
               failAtS?: number, deadlineS?: number, params?: object, colliders?: [box|cyl] }],
  usagers: [{ id, name, pos, yaw, state: 'due'|'overdue'|'cut_off', amount, branchement: 'BP'|'BI'|'kiosque',
              overdueAtS?: number, quizSlot?: string, restoreBy: 'action'|'valve', variant?: number }],
  valves: [{ id, pos, yaw, quizSlot?: string, label?: string, effects: [Effect] }],
  npcs: [{ id, name, role: 'cheffe'|'magasinier'|'caissiere', pos, yaw, autoTalk?: boolean, variant?: number, script: [NpcStep] }],
  goal: { id: 'goal', pos } | null,
  gouttes: [[x,y,z], ...],        // goutte centres
  triggers: [{ id, min, max }],
  cameraZones: [{ id, min, max, yaw, pitch, distance, blendS?, orbitLimitDeg?, targetLock?: { x?: number, z?: number } }],
  helpBridges: [{ id, zone: { min, max }, block: { shapes, style: 'pipe' } }],
  hints: [Hint],
  objectives: [Objective],
  process: null | { title, steps: string[], when: [Matcher, ...] /* same length as steps */ },
}
```

**Sub-types:**

```js
// Matcher: payload fields compared with ===. Counted from level start (out-of-order tolerant).
Matcher = { event: string /* EV value */, where?: object, count?: number /* default 1 */ }
Effect = { op: 'give', kind, count } | { op: 'take', kind, count } | { op: 'setSolid', id, solid }
       | { op: 'setLevel', id, value } | { op: 'restore', id } | { op: 'feed', text, tone? }
NpcStep = { id, when: 'always' | { objective: string } | { hasItem: { kind, count } }, once?: boolean,
            lines: string[], quizSlot?: string, effects?: Effect[] }
Hint = { id, trigger?: string /* trigger id; undefined = whole level */, showOn?: Matcher, idleMs?: number /* default 2500 */,
         maxShows?: number /* default 3 */, durationMs?: number|null, anchorId?: string, text: string /* with {move}{jump}{act}{cam}{pause} */,
         doneWhen?: Matcher }
Objective = { id, text /* may contain {done} {total} */, target: string|null|'@urgent', done: Matcher & { total?: number },
              onDone?: Effect[] }
```

**Semantics of each entity type:**

- **Static boxes** are solid from `min.y` to `max.y`; their top is walkable unless `walkable:false`.
  - `invisible` style = solid with no visual, `cameraIgnore` defaults to true and walkable defaults to false.
  - `house_tin` / `kiosque` render as buildings with a flat walkable tin roof. `sign` is optional text (≤ 22 chars).
- **Cylinders** are solid between `y0` and `y1`, with a walkable top.
- **Waters** are volumes:
  - `deep`: feet below `max.y` triggers a respawn (`PLAYER_FALL` reason `'water'`).
  - shallow: speed is multiplied by `shallowWaterFactor`.
- **Movers** move along `path` at `speed` (m/s), pausing `pauseS` at each end, pingpong. `phase` offsets the start (fraction of a full cycle). Their top is walkable and carries the player.
- **Blocks** can be toggled solid.
  - Effect `setSolid` true: the view animates from `offsetHidden` to 0 over `animMs`, then the collider becomes solid.
  - `setSolid` false: the collider becomes non-solid immediately, the view animates to `offsetHidden` and is then hidden.
- **Jump pads:** when the grounded player's feet are within `r` of `pos` (horizontal, |dy| < 0.3), call `Player.launch(target, apexAbove, lockMs)`.
- **Checkpoints** activate when the player is within `checkpointRadius`. Each one activates once, which calls `player.setCheckpoint` and emits the event.
- **Goal** is active only when every objective before the last one is done. Within `goalRadius` it emits `GOAL_REACHED`.
- **Gouttes** are collected within `goutteRadius` of the player centre (feet + 0.55).
- **Triggers** emit `TRIGGER_ENTER` / `TRIGGER_EXIT` on transitions of the feet point. There is no enter event if the player spawns inside.
- **Help bridges:** a `PLAYER_FALL` whose `lastSafe` **or** fall position lies in `zone` increments that bridge's counter. When `help.falls` (3) falls happen within `help.windowS` (90 s) and `assists.offerHelpBridge` is on, emit `HELP_OFFER` (once per bridge). `HELP_ACCEPTED` creates the block (non-solid, offset `[0,-1.5,0]`, 1000 ms) and sets it solid.
- **Objectives** are sequential. The current objective completes when its matcher count is reached (counted since level start). `onDone` effects then run. The level completes when the **last** objective is done.
- **`target: '@urgent'`** resolves to the broken ouvrage with the earliest deadline, or `null` when none is broken.
- **Process track:** `current` becomes `i` when `when[i]` matches (monotonic, never goes back).

---

## 6. Level data (complete)

All four files follow this template. Positions use the conventions of §2.1.

### 6.1 `L0_premier_jour.js` (tutorial, Ampasina)

```js
import { box, cyl, ramp, line, padArc } from 'a3d/levels/helpers.js';
export default {
  id: 'L0_premier_jour', index: 0, title: 'Premier jour au village', place: 'Ampasina',
  description: "Découvrez les trois gestes du technicien : se déplacer, sauter et agir. Réparez une borne fontaine et rendez l'eau à Tiana.",
  durationLabel: '≈ 4 min', theme: { sky: 'matin', fogNear: null, fogFar: null },
  abilities: { glide: false }, hud: { satisfaction: false, receipts: false, missionTimer: false }, satisfactionStart: 80,
  spawn: { pos: [0, 0, -3], yaw: 0 }, killY: -8, bounds: { min: [-10, -6], max: [10, 80] },
  parTimeS: 240, minTimeS: 60,
  stars: { s3: 'quiz_first_try', s3Label: 'Quiz réussi du premier coup' },
  quizSlots: [{ slot: 'q1', module: 'usage_intro', intro: 'Avant de réparer, une question :' }],
  ficheReflexe: ["Signalez toute fuite, même petite.", "Manœuvrez le robinet sans forcer.", "Chaque point d'eau est suivi dans Hydria."],
  statics: [
    box([-10, -1, -6], [10, 0, 26], 'grass'),               // village square + path
    box([-9, 0, -5], [-5, 2.6, -1], 'house_tin', { sign: 'BUREAU HYDRIA' }),
    box([-10, 0, 23.4], [10, 0.5, 24.0], 'brick'),          // muret (must jump)
    box([-10, -1, 26], [10, -0.6, 27], 'laterite'),         // caniveau, 0.6 m deep ditch (safe)
    box([-10, -1, 27], [10, 0, 40], 'grass'),
    box([-1.5, -1, 41.2], [1.5, 0, 44.2], 'rock'),          // stepping stone S1 (gaps 1.2 / 1.4 / 1.4)
    box([-0.5, -1, 45.6], [2.5, 0, 48.6], 'rock'),          // stepping stone S2
    box([-10, -1, 50], [10, 0, 80], 'grass'),
    box([-9.5, 0, 53.5], [-6, 2.6, 56.5], 'house_tin'),     // Aina's house
    box([6, 0, 57.5], [9.5, 2.6, 60.5], 'house_tin'),       // Tiana's house
    box([-3, 0, 69], [3, 4, 75], 'kiosque', { sign: 'KIOSQUE HYDRIA' }),
  ],
  waters: [{ min: [-10, -3, 40], max: [10, -0.4, 50], deep: true, flow: [1, 0] }],
  decor: [
    { kind: 'path', points: [[0, 0, -3], [0, 0, 8], [3, 0, 16], [4, 0, 19]], width: 2.2 },
    { kind: 'path', points: [[0, 0, 28], [0, 0, 40]], width: 2.2 },
    { kind: 'path', points: [[0, 0, 50], [0, 0, 63]], width: 2.2 },
    { kind: 'ravinala', pos: [-8, 0, 6] }, { kind: 'ravinala', pos: [8, 0, 8], yaw: 40 },
    { kind: 'ravinala', pos: [-8, 0, 18], yaw: 80 }, { kind: 'ravinala', pos: [8, 0, 32] },
    { kind: 'ravinala', pos: [-8, 0, 35], yaw: 120 }, { kind: 'ravinala', pos: [-8, 0, 65] }, { kind: 'ravinala', pos: [8, 0, 66], yaw: 200 },
    { kind: 'baobab', pos: [8, 0, 37], collider: { type: 'cyl', r: 1.0, h: 6 } },
    { kind: 'rock', pos: [-6, 0, 39.5], scale: 1.2 }, { kind: 'rock', pos: [6, 0, 50.5] },
    { kind: 'flowers', pos: [-3, 0, 12] }, { kind: 'bush', pos: [6, 0, 14] },
  ],
  movers: [], blocks: [],
  jumpPads: [{ id: 'pad1', pos: [0, 0, 63], r: 0.8, target: [0, 4, 72], apexAbove: 2.5, lockMs: 600 }],
  checkpoints: [{ id: 'cp1', pos: [0, 0, 28.5], yaw: 0 }, { id: 'cp2', pos: [0, 0, 52], yaw: 0 }],
  ouvrages: [{ id: 'bf1', kind: 'bf', name: 'Borne fontaine BF1', pos: [4, 0, 19], yaw: 180, state: 'broken', quizSlot: 'q1' }],
  usagers: [
    { id: 'aina', name: 'Aina', pos: [-4, 0, 55], yaw: 90, state: 'due', amount: 2500, branchement: 'BP', restoreBy: 'action', variant: 0 },
    { id: 'tiana', name: 'Tiana', pos: [4, 0, 59], yaw: 270, state: 'cut_off', amount: 3000, branchement: 'BP', restoreBy: 'action', variant: 1 },
  ],
  valves: [],
  npcs: [{ id: 'rasoa', name: 'Rasoa', role: 'cheffe', pos: [-2.5, 0, 1], yaw: 150, autoTalk: false, variant: 0, script: [
    { id: 'accueil', when: 'always', once: true, lines: ["Bonjour, je suis Rasoa, cheffe de site.", "Aujourd'hui, vous êtes Koto, technicien Hydria.", "Suivez l'objectif affiché en haut de l'écran."] },
    { id: 'rappel', when: 'always', lines: ["Courage, vous vous débrouillez très bien !"] },
  ] }],
  goal: { id: 'goal', pos: [1, 4, 73] },
  gouttes: [
    [0, 0.6, 2], [0, 0.6, 4], [0, 0.6, 6], [0.5, 0.6, 8], [1.2, 0.6, 10], [2, 0.6, 12], [2.8, 0.6, 14], [3.5, 0.6, 16],
    [2.5, 0.6, 20.5], [5.5, 0.6, 20.5],
    [1, 1.3, 23.7], [3, 1.3, 23.7], [1, 1.0, 26.5], [3, 1.0, 26.5],
    [0, 1.4, 40.6], [0, 0.9, 42.7], [1, 1.4, 44.9], [1, 0.9, 47.1], [1, 1.4, 49.3],
    [-2, 0.6, 53], [-2, 0.6, 56], [2, 0.6, 56], [2, 0.6, 59],
    ...padArc([0, 0, 63], [0, 4, 72], 2.5, 6),
    [-1.5, 4.6, 73.5],
  ],                                                         // total = 30
  triggers: [
    { id: 't_bf1', min: [0, -1, 15], max: [8, 3, 23] },
    { id: 't_muret', min: [-10, -1, 21], max: [10, 3, 23.4] },
    { id: 't_river', min: [-10, -1, 36], max: [10, 3, 40] },
    { id: 't_river_done', min: [-10, -1, 50], max: [10, 3, 54] },
    { id: 't_aina', min: [-8, -1, 51], max: [0, 3, 58] },
    { id: 't_pad', min: [-3, -1, 60], max: [3, 3, 66] },
  ],
  cameraZones: [{ id: 'L0_river', min: [-10, -3, 37], max: [10, 4, 50], yaw: 0, pitch: 32, distance: 9, blendS: 0.8, orbitLimitDeg: 30 }],
  helpBridges: [{ id: 'hb_river', zone: { min: [-10, -3, 38], max: [10, 3, 50] },
                  block: { shapes: [{ type: 'box', min: [-1.5, -0.3, 40], max: [1.5, 0, 50] }], style: 'pipe' } }],
  hints: [
    { id: 'h_move', text: 'Avancez avec {move}', idleMs: 2500, doneWhen: { event: 'goutte:collected', count: 3 } },
    { id: 'h_act', trigger: 't_bf1', anchorId: 'bf1', text: 'Approchez-vous, puis {act} pour réparer', doneWhen: { event: 'action:start', where: { id: 'bf1' } } },
    { id: 'h_jump', trigger: 't_muret', text: 'Sautez avec {jump}', idleMs: 1500, doneWhen: { event: 'player:jump', count: 2 } },
    { id: 'h_fall', showOn: { event: 'player:fall' }, maxShows: 1, durationMs: 3500, text: 'Pas de panique : vous revenez juste avant.' },
    { id: 'h_pay', trigger: 't_aina', anchorId: 'aina', text: "Approchez-vous d'Aina, puis {act} pour encaisser", doneWhen: { event: 'usager:paid', where: { id: 'aina' } } },
    { id: 'h_restore', showOn: { event: 'usager:state', where: { id: 'tiana', state: 'restore_pending' } }, idleMs: 0, anchorId: 'tiana',
      text: "Paiement reçu : remettez l'eau avec {act} !", doneWhen: { event: 'usager:restored', where: { id: 'tiana' } } },
    { id: 'h_pad', trigger: 't_pad', text: "Marchez sur le jet d'eau pour monter sur le toit", doneWhen: { event: 'player:jump', where: { kind: 'pad' } } },
  ],
  objectives: [
    { id: 'o1', text: "Avancez jusqu'à la borne fontaine BF1", target: 'bf1', done: { event: 'trigger:enter', where: { id: 't_bf1' } } },
    { id: 'o2', text: 'Réparez la borne fontaine BF1', target: 'bf1', done: { event: 'ouvrage:repaired', where: { id: 'bf1' } } },
    { id: 'o3', text: 'Franchissez le muret et le ruisseau', target: 'cp2', done: { event: 'trigger:enter', where: { id: 't_river_done' } } },
    { id: 'o4', text: "Encaissez le paiement d'Aina", target: 'aina', done: { event: 'usager:paid', where: { id: 'aina' } } },
    { id: 'o5', text: "Encaissez Tiana, puis remettez-lui l'eau", target: 'tiana', done: { event: 'usager:restored', where: { id: 'tiana' } } },
    { id: 'o6', text: "Prenez le jet d'eau et rejoignez le drapeau", target: 'goal', done: { event: 'goal:reached' } },
  ],
  process: null,
};
```

### 6.2 `L1_pompe_panne.js` (Andranomena)

```js
export default {
  id: 'L1_pompe_panne', index: 1, title: 'La pompe en panne', place: 'Andranomena',
  description: "Suivez une réparation de bout en bout : signalement, matériel du magasin, réparation, validation.",
  durationLabel: '≈ 5 min', theme: { sky: 'matin', fogNear: null, fogFar: null },
  abilities: { glide: false }, hud: { satisfaction: false, receipts: false, missionTimer: false }, satisfactionStart: 80,
  spawn: { pos: [0, 0, -3], yaw: 0 }, killY: -8, bounds: { min: [-20, -6], max: [16, 36] },
  parTimeS: 300, minTimeS: 90,
  stars: { s3: 'quiz_first_try', s3Label: 'Les 2 quiz réussis du premier coup' },
  quizSlots: [{ slot: 'q1', module: 'stocks_livraisons', intro: 'Avant de sortir le matériel :' },
              { slot: 'q2', module: 'planning_validation', intro: 'Avant de réparer :' }],
  ficheReflexe: ["Tout signalement devient une réparation suivie dans Hydria.", "Le matériel sort du magasin avec un bon de livraison.", "Une réparation n'est finie qu'après validation du responsable."],
  statics: [
    box([-8, -1, -6], [8, 0, 2], 'grass'),  box([-8, -1, 2], [6, 0, 14], 'grass'),   // zone A
    box([8, -1, -6], [16, 0, 2], 'grass'),                                           // A2 (south of plateau)
    box([-7.5, 0, -5.5], [-3.5, 2.6, -1.5], 'house_tin', { sign: 'BUREAU HYDRIA' }),
    box([-20, -1, -2], [-8, 0, 12], 'laterite'),                                     // B magasin yard
    box([-19.5, 0, -1.5], [-14.5, 3, 3.5], 'house_tin', { sign: 'MAGASIN' }),
    box([-20, -1, 22], [-2, 0, 36], 'grass'),                                        // D (BF3)
    box([4, -1, 22], [16, 0, 36], 'grass'),                                          // F
    box([6, -1, 18], [16, 0.8, 22], 'laterite'),                                     // terrace T1
    box([6, -1, 14], [16, 1.6, 18], 'laterite'),                                     // terrace T2
    box([6, -1, 2], [16, 2.4, 14], 'concrete'),                                      // plateau P (station); west edge = 2.4 m drop onto A
  ],
  waters: [
    { min: [-20, -3, 12], max: [-8, -0.4, 22], deep: true },                        // canal W1
    { min: [-8, -3, 14], max: [6, -0.4, 22], deep: true },                          // lagoon W2
    { min: [-2, -3, 22], max: [4, -0.4, 36], deep: true, flow: [0, 1] },            // ravine W3
  ],
  decor: [
    { kind: 'path', points: [[0, 0, -3], [-8, 0, 2], [-12, 0, 2]], width: 2.2 },
    { kind: 'path', points: [[-14, 0, 22], [-10, 0, 28]], width: 2.0 },
    { kind: 'ravinala', pos: [6, 0, -4] }, { kind: 'ravinala', pos: [-19, 0, 10] }, { kind: 'ravinala', pos: [-18, 0, 24] },
    { kind: 'ravinala', pos: [-3, 0, 34] }, { kind: 'ravinala', pos: [15, 0, 35] }, { kind: 'ravinala', pos: [5, 0, 35] },
    { kind: 'baobab', pos: [14.5, 0, 32], collider: { type: 'cyl', r: 1.0, h: 6 } },
    { kind: 'crate', pos: [-13.5, 0, 4] }, { kind: 'barrel', pos: [-13.8, 0, 5.2] },
    { kind: 'pipe', points: [[11, 2.45, 6], [11, 2.45, 3], [7, 2.45, 3]], radius: 0.15 },
  ],
  movers: [{ id: 'raft', size: [3, 0.4, 3], path: [[-14, -0.2, 13.6], [-14, -0.2, 20.4]], speed: 1.2, pauseS: 1.5, mode: 'pingpong', phase: 0, style: 'wood' }],
  blocks: [{ id: 'bridge1', shapes: [{ type: 'box', min: [-2, -0.3, 27], max: [4, 0, 31] }], style: 'wood',
             solidAtStart: false, offsetHidden: [6, 0, 0], animMs: 1200 }],
  jumpPads: [],
  checkpoints: [{ id: 'cp1', pos: [-14, 0, 24.5], yaw: 0 }, { id: 'cp2', pos: [10, 0, 26], yaw: 180 }, { id: 'cp3', pos: [11, 2.4, 13], yaw: 180 }],
  ouvrages: [
    { id: 'bf3', kind: 'bf', name: 'Borne fontaine BF3', pos: [-10, 0, 30], yaw: 180, state: 'broken', requiresItem: 'caisse_materiel', quizSlot: 'q2' },
    { id: 'station', kind: 'station', name: 'Station de pompage', pos: [11, 2.4, 8], yaw: 0, state: 'broken', requiresItem: 'caisse_materiel' },
  ],
  usagers: [],
  valves: [{ id: 'v1', pos: [-3.5, 0, 24.5], yaw: 180, label: 'Sortir le pont', effects: [{ op: 'setSolid', id: 'bridge1', solid: true }] }],
  npcs: [
    { id: 'rasoa', name: 'Rasoa', role: 'cheffe', pos: [1.5, 0, 1.5], yaw: 200, script: [
      { id: 'signalement', when: { objective: 'o1' }, once: true, lines: ["Bonjour ! Hery signale une fuite à la borne fontaine BF3.", "La station de pompage fait aussi des étincelles.", "Je crée la réparation dans Hydria : statut « Signalée ». Allez chercher le matériel au magasin."] },
      { id: 'validation', when: { objective: 'o7' }, once: true, lines: ["Les deux ouvrages fonctionnent ? Parfait.", "Je contrôle et je valide la réparation dans Hydria.", "Une réparation n'est terminée qu'après validation !"] },
      { id: 'rappel', when: 'always', lines: ["Suivez l'objectif affiché en haut de l'écran."] } ] },
    { id: 'fara', name: 'Fara', role: 'magasinier', pos: [-12, 0, 1.5], yaw: 90, script: [
      { id: 'remise', when: { objective: 'o2' }, once: true, quizSlot: 'q1', lines: ["Voici la caisse : joint, clé et fusible.", "Le matériel sort du magasin avec un bon de livraison."],
        effects: [{ op: 'give', kind: 'caisse_materiel', count: 1 }] },
      { id: 'rappel', when: 'always', lines: ["Le magasin est ouvert : revenez si besoin."] } ] },
  ],
  goal: null,
  gouttes: [
    [0, 0.6, 1], [-3, 0.6, 4], [-6, 0.6, 6],
    [-10, 0.6, 5], [-12, 0.6, 8], [-14, 0.6, 10], [-17, 0.6, 7], [-17, 0.6, 4],
    [-14, 1.0, 15], [-14, 1.0, 17], [-14, 1.0, 19],
    [-14, 0.6, 26], [-12, 0.6, 28], [-8, 0.6, 32], [-6, 0.6, 34], [-16, 0.6, 32], [-18, 0.6, 34], [-4, 0.6, 28],
    [-1, 0.8, 29], [1, 0.8, 29], [3, 0.8, 29],
    [6, 0.6, 30], [8, 0.6, 33], [12, 0.6, 33], [14, 0.6, 29], [12, 0.6, 25], [8, 0.6, 24],
    [9, 1.5, 20], [13, 1.5, 20], [9, 2.3, 16], [13, 2.3, 16],
    [8, 3.0, 12], [14, 3.0, 12], [14, 3.0, 4], [8, 3.0, 4],
    [5, 0.6, 4], [3, 0.6, 6], [-4, 0.6, -2], [4, 0.6, -2], [0, 0.6, -5],
  ],                                                         // total = 40
  triggers: [
    { id: 't_raft', min: [-20, -1, 8], max: [-8, 3, 12] },
    { id: 't_canal_nord', min: [-20, -1, 22], max: [-2, 3, 26] },
    { id: 't_drop', min: [6, 1.5, 2], max: [9, 5, 14] },
  ],
  cameraZones: [
    { id: 'L1_canal', min: [-20, -1, 8], max: [-8, 6, 24], yaw: 0, pitch: 35, distance: 10, blendS: 0.8, orbitLimitDeg: 30 },
    { id: 'L1_terraces', min: [4, -1, 12], max: [16, 8, 24], yaw: 180, pitch: 30, distance: 9, blendS: 0.8, orbitLimitDeg: 30 },
  ],
  helpBridges: [{ id: 'hb_canal', zone: { min: [-20, -3, 10], max: [-8, 3, 22] },
                  block: { shapes: [{ type: 'box', min: [-19, -0.3, 12], max: [-17, 0, 22] }], style: 'pipe' } }],
  hints: [
    { id: 'h_talk', idleMs: 4000, anchorId: 'rasoa', text: 'Approchez-vous de Rasoa et appuyez sur {act} pour parler', doneWhen: { event: 'npc:step', where: { npcId: 'rasoa', stepId: 'signalement' } } },
    { id: 'h_raft', trigger: 't_raft', text: 'Attendez le radeau, puis montez dessus', doneWhen: { event: 'trigger:enter', where: { id: 't_canal_nord' } } },
    { id: 'h_drop', trigger: 't_drop', text: 'Pour descendre, maintenez {move} vers le bord', doneWhen: { event: 'npc:step', where: { npcId: 'rasoa', stepId: 'validation' } } },
  ],
  objectives: [
    { id: 'o1', text: 'Parlez à Rasoa (signalement de la panne)', target: 'rasoa', done: { event: 'npc:step', where: { npcId: 'rasoa', stepId: 'signalement' } } },
    { id: 'o2', text: 'Allez chercher le matériel au magasin', target: 'fara', done: { event: 'item:received', where: { kind: 'caisse_materiel' } } },
    { id: 'o3', text: 'Traversez le canal sur le radeau', target: 'cp1', done: { event: 'trigger:enter', where: { id: 't_canal_nord' } } },
    { id: 'o4', text: 'Réparez la borne fontaine BF3', target: 'bf3', done: { event: 'ouvrage:repaired', where: { id: 'bf3' } } },
    { id: 'o5', text: 'Ouvrez la vanne pour sortir le pont', target: 'v1', done: { event: 'valve:opened', where: { id: 'v1' } } },
    { id: 'o6', text: 'Montez réparer la station de pompage', target: 'station', done: { event: 'ouvrage:repaired', where: { id: 'station' } } },
    { id: 'o7', text: 'Redescendez faire valider la réparation par Rasoa', target: 'rasoa', done: { event: 'npc:step', where: { npcId: 'rasoa', stepId: 'validation' } } },
  ],
  process: { title: 'Réparation BF3 + station', steps: ['Signalée', 'Planifiée', 'En cours', 'Terminée', 'Validée'], when: [
    { event: 'npc:step', where: { npcId: 'rasoa', stepId: 'signalement' } },
    { event: 'item:received', where: { kind: 'caisse_materiel' } },
    { event: 'action:start', where: { id: 'bf3' } },
    { event: 'ouvrage:repaired', where: { id: 'station' } },
    { event: 'npc:step', where: { npcId: 'rasoa', stepId: 'validation' } } ] },
};
```

### 6.3 `L2_tournee.js` (Ampasina-Haut)

```js
export default {
  id: 'L2_tournee', index: 2, title: "Tournée d'encaissement", place: 'Ampasina-Haut',
  description: "Encaissez quatre usagers, remettez l'eau chez Mamy et rapportez les reçus à la caissière. Nouveau : planer !",
  durationLabel: '≈ 5 min', theme: { sky: 'midi', fogNear: null, fogFar: null },
  abilities: { glide: true }, hud: { satisfaction: true, receipts: true, missionTimer: false }, satisfactionStart: 80,
  spawn: { pos: [0, 0, -3], yaw: 0 }, killY: -8, bounds: { min: [-12, -6], max: [16, 70] },
  parTimeS: 330, minTimeS: 100,
  stars: { s3: 'tournee_a_l_heure', s3Label: "Tournée à l'heure : Tiana et Hery payés à temps, eau remise chez Mamy" },
  quizSlots: [{ slot: 'q1', module: 'encaissements', intro: 'Avant de régulariser cet impayé :' },
              { slot: 'q2', module: 'encaissements', intro: "Avant de remettre l'eau :" },
              { slot: 'q3', module: 'releves_facturation', intro: 'Avant de pointer les reçus :' }],
  ficheReflexe: ["Date limite de paiement : le 5 du mois pour un kiosque, le 15 pour un BP ou une BI volume.", "Après le paiement d'un usager coupé, la remise en eau est obligatoire.", "Chaque reçu revient à la caissière pour être pointé."],
  statics: [
    box([-8, -1, -6], [8, 0, 8], 'laterite'),
    box([-12, -1, 8], [16, 0, 46], 'laterite'),             // E1 street
    box([-12, -1, 46], [4, 0, 58], 'laterite'),             // E2
    box([9, -1, 46], [16, 0, 58], 'laterite'),              // E3
    box([-12, -1, 58], [16, 0, 70], 'laterite'),            // E4
    box([-7.5, 0, -5.5], [-3.5, 2.6, -1.5], 'house_tin', { sign: 'BUREAU HYDRIA' }),
    box([-12, 0, 10], [-9, 2.6, 14], 'house_tin'),          // Tiana
    box([-3, 0, 15], [-1, 1.0, 17], 'wood'), box([2, 0, 18], [4, 1.0, 20], 'wood'),   // market stalls
    box([5, 0, 22], [11, 1.2, 28], 'concrete'),             // estrade
    ramp([1, 0, 23], [5, 1.2, 27], '+x', 'concrete'),
    box([7, 1.2, 26], [11, 3.8, 28], 'kiosque', { sign: 'KIOSQUE HYDRIA' }),
    box([-12, 0, 34], [-9, 2.6, 38], 'house_tin'),          // Mamy
    box([-12, 0, 44], [-8, 1.1, 48], 'house_tin'),          // R1
    box([-12, 0, 49], [-8, 2.2, 53], 'house_tin'),          // R2
    box([-7, 0, 49], [-3, 3.3, 53], 'house_tin'),           // R3
    box([-2, 0, 49], [4, 4.4, 54], 'house_tin'),            // R4 (valve)
    box([9, 0, 47], [15, 3.0, 57], 'concrete'),             // H (Hery), reachable only by gliding
    box([-6, 0, 64], [6, 2.8, 69], 'house_tin', { sign: 'CAISSE' }),
  ],
  waters: [{ min: [4, -3, 46], max: [9, -0.4, 58], deep: true, flow: [0, 1] }],   // channel under the glide gap
  decor: [
    { kind: 'path', points: [[0, 0, -3], [0, 0, 62]], width: 3.0 },
    { kind: 'ravinala', pos: [14, 0, 12] }, { kind: 'ravinala', pos: [14, 0, 33] }, { kind: 'ravinala', pos: [-11, 0, 62] },
    { kind: 'tree', pos: [14, 0, 62] }, { kind: 'cart', pos: [12, 0, 17], yaw: 90, collider: { type: 'box', size: [1.6, 1.2, 3] } },
    { kind: 'crate', pos: [10.5, 1.2, 24] }, { kind: 'barrel', pos: [-8.6, 0, 9.5] },
    { kind: 'fence', points: [[4, 0, 45.8], [4, 0, 46]] },
  ],
  movers: [], blocks: [], jumpPads: [],
  checkpoints: [{ id: 'cp1', pos: [0, 0, 30], yaw: 0 }, { id: 'cp2', pos: [2.5, 4.4, 50], yaw: 90 }, { id: 'cp3', pos: [12, 3.0, 49], yaw: 0 }],
  ouvrages: [],
  usagers: [
    { id: 'tiana', name: 'Tiana', pos: [-7.5, 0, 12], yaw: 90, state: 'due', amount: 3000, branchement: 'BP', overdueAtS: 150, restoreBy: 'action', variant: 1 },
    { id: 'soa', name: 'Soa', pos: [7.5, 1.2, 24.5], yaw: 270, state: 'overdue', amount: 5000, branchement: 'kiosque', quizSlot: 'q1', restoreBy: 'action', variant: 2 },
    { id: 'mamy', name: 'Mamy', pos: [-7.5, 0, 36], yaw: 90, state: 'cut_off', amount: 3500, branchement: 'BP', restoreBy: 'valve', variant: 3 },
    { id: 'hery', name: 'Hery', pos: [12, 3.0, 52], yaw: 270, state: 'due', amount: 4000, branchement: 'BI', overdueAtS: 150, restoreBy: 'action', variant: 4 },
  ],
  valves: [{ id: 'v_mamy', pos: [1, 4.4, 52], yaw: 270, quizSlot: 'q2', label: "Remettre l'eau chez Mamy", effects: [{ op: 'restore', id: 'mamy' }] }],
  npcs: [
    { id: 'rasoa', name: 'Rasoa', role: 'cheffe', pos: [1.5, 0, 1.5], yaw: 200, autoTalk: true, script: [
      { id: 'brief', when: 'always', once: true, lines: ["Votre tournée : Tiana, Soa, Mamy, puis Hery.", "Les voyants au-dessus des usagers montrent leur état : jaune à payer, orange impayé, rouge eau coupée.", "Rapportez ensuite les reçus à Voahirana, à la caisse."] },
      { id: 'rappel', when: 'always', lines: ["Bonne tournée ! Suivez l'objectif en haut de l'écran."] } ] },
    { id: 'voahirana', name: 'Voahirana', role: 'caissiere', pos: [0, 0, 62.5], yaw: 180, script: [
      { id: 'remise', when: { hasItem: { kind: 'recu', count: 4 } }, once: true, quizSlot: 'q3', lines: ["Merci ! Je pointe les 4 reçus de la tournée.", "Chaque reçu doit revenir à la caisse pour être enregistré."],
        effects: [{ op: 'take', kind: 'recu', count: 4 }] },
      { id: 'rappel', when: 'always', lines: ["Rapportez-moi les 4 reçus de la tournée."] } ] },
  ],
  goal: null,
  gouttes: [
    [0, 0.6, 2], [0, 0.6, 5], [-3, 0.6, 9], [-5, 0.6, 11],
    [-2, 1.6, 16], [3, 1.6, 19], [0, 0.6, 22],
    [2, 0.9, 25], [4, 1.5, 25], [9, 1.8, 23],
    [0, 0.6, 30], [-3, 0.6, 33], [-5, 0.6, 38],
    [-10, 0.6, 41], [-10, 1.7, 46], [-10, 2.8, 51], [-5, 3.9, 51], [-1, 5.0, 52], [3, 5.0, 52],
    ...line([5, 6.3, 51.5], [8, 6.0, 51.5], 4),
    [10, 3.6, 49], [14, 3.6, 49], [14, 3.6, 55], [10, 3.6, 55],
    [6, 0.6, 59], [3, 0.6, 60], [-3, 0.6, 60], [-6, 0.6, 58], [-8, 0.6, 64],
    [12, 0.6, 30], [14, 0.6, 40], [13, 0.6, 20], [-10, 0.6, 26], [-10, 0.6, 30], [8, 0.6, 36], [5, 0.6, 44], [-4, 0.6, 44],
  ],                                                         // total = 40
  triggers: [{ id: 't_roofs', min: [-12, -1, 40], max: [-6, 3, 44] }, { id: 't_glide', min: [-2, 4, 49], max: [4, 9, 54] }],
  cameraZones: [{ id: 'L2_roofs', min: [-12, -1, 40], max: [16, 12, 58], yaw: 60, pitch: 28, distance: 11, blendS: 0.8, orbitLimitDeg: 30 }],
  helpBridges: [{ id: 'hb_glide', zone: { min: [4, -3, 44], max: [9, 6, 60] },
                  block: { shapes: [{ type: 'ramp', min: [4, 3.0, 50.5], max: [9, 4.4, 53], up: '-x', thickness: 0.3 }], style: 'pipe' } }],
  hints: [
    { id: 'h_roof', trigger: 't_roofs', text: 'Grimpez de toit en toit avec {jump}', doneWhen: { event: 'valve:opened', where: { id: 'v_mamy' } } },
    { id: 'h_glide', trigger: 't_glide', idleMs: 500, maxShows: 5, text: "Sautez, puis maintenez {jump} pendant la chute pour planer jusqu'à Hery",
      doneWhen: { event: 'player:glide', where: { active: true } } },
  ],
  objectives: [
    { id: 'o1', text: 'Encaissez Tiana (branchement particulier)', target: 'tiana', done: { event: 'usager:paid', where: { id: 'tiana' } } },
    { id: 'o2', text: "Régularisez l'impayé de Soa au kiosque", target: 'soa', done: { event: 'usager:paid', where: { id: 'soa' } } },
    { id: 'o3', text: 'Encaissez Mamy (eau coupée)', target: 'mamy', done: { event: 'usager:paid', where: { id: 'mamy' } } },
    { id: 'o4', text: "Remettez l'eau chez Mamy : ouvrez la vanne sur les toits", target: 'v_mamy', done: { event: 'usager:restored', where: { id: 'mamy' } } },
    { id: 'o5', text: "Planez jusqu'à Hery et encaissez-le", target: 'hery', done: { event: 'usager:paid', where: { id: 'hery' } } },
    { id: 'o6', text: 'Rapportez les 4 reçus à Voahirana (caisse)', target: 'voahirana', done: { event: 'npc:step', where: { npcId: 'voahirana', stepId: 'remise' } } },
  ],
  process: null,
};
```

### 6.4 `L3_chateau.js` (hub, then scaffold)

```js
export default {
  id: 'L3_chateau', index: 3, title: "Journée chargée au château d'eau", place: 'Andranomena-Centre',
  description: "Les pannes s'enchaînent : traitez la plus urgente, puis grimpez remplir le château d'eau.",
  durationLabel: '≈ 6 min', theme: { sky: 'midi', fogNear: null, fogFar: null },
  abilities: { glide: true }, hud: { satisfaction: true, receipts: false, missionTimer: true }, satisfactionStart: 80,
  spawn: { pos: [0, 0, -14], yaw: 0 }, killY: -8, bounds: { min: [-20, -20], max: [20, 40] },
  parTimeS: 360, minTimeS: 80,
  stars: { s3: 'service_exemplaire', s3Label: 'Service exemplaire : aucune panne manquée' },
  quizSlots: [{ slot: 'q1', module: 'dashboards_controles', intro: 'Avant de tourner la vanne :' },
              { slot: 'q2', module: 'data_villages_ouvrages', intro: 'Avant de tourner la vanne :' },
              { slot: 'q3', module: 'dashboards_controles', intro: 'Avant la vanne maîtresse :' }],
  ficheReflexe: ["Une vanne fermée prive tout un quartier d'eau.", "Traitez d'abord la panne la plus ancienne.", "Les tableaux de bord servent à repérer les anomalies."],
  statics: [
    box([-20, -1, -20], [20, 0, 20], 'grass'),                                // hub
    box([-20, -1, 27], [20, 0, 40], 'grass'),                                 // behind the château (decor only, unreachable)
    box([-20, 0, 25], [20, 12.5, 26], 'invisible'),                           // back wall of the scaffold
    box([-8, 0, 2], [-4, 2.6, 6], 'house_tin'), box([4, 0, 6], [8, 2.6, 10], 'house_tin'),
    box([2, 0, -8], [4, 1.0, -6], 'wood'), box([-4, 0, -4], [-2, 1.0, -2], 'wood'),          // stalls
    box([-3.6, 0, 3], [-2, 1.2, 5], 'wood'), box([8.4, 0, 7], [9.8, 1.2, 9], 'wood'),        // climb aids to the roofs
    // scaffold row 1 (z 22..25)
    box([-10, -1, 20], [-6, 0.8, 25], 'wood'),                                // P1 (entry from the hub, behind the gate)
    box([-4.4, 1.4, 22], [-0.4, 1.8, 25], 'wood'),                            // P2
    box([1.2, 2.4, 22], [5.2, 2.8, 25], 'wood'),                              // P3
    box([6.8, 3.4, 22], [10.8, 3.8, 25], 'wood'),                             // P4 balcony 1
    // scaffold row 2
    box([6.8, 7.6, 22], [10.8, 8.0, 25], 'wood'),                             // P5
    box([1.2, 8.6, 22], [5.2, 9.0, 25], 'wood'),                              // P6
    box([-4.4, 9.6, 22], [-0.4, 10.0, 25], 'wood'),                           // P7 balcony 2
    box([-10, 10.6, 22], [-6, 11.0, 25], 'wood'),                             // P8 balcony 3 + pad
  ],
  waters: [{ min: [-20, -3, 20], max: [20, -0.4, 27], deep: true }],          // settling basin under the scaffold
  decor: [
    { kind: 'pipe', points: [[0, -0.2, 27], [0, 0.15, 19], [-14, 0.15, 8]], radius: 0.18 },
    { kind: 'pipe', points: [[0, 0.15, 10], [14, 0.15, -4]], radius: 0.15 },
    { kind: 'pipe', points: [[0, 0.15, 10], [-12, 0.15, -12]], radius: 0.15 },
    { kind: 'ravinala', pos: [-18, 0, -18] }, { kind: 'ravinala', pos: [18, 0, -18] }, { kind: 'ravinala', pos: [18, 0, 10] },
    { kind: 'baobab', pos: [16, 0, 14], collider: { type: 'cyl', r: 1.0, h: 6 } },
    { kind: 'rice_patch', pos: [14, 0, -14], size: [8, 6] }, { kind: 'flowers', pos: [-15, 0, 0] },
  ],
  movers: [{ id: 'lift', size: [2.5, 0.4, 3], path: [[12.55, 3.6, 23.5], [12.55, 7.8, 23.5]], speed: 1.0, pauseS: 1.5, mode: 'pingpong', phase: 0, style: 'metal' }],
  blocks: [{ id: 'gate', style: 'metal', solidAtStart: true, offsetHidden: [0, -2.4, 0], animMs: 1000, shapes: [
    { type: 'box', min: [-11, 0, 19.4], max: [-5, 2.2, 20] },
    { type: 'box', min: [-11, 0, 20], max: [-10, 2.2, 21.5] },
    { type: 'box', min: [-6, 0, 20], max: [-5, 2.2, 21.5] } ] }],
  jumpPads: [{ id: 'pad_top', pos: [-7, 11.0, 23.5], r: 0.7, target: [-2, 15, 29], apexAbove: 1.5, lockMs: 600 }],
  checkpoints: [{ id: 'cp1', pos: [8.5, 3.8, 23.3], yaw: 90 }, { id: 'cp2', pos: [-1.5, 10.0, 23.3], yaw: 270 }, { id: 'cp3', pos: [-9.3, 11.0, 22.7], yaw: 90 }],
  ouvrages: [
    { id: 'bf2', kind: 'bf', name: 'Borne fontaine BF2', pos: [-14, 0, 8], yaw: 90, state: 'healthy', failAtS: 8, deadlineS: 35 },
    { id: 'pmh', kind: 'pompe', name: 'Pompe PMH Est', pos: [14, 0, -4], yaw: 270, state: 'healthy', failAtS: 30, deadlineS: 35 },
    { id: 'kiosque_so', kind: 'kiosque', name: 'Kiosque Sud-Ouest', pos: [-12, 0, -12], yaw: 90, state: 'healthy', failAtS: 34, deadlineS: 35 },
    { id: 'chateau', kind: 'chateau', name: "Château d'eau", pos: [0, 0, 31], yaw: 180, state: 'healthy', interactive: false,
      params: { tankBottom: 12.6, tankTop: 15, radius: 6, level: 0 },
      colliders: [ { type: 'cyl', c: [0, 31], r: 6, y0: 12.6, y1: 15, style: 'metal' },
                   { type: 'cyl', c: [-4.2, 27.2], r: 0.45, y0: 0, y1: 12.6 }, { type: 'cyl', c: [4.2, 27.2], r: 0.45, y0: 0, y1: 12.6 },
                   { type: 'cyl', c: [-4.2, 34.8], r: 0.45, y0: 0, y1: 12.6 }, { type: 'cyl', c: [4.2, 34.8], r: 0.45, y0: 0, y1: 12.6 } ] },
  ],
  usagers: [],
  valves: [
    { id: 'v1', pos: [9.8, 3.8, 24.2], yaw: 180, quizSlot: 'q1', label: 'Ouvrir la vanne 1', effects: [{ op: 'setLevel', id: 'chateau', value: 0.33 }] },
    { id: 'v2', pos: [-3.6, 10.0, 24.2], yaw: 180, quizSlot: 'q2', label: 'Ouvrir la vanne 2', effects: [{ op: 'setLevel', id: 'chateau', value: 0.66 }] },
    { id: 'v3', pos: [-9.2, 11.0, 24.2], yaw: 180, quizSlot: 'q3', label: 'Ouvrir la vanne maîtresse', effects: [{ op: 'setLevel', id: 'chateau', value: 1.0 }] },
  ],
  npcs: [{ id: 'rasoa', name: 'Rasoa', role: 'cheffe', pos: [1.5, 0, -11], yaw: 200, autoTalk: true, script: [
    { id: 'brief', when: 'always', once: true, lines: ["Journée chargée : les ouvrages vont tomber en panne.", "Quand plusieurs pannes arrivent, traitez d'abord la plus ancienne.", "Ensuite, montez remplir le château d'eau."] },
    { id: 'rappel', when: 'always', lines: ["La flèche vous montre la panne la plus urgente."] } ] }],
  goal: { id: 'goal', pos: [0, 15, 32] },
  gouttes: [
    ...line([-4, 0.6, -10], [4, 0.6, -10], 5), ...line([-6, 0.6, -2], [-12, 0.6, 6], 4), ...line([5, 0.6, -9], [12, 0.6, -5], 4),
    [-6, 3.2, 4], [6, 3.2, 8], [3, 1.6, -7], [-3, 1.6, -3], [-9, 0.6, -9], [-6, 0.6, -12], [-10, 0.6, -15],
    [-9, 1.4, 23.5], [-7, 1.4, 23.5], [-5.2, 2.6, 23.5], [-3.4, 2.4, 23.5], [-1.4, 2.4, 23.5], [0.4, 3.6, 23.5],
    [2.2, 3.4, 23.5], [4.2, 3.4, 23.5], [6.0, 4.6, 23.5], [7.8, 4.4, 23.0], [9.0, 4.4, 23.0],
    [12.55, 5.0, 23.5], [12.55, 6.6, 23.5],
    [7.8, 8.6, 23.5], [9.8, 8.6, 23.5], [6.0, 9.8, 23.5], [2.2, 9.6, 23.5], [4.2, 9.6, 23.5], [0.4, 10.8, 23.5],
    [-2.4, 10.6, 23.0], [-1.0, 10.6, 23.0], [-5.2, 11.8, 23.5], [-8.5, 11.6, 23.0], [-6.6, 11.6, 22.6],
    ...padArc([-7, 11.0, 23.5], [-2, 15, 29], 1.5, 4), [1, 15.6, 31], [-1, 15.6, 33],
  ],                                                         // total = 20 + 24 + 6 = 50
  triggers: [
    { id: 't_gate', min: [-12, -1, 15], max: [-4, 3, 20] },
    { id: 't_lift', min: [6.8, 3.5, 22], max: [11, 6, 25] },
    { id: 't_row2', min: [-11, 7.5, 21], max: [14, 12, 26] },
  ],
  cameraZones: [{ id: 'L3_scaffold', min: [-13, 0, 18], max: [15, 20, 27], yaw: 0, pitch: 12, distance: 15, blendS: 1.0, orbitLimitDeg: 15, targetLock: { z: 23.5 } }],
  helpBridges: [],
  hints: [
    { id: 'h_prio', showOn: { event: 'ouvrage:broken' }, idleMs: 0, maxShows: 1, durationMs: 4500, text: 'Une panne ! Suivez la flèche et réparez avec {act}' },
    { id: 'h_two', showOn: { event: 'ouvrage:broken', count: 2 }, idleMs: 0, maxShows: 1, durationMs: 4500, text: "Plusieurs pannes : commencez par la plus ancienne." },
    { id: 'h_gate', trigger: 't_gate', text: 'La passerelle ouvrira quand toutes les pannes seront traitées.', doneWhen: { event: 'objective:done', where: { id: 'o1' } } },
    { id: 'h_lift', trigger: 't_lift', text: "Attendez l'ascenseur, puis montez dessus", doneWhen: { event: 'trigger:enter', where: { id: 't_row2' } } },
  ],
  objectives: [
    { id: 'o1', text: 'Réparez les pannes des ouvrages ({done}/{total})', target: '@urgent', done: { event: 'ouvrage:resolved', count: 3, total: 3 },
      onDone: [{ op: 'setSolid', id: 'gate', solid: false }, { op: 'feed', text: "Toutes les pannes sont traitées : montez remplir le château d'eau.", tone: 'success' }] },
    { id: 'o2', text: "Ouvrez la vanne 1 du château d'eau", target: 'v1', done: { event: 'valve:opened', where: { id: 'v1' } } },
    { id: 'o3', text: 'Ouvrez la vanne 2', target: 'v2', done: { event: 'valve:opened', where: { id: 'v2' } } },
    { id: 'o4', text: 'Ouvrez la vanne maîtresse', target: 'v3', done: { event: 'valve:opened', where: { id: 'v3' } } },
    { id: 'o5', text: 'Montez sur la cuve et rejoignez le drapeau', target: 'goal', done: { event: 'goal:reached' } },
  ],
  process: null,
};
```

`levels/index.js` exports:
- `LEVELS = [L0, L1, L2, L3]`
- `getLevel(n)`
- `LEVEL_META = LEVELS.map(l => ({ index, id, title, place, description, durationLabel, gouttes: l.gouttes.length, s3Label }))`

**P4 adds a load-time sanity check (dev only).** It warns when:
- `gouttes.length` differs from the server value in the bootstrap `levels_meta`;
- any id is duplicated;
- a matcher references an unknown id.

---

## 7. Collision and controller (P3)

### 7.1 `physics/CollisionWorld.js`

```js
export class CollisionWorld {
  constructor()
  addBox(min, max, opts = {}) : Collider          // opts: {id?, walkable=true, solid=true, cameraIgnore=false, tag?, userData?}
  addCylinder(cx, cz, r, y0, y1, opts = {}) : Collider
  addRamp(min, max, up, thickness = 0.4, opts = {}) : Collider
  addMover(size, opts = {}) : MoverCollider       // centre set each fixed step with setCenter
  addVolume(min, max, kind /* 'water_deep'|'water_shallow' */, id = null) : Volume
  setSolid(collider, solid) : void
  remove(colliderOrVolume) : void
  setBounds(minX, minZ, maxX, maxZ) : void
  setKillY(y) : void
  build() : void                                  // build the static broadphase (uniform grid, 4 m cells); call after static adds
  groundAt(x, z, maxY, expand = 0, out = {}) : { y:number, collider:Collider|null }  // highest walkable top ≤ maxY+1e-3 covering (x,z) with the footprint grown by `expand`; y = -Infinity if none
  overlapVolumes(x, y, z, out = []) : Volume[]    // volumes whose AABB contains the point (y < max.y)
  segmentBlocked(ax, ay, az, bx, by, bz) : number // first-hit fraction t in [0,1] against solid, non-cameraIgnore boxes/cylinders/ramps (AABB approximation); 1 = clear
  // internal for Player: resolveHorizontal(...), ceilingAt(...)
}
// Collider: {kind:'box'|'cyl'|'ramp'|'mover', id, min:[x,y,z], max:[x,y,z], solid, walkable, cameraIgnore, userData}
// MoverCollider adds: setCenter(x,y,z), center:{x,y,z}, delta:{x,y,z} (last step), velocity:{x,y,z} (m/s)
// Volume: {kind, id, min, max}
```

- A ramp surface height at a point is computed at the point clamped into the footprint, using the `up` axis.
- Movers are not in the grid; they are always tested (≤ 2 per level).

### 7.2 `player/Player.js`

```js
export class Player {
  constructor({ engine, world, bus, assists, abilities })
  position: THREE.Vector3        // feet, simulation state
  renderPosition: THREE.Vector3  // interpolated, for visuals and camera
  velocity: THREE.Vector3
  yaw: number                    // facing, radians (facing convention)
  grounded: boolean
  groundRef: number              // y of the last ground touched (read by the camera)
  character: CharacterView       // created with createCharacter('technicien', {toolbox:true})
  abilities: { glide: boolean }
  stats: { falls: number, jumps: number }
  spawn(pos, yawDeg) : void      // teleport, clear velocity, reset the safe ring, set the checkpoint
  setCheckpoint(pos, yawDeg) : void
  setInputEnabled(enabled) : void
  setActionLock(locked) : void   // no movement/jump; facing frozen; pose 'work'
  fixedUpdate(dt, input /* InputState */, moveYaw /* camera yaw ψ used as move frame */) : void
  update(dt, alpha) : void       // interpolation, visual turning, squash, pose, blob shadow, landing marker
  respawn(reason) : void         // fade sequence (§7.4)
  autoWalkTo(target /*[x,y,z]*/, faceYawDeg) : Promise<boolean>
  launch(target, apexAbove, lockMs) : void
  isInvulnerable() : boolean
  dispose() : void
}
```

**Fixed-step algorithm** (`dt = 1/60`, in this order):

1. **Carry.** If the support collider recorded last step is a mover, add `mover.delta` to the position.
2. **Input to target velocity.**
   - Stick magnitude `m` below `stickDeadzone` counts as 0.
   - Speed curve: `m ≤ 0.5` → `walkSpeed·m/0.5`; otherwise `walkSpeed + (runSpeed − walkSpeed)·(m − 0.5)/0.5`.
   - `input.walk` caps the speed at `walkSpeed`. Shallow water multiplies it by 0.6.
   - Direction comes from the `moveYaw` frame (§2.1).
3. **Horizontal velocity.**
   - On the ground: if there is input, `vh = dir · approach(|vh|, target, groundAccel·dt)` (direction changes instantly). Without input, `|vh|` approaches 0 at `groundDecel`.
   - In the air: `vh += clampLength(targetVel − vh, (input ? airAccel : airDecel)·dt)`.
   - While gliding, `|vh| ≤ glide.maxHSpeed`.
   - During the launch lock or the action lock, input is ignored.
4. **Jump.**
   - A press is buffered for `bufferMs`.
   - Jump if grounded, or if within `coyoteMs` of leaving the ground without having jumped: `vy = 10.10`. Emit `PLAYER_JUMP`.
   - **On leaving a mover**, add the mover's velocity to the player's velocity.
   - Releasing the jump button while `vy > cutVelocity` sets `vy = cutVelocity`.
5. **Glide.** Requires `abilities.glide`, airborne, `vy ≤ 0` and `jumpHeld`, with the glide time below `durationS` unless `assists.infiniteGlide`.
   - While active: `vy = max(vy, −fallSpeed)`.
   - Emit `PLAYER_GLIDE {active}` on each change. Glide time resets on landing.
6. **Gravity.** `vy -= (vy > 0 ? gravityUp : gravityDown)·dt`, then clamp to `−terminalVelocity`. During a launch, use `pad.gravity` in both directions until landing.
7. **Horizontal move with substeps** (substep length ≤ `maxSubstep`).
   - For each solid collider overlapping the vertical span `(feet + stepUp, feet + height)`, push the circle (r 0.35) out:
     - box: closest point of the rect;
     - cylinder: radial push;
     - ramp: solid where its surface height at the point is above `feet + stepUp`.
   - Remove the velocity component along the push normal.
   - **Safe edges** (if `assists.safeEdges` and grounded): a candidate position is rejected when `groundAt(cand, feet + stepUp, 0)` drops by more than `safeEdgeDrop` and the stick has not pushed toward the drop for `safeEdgeHoldS`. Test x and z axes separately so the player can slide along the edge.
8. **Vertical.** `y += vy·dt`.
   - Let `g = groundAt(x, z, prevFeet + stepUp, supportExpand)`.
   - If `vy ≤ 0` and `y ≤ g.y`: land. Set `y = g.y` and `vy = 0`, record the support collider, set `groundRef = g.y`, and emit `PLAYER_LAND {fallHeight = peakY − g.y, heavy = fallHeight > 3}`.
   - If grounded last step and `g.y ∈ [y − snapDown, y]`: snap down.
   - If grounded and `g.y ∈ (y, y + stepUp]`: step up.
9. **Ceiling.** If `vy > 0` and a solid collider covering `(x, z)` (inset 0.1) has its bottom between the previous head and the new head:
   - when the overlap is within `ceilingCornerNudge` of that collider's edge, nudge the player horizontally out of it;
   - otherwise set `y = bottom − height` and `vy = 0`.
10. **Ledge magnet.** Applies when airborne, `vy < 2`, a walkable top T satisfies `T − maxBelow ≤ feet < T`, the horizontal distance to its footprint is ≤ `maxDist`, and the velocity or input points toward it (dot > 0).
    - Hoist over `hoistS` to the closest footprint point inset by 0.3, at height T. Input is locked during the hoist.
11. **Landing assist.** Applies when airborne, descending, and `landingAssist ≠ 'off'`.
    - Predict the no-input landing point P (§7.3).
    - If P is over void and a walkable top within `coneRadius` of P exists at a height ≥ P.y − 0.5, apply a lateral acceleration toward its nearest footprint point, capped at the assist value (m/s of lateral velocity, total for the jump).
    - Skip it if `dot(inputDir, correction) < cancelDot`.
12. **Volumes and limits.**
    - Deep water: fall reason `'water'`.
    - Shallow water: speed flag.
    - `y < killY`: reason `'void'`.
    - x/z beyond bounds: clamp; this is *not* a fall.
13. **Safe-ground sampling.** Every `sampleS`, when grounded for ≥ `minGroundedS` on a non-mover collider with edge distance ≥ 0.6, push `{pos, collider}` into a ring of 8.
14. **Jump-pad launch** is called by P4 (`launch`). Use the formula from `padArc`: `vy0`, horizontal velocity `= (target − start)_h / T`. Emit `PLAYER_JUMP {kind:'pad'}` and lock input for `lockMs`.

**Auto-walk:** steer at `walkSpeed` toward the target and ignore input. Stop when within `autoWalkStop` or after `autoWalkMaxMs`. Resolve `true` if reached, otherwise `false`. Then face `faceYawDeg`.

**Visuals in `update`:**
- Turn the visual facing toward the velocity at 900°/s.
- Call `character.setPose(...)` with idle, walk, run, jump, fall, glide or work.
- Squash on jump and land.
- Emit `PLAYER_STEP` every 0.32 s while running grounded (0.45 s while walking).
- Emit a `runDust` puff when speed > 3.
- Update the blob shadow: `engine.fx.blobs` handle, using `groundAt(renderPos, renderPos.y + 0.1, 0)`.
- Landing marker (§7.3) when `assists.landingMarker`.

### 7.3 `player/prediction.js`

```js
export function predictLanding(world, pos, vel, opts /* {gravityUp, gravityDown, stepS, horizonS, killY} */, out) // -> out:{x,y,z, mode:'ground'|'void', t}
export function findLedge(world, pos, vel, inputDir, out) // -> boolean
export function landingCorrection(world, predicted, pos, vel, maxLateral, out) // -> {ax, az} (acceleration)
```

`predictLanding`:
- Sample every 0.05 s up to 1.5 s.
- The first sample whose `y ≤ groundAt(sample, prevSampleY, 0).y` gives mode `'ground'`.
- Otherwise the mode is `'void'`, placed at the last sample's x/z with `y = groundRef`.
- The marker is drawn with `engine.fx.landing.set(x, y + 0.02, z, mode)`: a cyan ring for ground, a blinking orange ring for void. Call `set(null)` when grounded.

### 7.4 Fall and respawn sequence

1. Emit `PLAYER_FALL {reason, x, y, z, lastSafe}`. Disable input and freeze the simulation. P5 fades to light blue over 250 ms and P5 Audio plays a splash.
2. After `fallFadeMs` (real-time timer):
   - Pick the respawn point: ring entry at index `len − 1 − lookbackSamples`, preferring entries with edge distance ≥ `respawnEdgeMargin`, then the newest valid one, then the checkpoint.
   - Move the point toward its collider centre until edge distance ≥ `min(1.0, halfWidth − 0.1)`.
   - Teleport there with zero velocity and the yaw of that sample.
   - Call `cameraRig.snapBehind()` via the event.
   - Emit `PLAYER_RESPAWN`.
   - Grant invulnerability for 1 s. Increment `stats.falls`.
3. P5 fades out over 300 ms.

There is no score or satisfaction penalty for a fall.

---

## 8. Camera (P3, `camera/CameraRig.js`)

```js
export class CameraRig {
  constructor({ engine, world, bus, settings /* {reducedMotion, cameraDistance, invertY, shake} */ })
  setTarget(player) : void
  setZones(zones /* level.cameraZones */) : void
  snapBehind() : void              // instant: ψ = player.yaw + π, default pitch/distance, no blend
  get yaw() : number               // current camera ψ
  get moveYaw() : number           // stable movement reference yaw (§8 rule 6)
  applySettings(settings) : void
  update(dt, input) : void         // called once per rendered frame, after player.update
  dispose() : void
}
```

**Rules:**

1. **Target point.**
   - Horizontal: the player's `renderPosition` plus a look-ahead of `lookAhead · min(1, |vh|/6)` along the velocity, smoothed with a 0.4 s time constant. No look-ahead with reduced motion.
   - Vertical: `refY + targetHeight`. `refY = player.groundRef`, except that while airborne it only follows when `feet > refY + 2.5` (then `refY = feet − 2.5`) or `feet < refY − 1.0` (then `refY = feet + 1.0`).
   - Smoothing: `x += (t − x)·(1 − 2^(−dt/halfLife))`, with `halfLifeH` horizontally and `halfLifeV` vertically.
2. **Follow mode.**
   - Default pitch 25° and distance `TUNING.camera.distance[settings.cameraDistance]`.
   - FOV is 60° if `matchMedia('(pointer: coarse)')`, otherwise 50°. FOV never changes during play.
3. **Auto-recentre.**
   - After `recenterDelayS` without manual camera input (`recenterAfterManualS` after a manual orbit), and when `dot(moveDir, camForward) > 0.3`: rotate ψ toward `player.yaw + π` at ≤ 45°/s with ease-out.
   - Never recentre while `dot < −0.2` (walking toward the camera).
4. **Manual orbit.** Use `input.camYawDelta` and `input.camPitchDelta` (degrees, already scaled per device). Clamp pitch between 10° and 55°. `zoomStep` cycles proche/normal/loin. `recenterPressed` triggers an eased snap behind the player over 0.4 s.
5. **Zones.**
   - Inside a zone (feet point in its AABB), blend over `blendS` (1.2 s with reduced motion, smoothstep) toward ψ = `zone.yaw·π/180 + π`, pitch = `zone.pitch`, distance = `zone.distance`.
   - Manual orbit is limited to ±`orbitLimitDeg` around the zone yaw.
   - `targetLock` fixes target x and/or z to the given values.
   - Emit `CAMERA_ZONE` on change. Leaving a zone returns to follow mode, keeping the current ψ.
6. **Stable movement frame.** `moveYaw` keeps its previous value during any automatic yaw change caused by a zone blend. It switches to the current ψ once the stick magnitude stays below 0.2, or after `moveFrameHoldS` (0.6 s). It follows ψ immediately during manual orbit and recentre.
7. **Speed cap.** Automatic yaw change is capped at 90°/s overall.
8. **Occlusion.**
   - Compute `t = world.segmentBlocked(target → desiredCamPos)`.
   - The desired distance becomes `max(occlusionMin, t·d − 0.3)`.
   - Pull in with half-life 0.05 s, push out with half-life 0.4 s.
   - Level design is responsible for avoiding occluders; there is no transparency.
9. **Shake.** On `EV.FX_SHAKE {amp, ms}`, apply only when `settings.shake && !settings.reducedMotion`. Amplitude is capped at 0.08. Use a random offset with linear decay.
10. **Never:** roll, head bob, motion blur, or camera rotation caused by a carrying platform.
11. **Respawn.** On `PLAYER_RESPAWN`, call `snapBehind()` unless a zone is active, in which case snap to the zone values.

---

## 9. Input (P3)

```js
export class InputManager {
  constructor({ element /* #a3d-stage */, touchLayer /* #a3d-touch */, bus, settings /* {leftHanded, vibration, invertY} */ })
  poll() : InputState            // call once per frame (beginFrame); returns the same mutable object every frame
  consumeEdges() : void          // clears every *Pressed / ui* edge on the snapshot and in the latch
  injectAct() : void             // latches actPressed (world-bubble click/tap, owned by P5)
  get device() : 'kbm'|'pad'|'touch'
  setActionHint(hint /* {icon:IconKey, label:string} | null */) : void   // touch AGIR button
  setTouchVisible(visible) : void
  setEnabled(enabled) : void     // false: gameplay fields read 0/false; ui* edges still work
  applySettings(settings) : void
  vibrate(ms, strength = 0.5) : void   // navigator.vibrate on touch; gamepad vibrationActuator 'dual-rumble'; respects settings.vibration
  dispose() : void
}
/* InputState = {
  moveX, moveY,             // [-1,1], radial magnitude ≤ 1 (keyboard diagonals normalised)
  walk,                     // boolean
  jumpPressed, jumpHeld, actPressed, actHeld,
  camYawDelta, camPitchDelta, // degrees accumulated since the previous poll (positive yaw = orbit right)
  zoomStep,                 // -1|0|1
  recenterPressed, pausePressed, objectivesPressed,
  uiUp, uiDown, uiLeft, uiRight, uiConfirm, uiBack,   // edges for menus/modals
  digit,                    // 0 or 1..4 (edge)
  device }                  */
```

**Latching rule.** Edges are latched when the event happens and remain true in every `poll()` until `consumeEdges()`. GameSession calls `consumeEdges()` after the **first fixed step** of a frame that runs at least one step, or at the end of `update()` when paused.

**Keyboard** (`KeyboardEvent.code`, so AZERTY and QWERTY behave identically):

| Action | Codes |
|---|---|
| Move | `KeyW` `KeyA` `KeyS` `KeyD`, arrows |
| Jump | `Space` |
| Act | `KeyE`, `Enter`, `NumpadEnter` |
| Walk | `ShiftLeft`, `ShiftRight` |
| Recentre | `KeyC` |
| Objectives | `Tab` (preventDefault) |
| Pause | `Escape`, `KeyP` |
| Digits | `Digit1`–`Digit4`, `Numpad1`–`Numpad4` |
| UI | Arrows = ui*; `Enter`/`Space` = uiConfirm; `Escape`/`Backspace` = uiBack |

**Mouse:**
- Right-button drag orbits: 0.2°/px yaw; pitch respects `invertY`.
- The context menu is prevented on the stage.
- Wheel: `zoomStep`.
- Middle click: recentre.
- No pointer lock.

**Gamepad** (`standard` mapping, polled inside `poll()`):

| Control | Mapping |
|---|---|
| Left stick | Move, radial deadzone 0.18 then rescaled |
| Right stick | Camera, deadzone 0.20, 140°/s × frame dt |
| `b0` (A) | Jump (`jumpHeld`) and uiConfirm |
| `b2` (X), `b1` (B) | Act; `b1` is also uiBack |
| `b4`, `b5` | Recentre |
| `b9` | Pause |
| `b12` | Objectives |
| `b12`–`b15` | uiUp, uiDown, uiLeft, uiRight |

**Touch** (`input/touch.js`, Pointer Events with `pointerType 'touch'`, `setPointerCapture`):

- **Floating joystick.**
  - A pointer down in the left 45 % × bottom 70 % of the stage (mirrored for left-handed) places the base there.
  - Base radius 64 px, knob radius 28 px, travel 56 px, deadzone 10 %. Magnitude = travel/56.
  - A ghost joystick (opacity 0.35) is shown at left 120 px, bottom 110 px until the first move.
- **SAUTER** button ⌀96, centre at (right 84, bottom 84). **AGIR** button ⌀80, centre at (right 210, bottom 72). Both are mirrored when left-handed.
- Safe-area insets are read from the CSS variables `--a3d-safe-left/right/bottom` (P5 CSS).
- Drag elsewhere in the right half: camera, 0.25°/px. Double tap within 300 ms: recentre.
- **DOM created by P3 inside `#a3d-touch`** (P5 styles these exact classes):

```html
<div class="a3d-stick is-ghost"><div class="a3d-stick-base"></div><div class="a3d-stick-knob"></div></div>
<button class="a3d-tbtn a3d-tbtn-jump" aria-label="Sauter"><svg class="a3d-tbtn-icon">…goutte + flèche…</svg><span class="a3d-tbtn-label">SAUTER</span></button>
<button class="a3d-tbtn a3d-tbtn-act is-disabled" aria-label="Agir"><i class="a3d-tbtn-fa fas fa-hand"></i><span class="a3d-tbtn-label">AGIR</span></button>
```

- P3 positions elements only with `style.transform` / `left` / `top`, and toggles only the classes `is-ghost`, `is-active`, `is-disabled`, `is-ready`, `is-left-handed`.
- **Act icon map** (FontAwesome): wrench → `fa-wrench`, coins → `fa-coins`, faucet_off / droplet → `fa-faucet-drip`, valve → `fa-gear`, speech → `fa-comment`, box → `fa-box`, receipt → `fa-receipt`, lock → `fa-lock`.
- **Device switching:** the last input source wins and emits `INPUT_DEVICE`. Touch controls are visible when `device === 'touch'` or, at boot, when the pointer is coarse.

---

## 10. Assist effects

| Assist | Owner | Effect |
|---|---|---|
| `guidePath` | P4 | Sparkle trail toward the current objective target: straight segments sampled every 1.5 m up to 20 m, at `groundRef + 0.3`, via `engine.fx.guide` |
| `objectiveArrow` | P5 | HUD compass arrow (target bearing relative to camera ψ) plus target distance |
| `landingAssist` | P3 | §7.2 step 11 (1.2 / 0.5 / 0 m/s) |
| `landingMarker` | P3 | Landing ring |
| `safeEdges` | P3 | §7.2 step 7 |
| `infiniteGlide` | P3 | No glide duration cap |
| `relaxedTimers` | P4 | `deadlineS` and `overdueAtS` × 1.5 |
| `pauseTimersOnFall` | P4 | Mission clock paused from `PLAYER_FALL` to `PLAYER_RESPAWN` + 300 ms |
| `offerHelpBridge` | P4 / P5 | Help-bridge offer |

The always-on helpers apply to every profile:
- coyote and buffer windows;
- ledge magnet;
- blob shadow;
- generous radii;
- action not cancelled by a brief flick.

---

## 11. Gameplay systems (P4)

### 11.1 APIs

```js
export class LevelBuilder {
  constructor({ engine, world /* CollisionWorld (new per level) */, bus, assists, player })
  async build(level /* LevelData */, onProgress /* (0..1) => void */) : Promise<LevelRuntime>
}
export class LevelRuntime {
  level; mission /* Mission */;
  preFixedUpdate(dt) : void                        // movers (setCenter + view targets), block animations
  postFixedUpdate(dt, player, input) : void        // triggers, gouttes, checkpoints, pads, goal, interactions, act, mission clock
  update(dt, alpha, player, cameraYaw) : void      // interpolate mover views, entity view updates, icons, guide trail
  setPaused(paused) : void
  getInteraction() : InteractionHint | null
  getObjectiveTarget() : {x,y,z} | null
  getLabelAnchors() : Array<{id, text, x, y, z}>   // y = top of head/prop + 0.4 (positions refreshed each call)
  getRunSummary() : RunSummary
  dispose() : void                                 // dispose views, StaticWorld, event listeners
}
```

**`LevelBuilder.build` order:**
1. `world.setBounds` and `world.setKillY`.
2. Statics → `world.add*` + `staticWorld.addPlatform(entity)`.
3. Waters → `world.addVolume` + `staticWorld.addWater`.
4. Decor → `staticWorld.addDecor` + optional collider.
5. `world.build()`.
6. `await staticWorld.build(p => onProgress(p*0.7))`.
7. Dynamic entities via the `create*View` factories, plus colliders: ouvrage defaults, movers, blocks.
8. Collectible field.
9. Icons and rings.
10. Set the player spawn.
11. Engine environment (`theme`).
12. Emit `LEVEL_READY`.

### 11.2 Default colliders and work spots

| Entity | Default collider |
|---|---|
| ouvrage `bf` | cylinder r 0.45, h 1.2 |
| ouvrage `pompe` | cylinder r 0.6, h 1.4 |
| ouvrage `kiosque` | box 3 × 2.6 × 3, centred on `pos` |
| ouvrage `station` | box 4 × 3 × 4 |
| ouvrage `chateau` | explicit `colliders` |
| usager / npc | cylinder r 0.35, h 1.1 |
| valve | cylinder r 0.3, h 1.0 |

- **Work spot:** `pos + facing(yaw) · (footprintHalfExtent + workSpotOffset)`.
- **In range:** horizontal distance from the player to the entity footprint ≤ `interact.radius` (1.6) and `|player.y − pos.y| ≤ 1.5`.

### 11.3 Interaction selection

This is the `getNearbyInteraction` priority. Among entities in range, the lowest class number wins; ties go to the nearest.

| Class | Candidate | `kind` | Label | Icon |
|---|---|---|---|---|
| 1 | broken ouvrage, item present | `repair` | « Réparer » | `wrench` |
| 2 | usager `restore_pending` with `restoreBy:'action'` | `restore` | « Remettre l'eau » | `droplet` |
| 3 | usager `cut_off` > `overdue` > `due` | `collect` | « Encaisser 3 000 Ar » | `coins` |
| 4 | closed valve | `valve` | `label` or « Ouvrir la vanne » | `valve` |
| 5 | npc with a non-`always` step available | `talk` | « Parler » (caissière with receipts: « Remettre les reçus ») | `speech` |
| 6 | npc default step | `talk` | « Parler » | `speech` |
| 7 | broken ouvrage without its item | `blocked` | « Il faut la caisse de matériel » (`enabled:false`) | `lock` |

- An usager in `restore_pending` with `restoreBy:'valve'` gives no interaction; its icon shows `valve`.
- Emit `INTERACTION_CHANGED` only when `targetId`, `kind` or `enabled` changes. `anchor` is the entity top + 0.6.

### 11.4 Act flow (`Interactions.act()`)

Triggered by `input.actPressed` when not paused and no action is running.

1. **`blocked`:** emit `FEED` with « Il vous faut la caisse de matériel (magasin). », tone `warn`. Stop.
2. **`talk`:** pick the NPC step. Emit `NPC_TALK` and pause (P5 opens the dialogue). On `DIALOGUE_CLOSED`:
   - if the step has `quizSlot`, run the quiz (step 3);
   - apply the effects;
   - emit `NPC_STEP`;
   - mark `once` steps as consumed.
3. **Quiz gate** (ouvrage, usager, valve or NPC with a `quizSlot` not yet asked this run): emit `QUIZ_REQUEST {slot, title: quizSlots[slot].intro}` and wait for `QUIZ_DONE` with the same slot. Score: `TUNING.score.quiz[min(attempts.length − 1, 2)]` when solved, 0 when skipped.
4. `await player.autoWalkTo(workSpot, yaw + 180)`. Then `player.setActionLock(true)` and emit `ACTION_START {durationMs}`. The ouvrage becomes `repairing` (`OUVRAGE_STATE`).
5. **Progress:** emit `ACTION_PROGRESS` at ≤ 30 Hz and call `view.setProgress(t)`.
   - **Cancel** if `|stick| > cancelStick` continuously for `cancelHoldS`: emit `ACTION_CANCEL`, revert `repairing` to `broken`, release the lock.
   - The mission clock keeps running during actions (except in L0/L1, which have no timers).
6. **Completion** (release the lock, emit `ACTION_DONE`):
   - **Repair:** state `healthy`. `OUVRAGE_REPAIRED {onTime: deadline == null || elapsed ≤ deadline}` and `OUVRAGE_RESOLVED {how:'repaired'}`. Score +22, satisfaction +7. Particles `confetti` + `jet`. `FX_SHAKE` is not used. Feed « {name} réparé. ».
   - **Collect:**
     - `due`: becomes `paid`, +14 / +3, `onTime = true`.
     - `overdue`: becomes `paid`, +6 / +2.
     - `cut_off`: becomes `restore_pending`, +0, feed « Paiement reçu chez {name}, remise en eau requise. ».
     - Emit `USAGER_PAID`.
     - If `hud.receipts`: `ITEM_RECEIVED {kind:'recu'}`.
     - Particles `coins`. Toast `+{amount} Ar`.
   - **Restore:** becomes `paid`, +10 / +5. `USAGER_RESTORED`. Particles `jet`.
   - **Valve:** `view.setOpen()`, apply the effects, `VALVE_OPENED`.
7. **Effect ops:**
   - `give` / `take`: inventory, then `INVENTORY_CHANGED`. `give caisse_materiel` also calls `player.character.setCarry('caisse')`.
   - `setSolid`: block animation and collider.
   - `setLevel`: `ouvrageView.setLevel(v)`.
   - `restore`: usager `restore_pending` → `paid` with the restore rewards and `USAGER_RESTORED`.
   - `feed`: emit `FEED`.

### 11.5 Mission clock and soft timers

- `elapsedS` advances in `postFixedUpdate` only when not paused and not in a fall pause (§10).
- **Scheduled failure:** a healthy ouvrage with `failAtS ≤ elapsed` that has not failed yet:
  - becomes `broken`, deadline = `elapsed + deadlineS·k` (k = 1.5 with relaxedTimers);
  - satisfaction −3; `OUVRAGE_BROKEN`; feed « Panne détectée sur {name}. » (warn).
- **Missed deadline:**
  - state `healthy` (« l'équipe de secours »), score −18, satisfaction −12;
  - `OUVRAGE_MISSED` + `OUVRAGE_RESOLVED {how:'missed'}`; `events.missed_breakdowns++`;
  - feed « Panne non traitée à temps sur {name} : l'équipe de secours est intervenue. ».
  - If the player is mid-action on it, cancel the action.
- **Soft overdue:** a `due` usager with `overdueAtS·k ≤ elapsed` becomes `overdue`, satisfaction −5, feed « {name} devient impayé. ». There is never an automatic cut-off.
- **Satisfaction** is clamped 0–100. It only matters when `hud.satisfaction`, and it is **never** a failure condition.
- Emit `MISSION_TICK` every second.

### 11.6 Collectibles, checkpoints, pads, goal, triggers, hints, help bridges

- **Gouttes:** `view.hide(i)`, score +5, particles `sparkle`, `GOUTTE_COLLECTED`.
- **Checkpoints:** call `player.setCheckpoint(pos, yaw)`, `view.activate()`, emit `CHECKPOINT_REACHED`. Push a segment `{cp, t_ms, falls (since the previous checkpoint), help_bridge}`.
- **Pads:** call `view.fire()` and `player.launch(...)`. Re-arm after 0.5 s.
- **Hints:**
  - At most one visible at a time; queue the rest.
  - A hint is *eligible* when its trigger zone contains the player (or it has no trigger), its `showOn` matcher has fired, it is not done, and its shows are under `maxShows` (counted in storage `hintsSeen`).
  - It is shown after `idleMs` of idle (no move input above 0.12 and no action).
  - It is hidden when its `doneWhen` matches, when the player leaves the trigger zone, or after `durationMs`.
- **Help bridges:** §5 semantics. On `HELP_ACCEPTED`, pause is released by P5, the block is created and `summary.helpBridges++`.

### 11.7 Stars (client side; the server recomputes)

| Star | Condition |
|---|---|
| ★1 | `completed` |
| ★2 | `gouttes === gouttes.length` |
| ★3 `quiz_first_try` | `quizFirstTry === quizCount` and `quizCount > 0`. Skipped slots count as not first-try; if every slot was skipped, ★3 is false. |
| ★3 `tournee_a_l_heure` | `events.on_time_payments ≥ 2 && events.restores ≥ 1` |
| ★3 `service_exemplaire` | `events.missed_breakdowns === 0 && events.repairs ≥ 3` |

- `on_time_payments` counts `USAGER_PAID` events with `stateBefore === 'due'` for usagers that have `overdueAtS`.
- On `LEVEL_COMPLETE`, add score +50 and freeze the clock. The summary then contains `durationMs = elapsedS·1000` (rounded).

---

## 12. Rendering (P2)

### 12.1 Engine API

```js
export class Engine {
  constructor({ canvas, container /* #a3d-stage */, bus, tier /* 'low'|'medium'|'high' */, settings, debug = false })
  scene: THREE.Scene; camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer
  tier: string; quality: object /* QUALITY_PRESETS[tier] */
  fx: { particles: Particles, icons: IconLayer, blobs: BlobShadows, landing: LandingMarker, guide: GuideTrail }
  async init() : Promise<void>      // renderer, lights, sky, fx; high tier: dynamic import('a3d/render/post.js')
  setLoop({ beginFrame(dt), fixedUpdate(dt), update(dt, alpha) }) : void
  start() : void; stop() : void
  setPaused(paused) : void          // fixedUpdate skipped; update(dt, 1) still runs; render ≤ 10 fps
  setEnvironment({ sky, fogNear, fogFar }) : void
  setFocus(vec3) : void             // shadow camera follow target (player renderPosition)
  async compile() : Promise<void>   // renderer.compileAsync(scene, camera)
  async setTier(tier, reason) : Promise<void>  // 200 ms fade to white (#a3d-fade via the 'engine:tier' event; P5 animates), rebuild materials, compile
  project(pos /* {x,y,z} */, out /* {x,y,visible} */) : object  // CSS px relative to the container; visible = in front and inside the viewport
  getStats() : { fps, drawCalls, triangles, tier, pixelRatio }
  dispose() : void                  // renderer.dispose(); forceContextLoss()
}
```

**Loop:**
- rAF timing with `dt = min((now − last)/1000, 0.1)`.
- **Render throttle** (low tier target 30 fps): skip the whole frame when `now − lastRendered < 1000/targetFps − 3` ms. This is time based, so it is correct on 90/120 Hz screens.
- **Per frame:** `beginFrame(dt)`; then `acc += dt`, and while `acc ≥ 1/60` and steps < 5, `fixedUpdate(1/60)` (excess accumulator is dropped); then `update(dt, acc·60)`; governor sample; render (composer on high).
- `webglcontextlost`: `preventDefault`, emit `ENGINE_CONTEXT_LOST`, stop.
- `webglcontextrestored`: `compile()`, emit `ENGINE_CONTEXT_RESTORED`, start.
- A `ResizeObserver` on the container sets size and pixel ratio: `clamp(devicePixelRatio·governorScale, min, max)`.

### 12.2 `engine/quality.js` (TF)

```js
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
export function hasWebGL2() : boolean
export function detectTier() : { tier, reason, renderer: string }
export class FpsGovernor {
  constructor({ preset, onScale /* (pixelRatio) => void */, onTierDown /* () => void */ })
  sample(frameIntervalMs) : void; reset() : void; pause(paused) : void
}
```

**`detectTier()`:**
- Uses a throwaway `webgl2` context, `WEBGL_debug_renderer_info` when available, `navigator.deviceMemory`, `hardwareConcurrency` and `matchMedia('(pointer: coarse)')`. It then calls `loseContext()`.
- **low** if the renderer matches `/SwiftShader|llvmpipe|Mali-(T\d|G(31|51|52|57))|Mali-4|Adreno \(TM\) ([1-5]\d\d|6[01]\d)|PowerVR/i`, **or** (coarse and (`deviceMemory ?? 4) ≤ 3` or `(hardwareConcurrency ?? 4) ≤ 4`)).
- **high** if not coarse **and** the renderer matches `/NVIDIA|GeForce|Radeon|AMD|Apple M|Iris\(R\) Xe|Arc/i` **and** `deviceMemory` is undefined or ≥ 8.
- **Otherwise medium** (including when the renderer string is masked).
- A user override from storage `quality` ≠ `'auto'` wins.
- Software rendering sets `reason: 'software'`; P5 shows « Rendu logiciel détecté : le jeu sera lent. ».

**Governor:**
- Windows of 2 s; median frame interval per window. The first 4 s after start, after a tier change and after unpause are ignored. Paused while `document.hidden`.
- `budget = 1000/targetFps`.
  - **Slow:** median > budget × 1.25. Two consecutive slow windows → pixel ratio × 0.85 (down to `pixelRatioMin`). At the floor, two more slow windows → `onTierDown()` (high → medium → low). GameSession applies it via `engine.setTier`.
  - **Fast:** median < budget × 0.7 for 5 consecutive windows → pixel ratio × 1.1 (≤ max).
  - The tier is **never** raised automatically.

### 12.3 Pipeline

**Colour pipeline:**
- `renderer.outputColorSpace = SRGBColorSpace`, `toneMapping = NeutralToneMapping`, exposure 1.0, `alpha: false`, `stencil: false`.
- Antialias only on the high tier without composer. On high **with** bloom, use `composer.renderTarget` `samples: 4` and let `OutputPass` apply tone mapping.
- **Every custom `ShaderMaterial` ends with `#include <tonemapping_fragment>` and `#include <colorspace_fragment>`.**
- **State colours** (icons, rings, lamps) use materials with `toneMapped: false`.

**Lights:**
- `HemisphereLight(#CFE8FF, #B8784E, 1.3)`.
- `DirectionalLight(#FFF1D6, 3.0)` at elevation 50° and azimuth 135°, fixed.
- On medium/high the shadow camera follows `setFocus` with texel snapping: ortho, near 1, far 80, bias −0.0005, normalBias 0.02.
- Shadow casters: player, characters, ouvrage views, movers, static chunk meshes. Receivers: chunks and platforms.

**Materials** (`MaterialFactory.get(key)`, cached shared instances):

| Key | Definition | Used by |
|---|---|---|
| `worldSoft` | `MeshToonMaterial({vertexColors:true})`; 8-px ramp `[70,95,130,170,205,230,245,255]` with `LinearFilter`; rim `pow(1−N·V, 3)·0.35` in `#FFF6E0` via `onBeforeCompile`; `customProgramCacheKey 'soft-rim'` | static geometry, props |
| `worldSoftNoFog` | same with `fog: false` | the château only |
| `hero` | high: `MeshStandardMaterial` roughness 0.45 + `RoomEnvironment` PMREM at intensity 0.4; others: toon with rim 0.5 | player, collectibles (emissive cyan 1.6) |
| `water` | §12.4 | water |
| `sky` | dome shader | sky |
| `particlesAdd`, `particlesAlpha` | particle pools | particles |
| `icon` | instanced billboards | icons |
| `blob` | radial gradient `CanvasTexture` 64², `depthWrite false`, `polygonOffset −1` | blob shadows |
| `ring` | additive, `toneMapped false` | rings |
| `outline` | inverted hull, high tier only, interactives only | outlines |

- Vertex colours are **Float32 linear** (avoids dark-tone banding).
- Baked AO is applied in vertex colours: × 0.72 on the bottom 0.3 m of walls and under eaves.

**Sky:**
- Sphere r 400, `BackSide`, gradient: zenith `#3A9BEF`, horizon `#CFEFFF`, below the horizon `#F3E3C3`.
- Sun disk + halo. `gl_Position.z = gl_Position.w`, `renderOrder 1000`, `depthWrite false`.
- `sky: 'midi'` shifts the zenith to `#2F8FE8`.
- Clouds: 0, 8 or 16 instanced merged icospheres at y 60–90, drifting 0.6 m/s.
- `Fog(#CFEFFF, near, far)` uses the theme value or the tier default. `camera.far = fogFar + 10` (minimum 120).

**Static world:**
- Chunks of 16 m. Per chunk: one merged `worldSoft` mesh, one water mesh, and `InstancedMesh` per foliage kind.
- Every static geometry passes through `prepStatic`: non-indexed, attributes exactly `position`, `normal`, `color` (Float32), with no `uv`.
- `mergeGeometries` is called per chunk. Grass and stone are auto-scattered on `grass`-style tops with a seeded PRNG (`mulberry32(hash(level.id))`), at the tier's density.
- The build is time-sliced: ≤ 8 ms per slice, yielding with `await new Promise(r => setTimeout(r))`.

**Budgets:**

| Tier | Draw calls | Triangles | Programs | GPU memory |
|---|---|---|---|---|
| low | ≤ 60 | ≤ 80k | ≤ 10 | ≤ 40 MB |
| medium | ≤ 110 | ≤ 200k | — | ≤ 70 MB |
| high | ≤ 180 | ≤ 450k | — | ≤ 150 MB |

The `?debug=1` overlay shows `renderer.info`.

### 12.4 Water, particles, icons, markers

**Water:** opaque `ShaderMaterial`.
- Vertex attribute `aShore`: 0 at the bank, 1 at ≥ 2 m inside the rect, computed from the distance to the rect edges.
- Colour = mix(`#5FD3F0`, `#1F8FD6`, `smoothstep(0, 0.7, aShore)`).
- Two scrolled samples of a 128² seeded noise `CanvasTexture` (`NoColorSpace`); the flow comes from `flow`.
- Foam band `#F4FCFF` at the shore. Fake sun glint. Fresnel toward the horizon colour.
- Low tier: one sample and no glint.

**Particles** (`fx/particles.js`):

```js
export class Particles { constructor(engine, capacity)
  emit(preset, pos, opts = {}) : void       // presets: 'sparkle','dust','runDust','splash','confetti','steam','coins','jet','glideMist'
  addContinuous(preset, anchor /* Object3D */, opts = {}) : { stop() }   // e.g. a broken BF leak jet, PMH steam
  update(dt) : void }
```

- Two `Points` pools (additive and alpha). CPU ring buffer. Upload with `attribute.addUpdateRange` + `needsUpdate`.

**Icons** (`fx/IconLayer.js`):

```js
export class IconLayer { constructor(engine)
  async init() : Promise<void>              // atlas: waits for document.fonts.load('900 48px "Font Awesome 6 Free"') ≤ 1.5 s, else canvas paths
  add(anchor /* Object3D */, offsetY, icon /* IconKey */, tint /* hex */) : { set(icon, tint), setVisible(b), remove() }
  addRing(anchor, radius, tint) : { set(tint), setVisible(b), remove() }
  update(time) : void }                     // one InstancedMesh for icons, one for rings; bob + pulse in the shader
```

**Markers** (`fx/markers.js`):

```js
export class BlobShadows { add() : { set(x, groundY, z, heightAbove), setVisible(b), remove() } }   // opacity 0.35*(1-h/4), radius 0.45→0.30
export class LandingMarker { set(x, y, z, mode /* 'ground'|'void' */) ; set(null) }
export class GuideTrail { setPath(points /* [[x,y,z],...] */ | null) ; update(dt) }
```

### 12.5 Props and characters (`render/props/index.js`, `actors/characters.js`)

```js
export class StaticWorld { constructor(engine, seedString)
  addPlatform(entity /* box|cyl|ramp with style */) : void
  addDecor(entity) : void
  addWater(def) : void
  async build(onProgress) : Promise<void>
  dispose() : void }
// Every view: { object3d: THREE.Object3D, update(dt, time): void, dispose(): void } plus:
export function createOuvrageView(def)   // + setState(state), setProgress(t|null), setLevel(t) (chateau), pop()
export function createUsagerView(def)    // + setState(state), setProgress(t|null), cheer(), character  (+ water-meter post with a state lamp)
export function createNpcView(def)       // + setTalking(b), character
export function createMoverView(def)     // object3d positioned by P4
export function createBlockView(def)     // + setT(t)  (0 = at offsetHidden, 1 = final), setVisible(b)
export function createJumpPadView(def)   // + fire()
export function createCheckpointView(def)// + activate()
export function createGoalView(def)      // + setActive(b), celebrate()
export function createValveView(def)     // + setProgress(t|null), setOpen()
export function createCollectibleField(positions) // + hide(i), count
export function createCharacter(kind /* 'technicien'|'usager'|'npc' */, opts /* {variant, toolbox, hat, tier} */) : CharacterView
// CharacterView: { object3d, setPose(state, speed01), squash(kind /* 'jump'|'land'|'pop' */, strength), setCarry(kind|null), update(dt), setVisible(b), dispose() }
// states: 'idle','walk','run','jump','fall','glide','work','cheer','wave','talk','sad'
```

**Box styles:** `grass` (green top, laterite sides), `laterite`, `rock`, `concrete`, `wood` (planks; the market-stall look when height ≤ 1.2), `brick`, `metal` (scaffold), `pipe` (blue PVC walkway), `house_tin` (brick walls, door, windows, blue tin roof cap, optional sign), `kiosque` (concrete, blue band, counter window, sign), `invisible`.

**Decor kinds:** `ravinala`, `baobab`, `tree`, `bush`, `rock`, `flowers`, `fence` (points), `path` (points, width), `pipe` (points, radius), `rice_patch` (pos, size), `cart`, `crate`, `barrel`, `sign` (text).

**Characters** are built from rigid parts parented to pivot `Object3D`s, with no `SkinnedMesh`.
- Chibi technicien: 1.1 m tall; cap, overalls `#1E6FD9`, yellow `#FFC53D` shirt and straps, orange gloves, red toolbox, Hydro-pack backpack.
- Low LOD ≈ 900 triangles, high ≈ 2.6k.

**Colours:** state colours in `STATE_COLORS` (§0); the palette tokens follow the visual proposal (`HYDRIA_BLUE #1E6FD9`, `HYDRIA_CYAN #22D3EE`, `LATERITE #C2502A`, `GRASS #7DBB4A`, etc.). Blue is reserved for water and Hydria items.

**Ouvrage state visuals:**
- `broken`: sparks or steam, leak jet (bf), drooping handle (pompe), red lamp, `wrench` icon.
- `repairing`: yellow lamp, `hourglass` icon.
- `healthy`: cyan halo, then the icon hides after 2 s.

---

## 13. UI (P5)

### 13.1 DOM skeleton

The template (P1) renders exactly:

```html
<div id="a3d-app" class="a3d-app" data-version="{{ a3d_version }}">
  <div id="a3d-stage" class="a3d-stage">
    <canvas id="a3d-canvas" class="a3d-canvas" aria-label="Hydria Quest 3D"></canvas>
    <div id="a3d-labels" class="a3d-layer a3d-labels" aria-hidden="true"></div>
    <div id="a3d-hud" class="a3d-layer a3d-hud" hidden></div>
    <div id="a3d-touch" class="a3d-layer a3d-touch" hidden></div>
    <div id="a3d-screens" class="a3d-layer a3d-screens"></div>
    <div id="a3d-fade" class="a3d-fade" aria-hidden="true"></div>
    <div id="a3d-rotate" class="a3d-rotate" hidden><i class="fas fa-rotate"></i><p>Tournez votre téléphone pour jouer en paysage</p></div>
  </div>
  <div id="a3d-fallback" class="a3d-fallback" hidden></div>
</div>
```

**Z-order:** canvas 0, labels 10, HUD 20, touch 30, screens 40, fade 50, rotate 60.

**Immersive mode** (`.a3d-app.is-immersive`): `position: fixed; inset: 0; z-index: 70`, with page scroll locked.
- Entered by « Plein écran » (`requestFullscreen` on `#a3d-app`, then a best-effort `screen.orientation.lock('landscape')` in try/catch).
- Entered automatically on coarse pointers at « Jouer ».
- When `requestFullscreen` is unavailable (iOS), only the class is applied.

**Embedded size** (desktop): `.a3d-stage { height: clamp(420px, calc(100vh - 9rem), 56.25vw) }`.

The stage uses `touch-action: none; overscroll-behavior: none; user-select: none; -webkit-tap-highlight-color: transparent`.

### 13.2 Screens (`ui/Screens.js`)

```js
export class Screens { constructor({ root /* #a3d-screens */, bus, bootstrap, strings })
  showStart({ onPlay, onFullscreen }) ; showOnboarding(onPick /* (profile) => void */)
  showLevelSelect({ best, unlockAll, onPick, onBack }) ; showLoading(progress01, label) ; hideAll()
  showComplete({ summary, server /* ResultResponse|null */, offline, level, onNext, onReplay, onSelect, onHome })
  showFallback(kind /* 'webgl2'|'cdn'|'error' */, links) }
```

**Start screen:**
- Title « Hydria Quest 3D »; subtitle « Une journée sur le terrain avec Koto, technicien Hydria ».
- Buttons « Jouer », « Plein écran »; link « Version 2D (simulation) ».
- Device-adapted tip: « Déplacement : ZQSD ou flèches · Sauter : Espace · Agir : E ».

**Onboarding:** « Avez-vous déjà joué à des jeux vidéo ? » with buttons « Jamais » → `debutant`, « Un peu » → `occasionnel`, « Souvent » → `joueur`. Note: « Vous pourrez changer ce réglage dans Pause › Aides. »

**Level select:**
- 4 cards: title, place, description, `durationLabel`, stars ★/☆, lock icon.
- Level n is unlocked if n = 0, or level n−1 has best ★1, or `unlock_all`.
- Header « Étoiles : {n}/12 ». Locked card text « Terminez le niveau précédent pour débloquer ».

**Loading:** « Préparation du village… » with a progress bar.

**Complete:**
- « Niveau terminé ! ». Stars animated one by one (0.4 s each, with the star SFX), « Nouvelle étoile ! » on new bits.
- Stats: « Gouttes {g}/{t} », « Temps {mm:ss} », « Chutes {f} », « Score {s} ».
- XP: « +{xp} XP » plus a level bar (`level_progress`) and earned badges.
- Card « Fiche réflexe » with the 3 rules and « Écouter » (if TTS is available).
- Saving states: « Enregistrement… », then « Progression enregistrée » or « Hors ligne : progression non enregistrée sur le serveur » or « Partie non retenue ({reason}) ».
- Buttons « Niveau suivant », « Rejouer », « Choisir un niveau », « Retour à l'Academy ».

**Fallbacks:**
- `webgl2`: « Votre navigateur ne prend pas en charge la 3D (WebGL 2). »
- `cdn`: « Le moteur 3D n'a pas pu être chargé. Vérifiez votre connexion. »
- `error`: « Une erreur est survenue. Rechargez la page. »
- Each shows the link « Jouer à la version 2D ».

### 13.3 HUD and prompts

```js
export class Hud { constructor({ root, bus, strings, level, assists, input })
  update(dt, ctx /* {cameraYaw, playerPos, targetPos} */) ; setVisible(b) ; dispose() }
export class Prompts { constructor({ root /* #a3d-hud */, bus, engine, input, glyphs }) ; update(dt) ; dispose() }
export class WorldLabels { constructor({ root /* #a3d-labels */, engine }) ; update(anchors, playerPos) }   // 4 nearest within 15 m, 30 Hz
export class Toasts { constructor({ root, engine }) ; show(text, worldPos|null, tone) }               // pooled (12 nodes)
```

**HUD layout:**

| Position | Content |
|---|---|
| Top-left | Pause button ⌀48 (`fa-pause`), then the objective chip « Objectif : {text} » (pulses on change; Tab / dpad-up expands the objectives list) |
| Top-centre | Process-track chips (current = filled); compass arrow + « {d} m » when `objectiveArrow` |
| Top-right | Gouttes « 💧 {n}/{t} », Score, Satisfaction bar (if `hud.satisfaction`), receipts « Reçus {n}/4 » (if `hud.receipts`), carried item icon, « Pannes en cours : {k} » (if `hud.missionTimer`), « Plein écran » button |
| Left, under the objective | Feed of the last 3 messages, each fading after 5 s |
| Action prompt | World bubble at the projected `hint.anchor` (icon + label; clickable/tappable, which calls `input.injectAct()`), plus a bottom line « {act} {label} » |

- A disabled hint shows a grey bubble with `reason`.
- P5 calls `input.setActionHint({icon, label} | null)` on each `INTERACTION_CHANGED`.

**Hints:** a bubble anchored on `anchorId` (if visible on screen), otherwise above the bottom line. Tokens are replaced by the glyphs of the current device:

| Token | kbm | pad | touch |
|---|---|---|---|
| `{move}` | `<kbd>ZQSD</kbd> ou les flèches` | le stick gauche | le pouce à gauche |
| `{jump}` | `<kbd>Espace</kbd>` | Ⓐ | SAUTER |
| `{act}` | `<kbd>E</kbd>` | Ⓧ | AGIR |
| `{cam}` | clic droit + glisser | le stick droit | glissez à droite |
| `{pause}` | `<kbd>Échap</kbd>` | Start | ⏸ |

Hint text is rebuilt (DOM nodes) only on `HINT_SHOW` and `INPUT_DEVICE`.

**Help offer:** pauses with reason `'help'`. Text « Besoin d'un coup de main ? » with « Faire apparaître la passerelle » (emits `HELP_ACCEPTED`) and « Non merci » (emits `HELP_DECLINED`).

**Toasts:** `SCORE_CHANGED` with a position gives « +10 »; `USAGER_PAID` gives « +3 000 Ar »; `SATISFACTION_CHANGED` gives « +7 satisfaction ».

**Respawn fade:** `#a3d-fade` uses the class `is-on` (light blue `#BFE9FF`, 250 ms). It is removed on `PLAYER_RESPAWN` with a 300 ms transition.

### 13.4 Quiz modal (`ui/QuizModal.js`)

```js
export class QuizModal { constructor({ root, bus, api, input, speech, strings })
  setRun({ runId, questionsBySlot /* {q1: Question} */, mode /* 'online'|'offline' */ }) ; open(slot, title) ; close() ; handleNav(input) ; getAnswers() /* [{slot, attempts}] */ }
```

**Flow on `QUIZ_REQUEST`:**
1. If there is no question for the slot, emit `QUIZ_DONE {skipped:true, firstTryCorrect:false, attempts:[], solved:true}` without opening.
2. Otherwise pause (`'quiz'`) and open the modal:
   - title `title`;
   - question text at ≥ 20 px;
   - vrai/faux: 2 big buttons side by side; QCM: up to 4 stacked buttons;
   - every button ≥ 56 px high, keys 1–4, gamepad dpad + A;
   - « 🔊 Écouter » when TTS is available.
3. **On choice** (online), disable the buttons and POST `/api/repondre/`:
   - `correct`: green, « Bonne réponse ! » + `explication` + « Continuer ».
   - wrong and not solved (QCM): grey out and cross the choice, « Pas tout à fait… Essayez encore. », re-enable the remaining options.
   - wrong and solved: highlight `reveal_choice_ids` in green, show `explication` + « Compris ! ».
4. **Network failure** after one retry:
   - offline fallback question (has `correct` flags): grade locally;
   - otherwise show « Réponse notée, correction à la fin de la partie. », record the attempt, and treat it as solved.
5. On close, emit `QUIZ_DONE {slot, skipped:false, firstTryCorrect: attempts.length === 1 && correctOnFirst, attempts, solved:true, offlineGraded}` and resume.

### 13.5 Dialogue, pause, settings

**Dialogue:**
- Bottom panel with the name and one line at a time.
- « Continuer » (Agir / Entrée / tap / A); « Fermer » on the last line.
- Pauses with reason `'dialogue'`. Emits `DIALOGUE_CLOSED {npcId, stepId}`.
- `autoTalk` NPCs open when the player first comes within 3 m (P4 emits `NPC_TALK`).

**Pause menu** (Escape / P / Start / HUD button; reason `'menu'`):
- « Reprendre », « Recommencer le niveau », « Commandes », « Aides », « Options », « Quitter le niveau ».

**Aides:**
- Profile radio (Mode guidé / Occasionnel / Joueur) plus per-assist toggles, each with a one-line description.
- Saved, then `SETTINGS_CHANGED`; it applies at the next level start, except the HUD-only assists, which apply immediately.

**Options:**
- « Qualité graphique : Auto / Économie / Standard / Haute » (`engine.setTier`, reason `'user'`).
- « Réduire les mouvements », « Distance de la caméra : Proche / Normale / Loin », « Inverser l'axe vertical », « Vibrations », « Commandes pour gaucher », « Secousses de caméra », « Volume », « Lecture vocale », « Grand texte ».

**Commandes:** an illustrated sheet for the active device, including « Nouveau : Espace sert à sauter, E à agir. ».

**Other pauses:**
- `document.visibilitychange` hidden → pause `'hidden'` (auto-resume on return is off; the menu is shown).
- Context lost → pause `'context'`.

### 13.6 Audio and speech

```js
export class Audio { constructor({ bus, settings }) ; unlock() /* call in the Play click handler */ ; setVolume(v) ; play(name, opts) ; setAmbience(on) ; suspend() ; resume() }
export const Speech = { available() : boolean, speak(text, onEnd) : void, cancel() : void }  // fr* voice only; available() false => hide buttons
```

**Synthesized SFX** (WebAudio oscillators + noise, no files), driven by bus events:
- `jump` (up-chirp), `land` (thump; heavy = louder), `goutte` (bell ping; pitch rises within a 1.5 s combo)
- `tick` (action progress every 0.5 s), `repair_done` (arpeggio C-E-G-C), `coins` (two-partial ding)
- `restore` (filtered noise swell), `valve` (metal clank), `splash` (fall into water), `whoosh` (respawn, pad)
- `checkpoint` (chime), `quiz_ok`, `quiz_ko` (soft low), `ui` (click), `star` (sparkle)

Ambience: low-volume wind plus synthesized birds, with ≤ 6 voices.

### 13.7 `net/ApiClient.js`

```js
export class ApiClient { constructor({ urls, csrf })
  async startRun(level) : Promise<StartResponse | {ok:false, offline:true} | {ok:false, error, status}>
  async answer(runId, slot, choiceId) : Promise<AnswerResponse | {ok:false, offline:true}>
  async submitResult(payload) : Promise<ResultResponse | {ok:false, offline:true} | {ok:false, error, status}>
  async flushPending() : Promise<void> }
```

- `fetch` with `credentials: 'same-origin'` and headers `X-CSRFToken: csrf` (from the bootstrap, falling back to the `csrftoken` cookie), `X-Requested-With: XMLHttpRequest`, `Content-Type: application/json`.
- Timeout 10 s via `AbortController`.
- One retry on a network error.
- `429`: wait `retry_after_s` and retry (maximum 2 times).
- `403` with `{"error":"csrf"}`: store the result payload in storage `pending` and show « Session expirée : rechargez la page pour enregistrer votre partie. ».
- `submitResult` on a network failure also stores the payload in `pending`.
- `flushPending()` runs at boot: POST, then remove on any 2xx/4xx (the server is idempotent).

---

## 14. Backend (P1)

### 14.1 Models

Append to `apps/serious_game/models.py`.

```python
class GameRun(models.Model):
    STATUT_EN_COURS, STATUT_TERMINE, STATUT_ABANDONNE, STATUT_REJETE = "en_cours", "termine", "abandonne", "rejete"
    STATUT_CHOICES = [(STATUT_EN_COURS, "En cours"), (STATUT_TERMINE, "Terminé"), (STATUT_ABANDONNE, "Abandonné"), (STATUT_REJETE, "Rejeté")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game3d_runs")
    level = models.PositiveSmallIntegerField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_COURS)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    client_duration_ms = models.PositiveIntegerField(default=0)
    quiz_snapshot = models.JSONField(default=list, blank=True)   # [{slot, source:'db'|'fallback', question_id, fallback_id, theme, question_text, question_type, answer_options, expected_answer, explication}]
    answers = models.JSONField(default=list, blank=True)         # [{slot, attempts:[choice_id...], solved:bool, first_try_correct:bool, source:'server'|'client'}]
    quiz_first_try = models.PositiveSmallIntegerField(default=0)
    gouttes = models.PositiveSmallIntegerField(default=0)
    gouttes_total = models.PositiveSmallIntegerField(default=0)
    events = models.JSONField(default=dict, blank=True)
    segments = models.JSONField(default=list, blank=True)
    falls = models.PositiveIntegerField(default=0)
    help_bridges = models.PositiveSmallIntegerField(default=0)
    assists = models.JSONField(default=list, blank=True)
    stars_mask = models.PositiveSmallIntegerField(default=0)
    new_stars_mask = models.PositiveSmallIntegerField(default=0)
    score = models.PositiveIntegerField(default=0)
    xp_etoiles = models.PositiveIntegerField(default=0)
    xp_pratique = models.PositiveIntegerField(default=0)
    xp_bonus = models.PositiveIntegerField(default=0)
    xp_gagne = models.PositiveIntegerField(default=0)
    rewards_processed = models.BooleanField(default=False)
    quality_tier = models.CharField(max_length=12, blank=True, default="")
    client_version = models.CharField(max_length=20, blank=True, default="")
    rejected_reason = models.CharField(max_length=120, blank=True, default="")
    class Meta:
        db_table = "game3d_runs"; ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "level", "-started_at"], name="game3d_run_user_lvl_idx")]
        verbose_name = "Partie Hydria Quest 3D"; verbose_name_plural = "Parties Hydria Quest 3D"

class GameLevelBest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game3d_bests")
    level = models.PositiveSmallIntegerField()
    best_stars_mask = models.PositiveSmallIntegerField(default=0)
    best_score = models.PositiveIntegerField(default=0)
    best_time_ms = models.PositiveIntegerField(null=True, blank=True)
    runs_completed = models.PositiveIntegerField(default=0)
    first_completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = "game3d_level_best"; unique_together = [("user", "level")]
        verbose_name = "Record Hydria Quest 3D"; verbose_name_plural = "Records Hydria Quest 3D"
```

**Migration `0010_game3d.py`:**
- Depends on `("serious_game", "0009_sync_model_labels")` and `swappable_dependency(AUTH_USER_MODEL)`.
- `CreateModel` for both models, plus `RunPython(seed_game_badges, unseed)`.
- **It must be compatible with Django 4.2**, the VPS version: no `db_comment`, no `GeneratedField`.
- Seeded badges are `QuizBadge` rows with `get_or_create` by code, `condition_type="jeu3d"`, `actif=True`:

| code | nom | icon | condition |
|---|---|---|---|
| `jeu_premiers_pas` | Premiers pas | `fa-shoe-prints` | Level 0 completed |
| `jeu_reparateur` | Réparateur | `fa-wrench` | ★3 on level 1 |
| `jeu_tournee_a_l_heure` | Tournée à l'heure | `fa-cash-register` | ★3 on level 2 |
| `jeu_chateau` | Maître du château d'eau | `fa-water` | Level 3 completed |
| `jeu_12_etoiles` | Douze étoiles | `fa-star` | All 12 stars |

### 14.2 `game3d_levels.py`

```python
GAME3D_VERSION = "1.0.0"
LEVELS = {
    0: dict(code="L0_premier_jour", titre="Premier jour au village", slots=[("q1", "usage_intro", "vrai_faux")],
            gouttes=30, par_s=240, min_s=60, star_xp=15, star3="quiz_first_try", score_max=400),
    1: dict(code="L1_pompe_panne", titre="La pompe en panne", slots=[("q1", "stocks_livraisons", None), ("q2", "planning_validation", None)],
            gouttes=40, par_s=300, min_s=90, star_xp=25, star3="quiz_first_try", score_max=600),
    2: dict(code="L2_tournee", titre="Tournée d'encaissement", slots=[("q1", "encaissements", None), ("q2", "encaissements", None), ("q3", "releves_facturation", None)],
            gouttes=40, par_s=330, min_s=100, star_xp=30, star3="tournee_a_l_heure", score_max=700),
    3: dict(code="L3_chateau", titre="Journée chargée au château d'eau", slots=[("q1", "dashboards_controles", None), ("q2", "data_villages_ouvrages", None), ("q3", "dashboards_controles", None)],
            gouttes=50, par_s=360, min_s=80, star_xp=30, star3="service_exemplaire", score_max=800),
}
ALL_STARS_BONUS_XP = 50
PRACTICE_BASE_XP, PRACTICE_PER_QUIZ_XP, PRACTICE_DAILY_CAP = 5, 2, 30
START_RATE_LIMIT_S, RUN_MAX_AGE_H, MAX_ANSWER_POSTS_PER_RUN = 8, 48, 30
QUESTION_MAX_LEN, OPTION_MAX_LEN = 220, 80
FALLBACK_QUESTIONS = { 0: [...], 1: [...], 2: [...], 3: [...] }
```

Each `FALLBACK_QUESTIONS` entry has the shape `{"id": "fb_l1_2", "type": "vrai_faux", "text": "...", "options": [{"text": "Vrai", "correct": False}, {"text": "Faux", "correct": True}], "explication": "..."}`. The contents:

| id | Type | Question | Answer |
|---|---|---|---|
| fb_l0_1 | VF | Une borne fontaine qui fuit doit être signalée, même si l'eau coule encore. | **Vrai** |
| fb_l0_2 | VF | Un relevé doit être rattaché à un point d'eau pour être exploitable. | **Vrai** |
| fb_l1_1 | QCM | Dans quel ordre suit-on une réparation ? | **« Signalée → Planifiée → En cours → Terminée → Validée »** (distractors « Planifiée → Signalée → Validée → Terminée », « En cours → Terminée → Signalée ») |
| fb_l1_2 | VF | Le matériel peut sortir du magasin sans bon de livraison. | **Faux** |
| fb_l1_3 | VF | Une réparation terminée doit encore être validée par le responsable. | **Vrai** |
| fb_l2_1 | QCM | Quelle est la date limite de paiement d'une facture de kiosque ? | **« Le 5 du mois »** (distractors « Le 15 du mois », « Le 30 du mois ») |
| fb_l2_2 | VF | Après le paiement d'un usager coupé, il faut remettre l'eau. | **Vrai** |
| fb_l2_3 | VF | Les reçus de la tournée doivent revenir à la caissière pour être enregistrés. | **Vrai** |
| fb_l3_1 | VF | Un tableau de bord sert aussi à repérer des anomalies. | **Vrai** |
| fb_l3_2 | QCM | Depuis un ouvrage, quelle chaîne mène à sa commune ? | **« Point d'eau → Parcelle → Village → Fokontany → Commune »** (distractors « Village → Ouvrage → District → Commune », « Parcelle → Commune → Fokontany → Village ») |
| fb_l3_3 | VF | Une vanne fermée peut priver tout un quartier d'eau. | **Vrai** |

Every fallback question has a short `explication` in French. Option ids are generated as `choice_{n}` in order.

### 14.3 `game3d_services.py`

```python
def get_visible_themes(user)                       # wraps views._get_theme_queryset_for_user (import inside the function)
def build_run_questions(user, level, count=None) -> list[dict]   # snapshots, one per slot (§ selection)
def start_run(user, level, count=None) -> GameRun  # rate limit raises Game3DRateLimited(retry_after_s)
def public_questions(run) -> list[dict]            # strips expected_answer and explication
def answer_question(run, slot, choice_id) -> dict  # select_for_update; grading rules below
def finalize_game_run(run_id, user, payload) -> dict  # transaction.atomic; idempotent
def compute_stars(run, payload_events, level_cfg) -> int
def award_game_badges(user, level, stars_mask, total_stars) -> list[QuizBadge]
def get_bests(user) -> dict                        # {"0": {"stars_mask", "best_time_ms", "best_score", "completed"}, ...}
```

**Question selection, per slot `(slot, module, preferred_type)`:**
1. Candidates:
   - `QuizQuestion.objects.filter(actif=True, est_dynamique=False, type_question__in=["qcm","vrai_faux"], theme__in=visible, theme__module_code=module)`;
   - snapshot via `serialize_question_snapshot`;
   - keep only snapshots with `len(question_text) ≤ 220`, 2–4 options each ≤ 80 chars, and a non-empty `expected_answer.choice_ids`;
   - exclude questions already used in this run.
2. **Missed first:** question ids from `QuizSessionQuestion(session__utilisateur=user, is_correct=False, answered_at ≥ now−30 days)` together with GameRun answers in the last 30 days where `first_try_correct` is false.
3. Prefer `preferred_type` when available, then pick at random with `random.SystemRandom`.
4. If nothing is left, take the next unused fallback question for the level (`source="fallback"`).
5. Snapshot entry: `{slot, source, question_id: str(uuid)|None, fallback_id: str|None, theme: theme.nom|"Questions du jeu", question_text, question_type, answer_options, expected_answer, explication}`.

**Answer grading** (`answer_question`):
- **Errors:** run not owned → `Http404`; statut ≠ en_cours → 409 `{"error":"partie_terminee"}`; unknown slot or choice → 400; more than 30 posts → 429.
- **Already solved** → return the stored state with `"already": true`.
- **Correct** → `solved = True`; `first_try_correct = len(attempts) == 1`.
- **Wrong:**
  - `vrai_faux` → `solved = True` (reveal);
  - `qcm` → `solved = len(set(attempts)) ≥ len(options) − 1` (reveal once only one option remains).
- **Response:** `{"ok": true, "correct": bool, "solved": bool, "attempt": n, "first_try_correct": bool, "eliminated": [wrong choice ids], "reveal_choice_ids": [...] if solved else [], "explication": explication if solved else ""}`.

**`finalize_game_run`:**
1. Lock the run with `select_for_update`; it must be owned by the user, otherwise `Http404`.
2. If `rewards_processed` → return the stored response with `already_processed: true`.
3. Validate `level == run.level` (else 400) and run age ≤ 48 h (else reject `"partie_expiree"`).
4. If `completed` is false → `abandonne`, xp 0, `rewards_processed = True`.
5. **Plausibility** (failure → `rejete`, xp 0, reason):
   - `duration_ms < min_s*1000` → `"duree_trop_courte"`;
   - `duration_ms > (now − started_at)ms + 5000` → `"duree_incoherente"`;
   - `gouttes < 0` or `gouttes > cfg.gouttes`, or `gouttes_total ≠ cfg.gouttes` → `"gouttes_invalides"`.
6. **Merge answers:** for each snapshot slot without a server answer, take the payload `attempts` (≤ 4, valid ids), grade them from the snapshot and mark them `source:'client'`. `quiz_first_try` = number of snapshot slots answered correctly on the first attempt.
7. **Stars:**
   - bit0 = `completed`;
   - bit1 = `gouttes == cfg.gouttes`;
   - bit2 by rule: `quiz_first_try` → `quiz_first_try == len(snapshot) > 0`; `tournee_a_l_heure` → `events.on_time_payments ≥ 2 and events.restores ≥ 1`; `service_exemplaire` → `events.missed_breakdowns == 0 and events.repairs ≥ 3`.
   - Event values are coerced to int, clamped 0–50.
8. **Best record:** `GameLevelBest` `select_for_update` / `get_or_create`.
   - `new = mask & ~best.best_stars_mask`; `xp_etoiles = popcount(new) * cfg.star_xp`.
9. **Practice XP:**
   - `today` = local day (`timezone.localdate()`, with a range filter on `finished_at` built from `localtime`).
   - `done_today = sum(xp_pratique)` of this user's runs finished today.
   - If no run of this level today has `xp_pratique > 0`: `xp_pratique = max(0, min(5 + 2*quiz_first_try, 30 − done_today))`.
10. **Update best:** `mask |= ...`, `best_score = max(best_score, min(score_client, cfg.score_max))`, `best_time_ms = min(...)`, `runs_completed += 1`, set `first_completed_at`.
11. **Bonus:** if the total best stars across levels moves from < 12 to 12 → `xp_bonus = 50`.
12. **Progress:**
    - `xp = xp_etoiles + xp_pratique + xp_bonus`;
    - `progress = get_or_create_user_progress(user)` (`select_for_update`);
    - `total_xp += xp`, `level = calculate_level(total_xp)`, `last_activity_date = localdate`;
    - save only those fields. **`quizzes_completed` and the streaks are never touched.**
13. Award badges.
14. Save the run: `statut = termine`, all fields, `finished_at`, `rewards_processed = True`.

**Result response:**

```json
{"ok": true, "run_id": "…", "statut": "termine", "already_processed": false, "rejected_reason": "",
 "stars_mask": 7, "new_stars_mask": 4, "stars": [true, true, true],
 "xp_gagne": 35, "xp_detail": {"etoiles": 30, "pratique": 5, "bonus": 0},
 "total_xp": 420, "level": 3, "level_progress": {"level": 3, "progress_percent": 68, "current_level_xp": 170, "xp_to_next_level": 80, "next_level_threshold": 500},
 "best": {"stars_mask": 7, "best_time_ms": 171300, "best_score": 260}, "total_stars": 8,
 "badges": [{"code": "jeu_reparateur", "nom": "Réparateur", "icon": "fa-wrench"}]}
```

### 14.4 Endpoints

New file `views_game3d.py`; routes added to `urls.py` with the prefix `/serious-game/`. All views are `@login_required`; the APIs return JSON errors `{"ok": false, "error": code}`.

| Method + path | Name | Behaviour |
|---|---|---|
| `GET jeu-3d/` | `jeu_3d` | Renders `serious_game/jeu_3d.html` (§14.6) |
| `GET jeu-3d/api/questions/?level=L&count=N` | `jeu3d_questions` | Creates a GameRun (side effect, so `Cache-Control: no-store`). `N` defaults to the number of level slots and is clamped to it. Rate limit: 429 `{"ok": false, "error": "trop_rapide", "retry_after_s": n}` if the user started a run less than 8 s ago. 200 → `{"ok": true, "run_id", "level", "questions": [{"slot", "type", "text", "options": [{"id", "text"}], "theme", "source"}], "best": {...}}` |
| `POST jeu-3d/api/repondre/` | `jeu3d_answer` | JSON `{run_id, slot, choice_id}` → answer response (§14.3) |
| `POST jeu-3d/api/resultat/` | `jeu3d_result` | JSON `ResultPayload` → result response; idempotent |

**ResultPayload** (built by P5):

```json
{"run_id": "uuid", "level": 1, "completed": true, "duration_ms": 254300, "gouttes": 38, "gouttes_total": 40,
 "answers": [{"slot": "q1", "attempts": ["choice_3", "choice_1"]}],
 "events": {"repairs": 2, "missed_breakdowns": 0, "payments_due": 0, "payments_overdue": 0, "payments_cutoff": 0, "restores": 0, "on_time_payments": 0, "receipts_delivered": 0, "valves": 1},
 "segments": [{"cp": "cp1", "t_ms": 61000, "falls": 2, "help_bridge": false}],
 "falls": 3, "help_bridges": 0, "assists": ["profile:debutant", "landingAssist:fort", "safeEdges"],
 "score_client": 410, "quality_tier": "low", "client_version": "a3d-1.0.0"}
```

**CSRF:**
- The POST endpoints keep Django's CSRF protection (no `csrf_exempt`).
- The page view calls `get_token(request)` and puts the token in the bootstrap. The JS sends `X-CSRFToken`.
- The existing `CSRF_FAILURE_VIEW` returns `{"error": "csrf"}` 403 for `X-Requested-With`.
- P1 verifies that `CSRF_TRUSTED_ORIGINS` contains `https://planning.hydria.mg`.

### 14.5 Bootstrap

`{{ a3d_bootstrap|json_script:"a3d-bootstrap" }}`:

```json
{"version": "1.0.0", "debug": false,
 "urls": {"questions": "/serious-game/jeu-3d/api/questions/", "answer": "/serious-game/jeu-3d/api/repondre/", "result": "/serious-game/jeu-3d/api/resultat/",
          "home": "/serious-game/", "simulation": "/serious-game/simulation/", "progress": "/serious-game/quiz/progression/"},
 "csrf": "…", "user": {"display_name": "Herizo", "is_staff": false},
 "progress": {"total_xp": 120, "level": 2, "level_progress": {...}},
 "best": {"0": {"stars_mask": 7, "best_time_ms": 171300, "best_score": 260, "completed": true}},
 "total_stars": 3, "unlock_all": false, "assist_default": "debutant",
 "levels_meta": {"0": {"gouttes": 30, "slots": ["q1"], "par_s": 240, "min_s": 60}, "...": {}},
 "fallback_questions": {"0": [{"id": "fb_l0_1", "type": "vrai_faux", "text": "…", "options": [{"id": "choice_1", "text": "Vrai", "correct": true}, {"id": "choice_2", "text": "Faux", "correct": false}], "explication": "…"}]}}
```

- `display_name`: `employe.surnom`, else `first_name`, else `username`.
- `assist_default`: `"debutant"` if the user has no completed GameRun, else `null`. localStorage still wins.
- `unlock_all`: `user.is_staff`.
- `debug`: `request.GET.get("debug") == "1"`.

The fallback answers are deliberately public: they are used only offline, and offline play gives no XP.

### 14.6 Template `serious_game/jeu_3d.html`

The template extends `planning_shell_base_template`.

**`extra_head` block**, which must be the first module-related tag on the page (P1 verifies that the base templates load no `type="module"` script before `extra_head`):

```html
<script type="importmap">{{ a3d_importmap|safe }}</script>
<link rel="stylesheet" href="{% static 'serious_game/css/academy3d.css' %}?v={{ a3d_css_hash }}">
```

**`a3d_importmap`** is built in the view with `json.dumps`:

```json
{"imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/",
  "a3d/main.js": "/static/serious_game/academy3d/main.js?v=1a2b3c4d5e",
  "a3d/core/EventBus.js": "/static/serious_game/academy3d/core/EventBus.js?v=…"
}}
```

How it is generated:
- Walk `Path(apps.serious_game.__file__).parent / "static/serious_game/academy3d"` recursively.
- Map every `*.js` file to `static("serious_game/academy3d/" + rel)` + `?v=` + the first 10 chars of the sha1 of its content.
- Cache with `functools.lru_cache` when not `DEBUG`; recompute on every request in `DEBUG`.
- The CSS hash is computed the same way.

**`content` block:** the DOM skeleton of §13.1, then `{{ a3d_bootstrap|json_script:"a3d-bootstrap" }}`. Above the stage: a small header « Hydria Quest 3D » and a link « Version 2D ».

**`extra_js` block:**

```html
<script type="module">
  import { boot } from 'a3d/main.js';
  boot(document.getElementById('a3d-app'));
</script>
<script>
  setTimeout(function () { if (!window.__a3dBooted) { var f = document.getElementById('a3d-fallback'); f.hidden = false;
    f.innerHTML = '<p>Le jeu n\'a pas pu démarrer (navigateur trop ancien ou connexion lente).</p><a href="{% url "serious_game:simulation" %}">Jouer à la version 2D</a>'; } }, 12000);
</script>
```

**Other template edits:**
- `index.html`: add a « Hydria Quest 3D » card linking to `serious_game:jeu_3d`, showing « {total_stars}/12 étoiles ».
- The existing simulation card is retitled « Simulation 2D ».
- `simulation.html`: add a link « Essayer Hydria Quest 3D ».
- Every serious_game template must keep `{% extends planning_shell_base_template %}`.

**Admin:**
- `GameRunAdmin`: `list_display` (user, level, statut, stars_mask, xp_gagne, client_duration_ms, started_at); filters on level and statut; JSON fields read-only.
- `GameLevelBestAdmin`.

### 14.7 Tests (`apps/serious_game/tests_game3d.py`)

Run with `--testrunner django.test.runner.DiscoverRunner`.

1. The page requires login. On `planning.hydria.mg` (reuse `PLANNING_SETTINGS` from `hydria/test_academy_subdomain.py`) it renders with `planning/base.html` and contains `three@0.170.0`, `a3d/main.js` and `a3d-bootstrap`.
2. The questions endpoint creates a GameRun with one snapshot per slot, and the response contains no `expected_answer` and no `explication`. With no DB questions it uses the fallback. It answers 429 within 8 s.
3. Answers:
   - QCM wrong, then retry, then correct;
   - vrai/faux wrong reveals and solves;
   - idempotent after solved;
   - another user's run gives 404;
   - a run in statut `termine` gives 409.
4. Results:
   - too-short duration → `rejete` and xp 0;
   - first completion gives star XP; an identical replay gives 0 star XP;
   - practice XP is capped at 30 per day across levels;
   - the 12-star bonus is awarded once;
   - a second POST of the same run is `already_processed` and gives no extra XP;
   - `completed: false` → `abandonne`;
   - `gouttes` above the total → rejected;
   - `QuizUserProgress.total_xp` and `level` are updated and `quizzes_completed` is unchanged;
   - badges are awarded.
5. A POST without a CSRF token, using `Client(enforce_csrf_checks=True)`, returns 403.

---

## 15. Orchestration (P5)

### 15.1 `main.js` boot

```js
export async function boot(rootEl) {
  window.__a3dBooted = true;
  // 1. bootstrap = JSON.parse(#a3d-bootstrap); bus = new EventBus(); settings, assist state; api = new ApiClient(); api.flushPending()
  // 2. Screens.showStart(); rotate overlay watcher (coarse && portrait)
  // 3. if (!hasWebGL2()) -> Screens.showFallback('webgl2') and stop
  // 4. preload: threePromise = Promise.race([import('three'), timeout(12000)]); on failure -> showFallback('cdn')
  // 5. on "Jouer" (user gesture): audio.unlock(); coarse -> enter immersive; onboarding if no assist state; level select
  // 6. on level pick: Screens.showLoading(0); const { GameSession } = await import('a3d/app/GameSession.js');
  //    session (one Engine + InputManager reused across levels) .load(index) -> .start()
}
```

### 15.2 `GameSession`

```js
export class GameSession {
  constructor(app /* {bus, bootstrap, settings, assistState, api, audio, screens, hud, prompts, quiz, dialogue, pause, labels, toasts, input?, engine?} */)
  async load(levelIndex, onProgress) : Promise<void>
  start() : void
  pause(reason) : void ; resume(reason) : void      // reason set; paused if non-empty
  async restartLevel() : Promise<void>              // new run (handles 429 waiting behind the loading screen)
  async quit(sendAbandon = true) : Promise<void>    // POST completed:false (best effort); dispose the level; show level select
  dispose() : void
}
```

**`load()`:**
1. `api.startRun(level)`:
   - online: `{run_id, questions}`;
   - offline: fallback questions from the bootstrap, `mode = 'offline'`, run id `null`.
2. Create the Engine once (tier from `detectTier`) and `await engine.init()`.
3. Create a new `CollisionWorld`, `Player`, `CameraRig`, `LevelBuilder` → `LevelRuntime` (progress 0–0.9).
4. Call `engine.compile()` (0.9–1.0).
5. `quiz.setRun(...)`, `cameraRig.setZones`, `player.spawn`, `cameraRig.snapBehind`.
6. Emit `LEVEL_START`.

**Frame order** (`engine.setLoop`):

```
beginFrame(dt):   inp = input.poll()
fixedUpdate(dt):  level.preFixedUpdate(dt); player.fixedUpdate(dt, inp, camera.moveYaw); level.postFixedUpdate(dt, player, inp);
                  if (inp.pausePressed) pause('menu'); input.consumeEdges()     // only after the first step of the frame
update(dt, a):    player.update(dt, a); level.update(dt, a, player, camera.yaw); camera.update(dt, inp);
                  engine.setFocus(player.renderPosition); hud.update(...); prompts.update(dt); labels.update(level.getLabelAnchors(), player.renderPosition);
                  if (paused) { activeModal.handleNav(inp); input.consumeEdges(); }
```

**Pause model:**
- Reasons: `menu`, `quiz`, `dialogue`, `help`, `hidden`, `context`.
- While at least one reason is active: `engine.setPaused(true)`, `level.setPaused(true)`, `input.setEnabled(false)`, `governor.pause(true)`.
- Emit `GAME_PAUSE` / `GAME_RESUME`. Modals emit their own reason via the bus, and GameSession listens.

**Completion:**
1. On `LEVEL_COMPLETE`: disable input, play the cheer pose and confetti.
2. After 1500 ms, show the complete screen in the « Enregistrement… » state.
3. If a run id exists, `submitResult(payload)`, where the payload is `RunSummary` + `quiz.getAnswers()` + `assistsUsedList` + tier + version.
4. Update the screen with the server response.
5. Update the local best (storage `best`) only with client stars from **online** runs.

**Tier changes:** an `engine.setTier` triggered by the governor is applied at the next respawn or quiz pause, or after a 200 ms fade if requested three times.

---

## 16. Work packages

Every package must:
- stay inside its files;
- code against the contracts above;
- stub missing imports locally (in a throwaway local harness that is not committed) while the other packages are in progress.

### P1: Backend and Django templates

**Files:**
- `apps/serious_game/models.py` (append only)
- `apps/serious_game/migrations/0010_game3d.py`
- `apps/serious_game/game3d_levels.py`
- `apps/serious_game/game3d_services.py`
- `apps/serious_game/views_game3d.py`
- `apps/serious_game/urls.py` (add 4 routes)
- `apps/serious_game/admin.py` (register 2 models)
- `apps/serious_game/templates/serious_game/jeu_3d.html`
- `apps/serious_game/templates/serious_game/index.html` (3D card)
- `apps/serious_game/templates/serious_game/simulation.html` (link)
- `apps/serious_game/tests_game3d.py`

**Imports:** `quiz_services` (`serialize_question_snapshot`, `get_or_create_user_progress`, `calculate_level`, `get_progress_to_next_level`), `views._get_theme_queryset_for_user`, existing models. No JS.

**Must match:** §5 and §6 counts (`gouttes` 30/40/40/50, slots, `min_s`) with the P4 level files; the DOM skeleton of §13.1 exactly; the JSON shapes of §14.

**Do not apply migration 0010 on the VPS** without the user's explicit go-ahead.

### P2: Engine, rendering, environment, props, characters, FX

**Files:** `engine/Engine.js`, `engine/quality.js`, `render/palette.js`, `render/materials.js`, `render/geometry.js`, `render/lighting.js`, `render/sky.js`, `render/water.js`, `render/post.js`, `render/StaticWorld.js`, `render/props/index.js`, `render/props/platforms.js`, `render/props/village.js`, `render/props/infra.js`, `render/props/interactives.js`, `actors/characters.js`, `fx/particles.js`, `fx/IconLayer.js`, `fx/markers.js`.

**Imports:**
- `three`
- `three/addons/utils/BufferGeometryUtils.js`
- `three/addons/geometries/RoundedBoxGeometry.js`
- high tier only: `three/addons/environments/RoomEnvironment.js` and the `postprocessing/{EffectComposer,RenderPass,UnrealBloomPass,OutputPass}.js` addons
- `a3d/core/events.js` (EV), `a3d/core/tuning.js` (`TUNING.camera` fov/near/far)

**Provides to:** P3 (Engine, `createCharacter`, `fx.*`), P4 (StaticWorld, `create*View`, `fx.icons` / `fx.guide` / `fx.particles`), P5 (Engine, `detectTier`, `hasWebGL2`, `QUALITY_PRESETS`, `palette`).

**Acceptance:** on a Mali-G52 / Adreno 610-class phone, low tier holds a steady 30 fps on L3 within the low budget. Every shader includes the tone-mapping and colour-space chunks.

### P3: Player controller, collision, camera, input

**Files:** `core/tuning.js`, `physics/CollisionWorld.js`, `physics/debugDraw.js`, `player/Player.js`, `player/SafeGround.js`, `player/prediction.js`, `camera/CameraRig.js`, `input/InputManager.js`, `input/keyboard.js`, `input/gamepad.js`, `input/touch.js`.

**Imports:** `three`; `a3d/core/events.js`; `a3d/core/assists.js` (types only); from P2: `a3d/actors/characters.js` (`createCharacter`) and `engine.fx.{blobs, landing, particles}` via the Engine instance.

**Provides to:** P4 (CollisionWorld API, `Player.launch` / `autoWalkTo` / `setActionLock` / `setCheckpoint` / `character`), P5 (InputManager, Player, CameraRig).

**Acceptance:**
- Every gap and step in §6 is clearable with the given tuning.
- No tunnelling at 20 m/s.
- Respawn in under 0.8 s.
- 30 fps and 144 fps give identical jump arcs.
- AZERTY ZQSD works.
- The touch controls work with two thumbs at the same time.

### P4: Levels, builder, gameplay systems

**Files:** `gameplay/states.js`, `gameplay/LevelBuilder.js`, `gameplay/LevelRuntime.js`, `gameplay/Mission.js`, `gameplay/Interactions.js`, `gameplay/entities.js`, `levels/index.js`, `levels/helpers.js`, `levels/L0_premier_jour.js`, `levels/L1_pompe_panne.js`, `levels/L2_tournee.js`, `levels/L3_chateau.js`.

**Imports:** `three` (builder and runtime only); `a3d/core/events.js`; `a3d/core/tuning.js`; `a3d/core/assists.js` (types); from P2: `a3d/render/StaticWorld.js`, `a3d/render/props/index.js`, `a3d/render/palette.js`, `engine.fx.*`; from P3: the `CollisionWorld` and `Player` instances (passed in, not constructed).

**Provides to:** P5 (`LEVELS`, `LEVEL_META`, `getLevel`, `LevelBuilder`, `LevelRuntime` API, `RunSummary`, all gameplay events).

**Acceptance:**
- Every level can be completed with every star by keyboard and by touch.
- A wrong quiz never blocks.
- Mission timers pause during quiz, dialogue, menus and falls.
- Out-of-order actions never soft-lock an objective.

### P5: UI, HUD, menus, quiz, audio, API client, orchestration, CSS

**Files:** `main.js`, `app/GameSession.js`, `core/EventBus.js`, `core/events.js`, `core/storage.js`, `core/assists.js`, `ui/dom.js`, `ui/strings.js`, `ui/glyphs.js`, `ui/Screens.js`, `ui/Hud.js`, `ui/Prompts.js`, `ui/QuizModal.js`, `ui/Dialogue.js`, `ui/PauseMenu.js`, `ui/WorldLabels.js`, `ui/Toasts.js`, `audio/Audio.js`, `audio/Speech.js`, `net/ApiClient.js`, `static/serious_game/css/academy3d.css`.

**Imports:**
- P2: `Engine`, `hasWebGL2`, `detectTier`, `QUALITY_PRESETS`, `palette`
- P3: `CollisionWorld`, `Player`, `CameraRig`, `InputManager`, `createCollisionDebugView` (debug)
- P4: `LEVELS`, `LEVEL_META`, `getLevel`, `LevelBuilder`

`main.js` and everything it imports statically must stay three-free.

**Delivers first** (day 1, because every other package imports them): `core/EventBus.js`, `core/events.js`, `core/storage.js`, `core/assists.js`, exactly as specified in §4.

**CSS must style:** every `a3d-*` class used by P5's DOM, the P3 touch classes (§9), the immersive and embedded layouts, `.a3d-fade.is-on`, `.a3d-rotate` (portrait + coarse only), `.a3d-app.is-big-text`. Use the safe-area variables `:root { --a3d-safe-left: env(safe-area-inset-left, 0px); … }`. No Tailwind dependency, and dark/light themes via `html[data-theme]`.

**Acceptance:**
- The full flow works: start, onboarding, level select, load, play, quiz, complete with server XP, then next level.
- Offline mode plays with the fallback questions and shows that progress is not saved.
- No class churn or `innerHTML` per frame.

---

## 17. Integration checklist and deployment

1. **Contract check:** `levels/*` gouttes counts equal `game3d_levels.LEVELS[...]["gouttes"]` (30/40/40/50). Slots and `min_s` match. The dev sanity check in `levels/index.js` warns on mismatch.
2. **Smoke test:** `/serious-game/jeu-3d/?debug=1` on a local planning host shows the stats overlay and the collider wireframes. Play L0 to the end, check the GameRun in the admin, replay and confirm 0 star XP.
3. **Real device:** one Mali/Adreno low-end phone (low tier, 30 fps), one desktop with an iGPU (medium), and gamepad and touch passes.
4. **Deployment** (follow the user's VPS procedure: compare against `git show HEAD:`, back up, then `scp`):
   - send the new `academy3d/` tree, `css/academy3d.css`, and the P1 Python and template files;
   - **ask the user before applying migration `0010_game3d`**;
   - run `collectstatic`;
   - reload gunicorn;
   - check that nginx serves `.js` as `application/javascript`;
   - `curl` `/serious-game/jeu-3d/` (302 to login when unauthenticated) and one static module URL (200).
5. **Cache busting:** the per-file `?v=` hashes come from the import map, so no manual versioning is needed after a deployment. When `DEBUG` is off, the import-map cache is cleared on process restart.
---

## 18. Amendments (orchestrator, 2026-10-11) — these OVERRIDE anything above

- **A1. Navigation links.** `templates/planning/base.html`, `templates/planning/includes/planning_sidebar.html` and `templates/planning/planning_home.html` are owned by the orchestrator, not by any package. They currently point the "jeu" links to `/serious-game/simulation/` (deployed before the 3D game existed); the orchestrator switches them to `/serious-game/jeu-3d/` once the game ships. No package edits them.
- **A2. Practice XP helper.** P1 implements practice XP through a **pure function** in `game3d_services.py`:
  `def compute_practice_xp(quiz_first_try: int, done_today_xp: int, level_already_practiced_today: bool) -> int`
  implementing §14.3 step 9 exactly (`0` if already practiced this level today, else `max(0, min(PRACTICE_BASE_XP + PRACTICE_PER_QUIZ_XP*quiz_first_try, PRACTICE_DAILY_CAP - done_today_xp))`). `finalize_game_run` computes `done_today_xp` / `level_already_practiced_today` from the DB and calls it. Tests cover it directly.
- **A3. Import map block.** Both `templates/base.html` and `templates/planning/base.html` define `extra_head` inside `<head>` and load no `type="module"` script before it, so the import map goes in `extra_head` as specified.
- **A4. Encoding.** All new files: UTF-8 **without BOM**, LF line endings.
- **A5. Pre-existing test failures.** `apps.serious_game.tests.QuizFlowTests` has 3 pre-existing errors (badge `first_quiz_completed` duplicated by migration 0004). Not in scope; do not "fix" them and do not be misled by them.
- **A6. Safety.** No package touches the VPS, deploys, or runs `migrate` against the local development database (tests create their own test DB). Only the orchestrator deploys.

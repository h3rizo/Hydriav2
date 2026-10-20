// Hydria Quest 3D: event names and payloads (exact contract, spec §4.2). Three-free.

/** @typedef {'wrench'|'hourglass'|'check'|'coins'|'faucet_off'|'droplet'|'valve'|'box'|'receipt'|'speech'|'flag'|'star'|'question'|'lock'} IconKey */

/** @typedef {{targetId:string, kind:'repair'|'collect'|'restore'|'valve'|'talk'|'blocked',
 *   label:string, icon:IconKey, anchor:{x:number,y:number,z:number}, enabled:boolean, reason?:string}} InteractionHint */

/** @typedef {{levelIndex:number, completed:boolean, durationMs:number, gouttes:number, gouttesTotal:number,
 *   falls:number, helpBridges:number, helpBridgeIds:string[],
 *   events:{repairs:number, missed_breakdowns:number, payments_due:number, payments_overdue:number,
 *           payments_cutoff:number, restores:number, on_time_payments:number, receipts_delivered:number, valves:number},
 *   segments:Array<{cp:string, t_ms:number, falls:number, help_bridge:boolean}>,
 *   scoreClient:number, satisfactionMin:number|null, quizFirstTry:number, quizCount:number,
 *   starsClient:[boolean,boolean,boolean]}} RunSummary */

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

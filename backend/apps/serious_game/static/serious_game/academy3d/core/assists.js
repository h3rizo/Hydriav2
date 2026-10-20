// Hydria Quest 3D: assist profiles and player settings (spec §4.4, §10). Three-free.
// Read by P3 (player/camera/input) and P4 (gameplay); written by P5 (onboarding, pause menu).
import { storage } from 'a3d/core/storage.js';

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

/** Every assist key, in display order. */
export const ASSIST_KEYS = Object.freeze([
  'guidePath', 'objectiveArrow', 'landingAssist', 'landingMarker', 'safeEdges',
  'infiniteGlide', 'relaxedTimers', 'pauseTimersOnFall', 'offerHelpBridge',
]);
/** Assists that only affect the HUD and therefore apply immediately (spec §13.5). */
export const HUD_ONLY_ASSISTS = Object.freeze(['objectiveArrow']);
export const LANDING_ASSIST_VALUES = Object.freeze(['fort', 'leger', 'off']);
export const PROFILE_IDS = Object.freeze(['debutant', 'occasionnel', 'joueur']);

const QUALITY_VALUES = ['auto', 'low', 'medium', 'high'];
const CAMERA_DISTANCES = ['proche', 'normal', 'loin'];

function resolveFlag(value, levelIndex) {
  if (value === 'early') return levelIndex <= 1;
  if (value === 'early2') return levelIndex <= 2;
  return !!value;
}

function normalizeLanding(value, fallback) {
  if (LANDING_ASSIST_VALUES.includes(value)) return value;
  if (value === true) return 'leger';
  if (value === false) return 'off';
  return fallback;
}

/**
 * Profile + overrides, then the 'early' / 'early2' rules for the given level.
 * @returns {{profile:string, guidePath:boolean, objectiveArrow:boolean, landingAssist:'fort'|'leger'|'off',
 *  landingMarker:boolean, safeEdges:boolean, infiniteGlide:boolean, relaxedTimers:boolean,
 *  pauseTimersOnFall:boolean, offerHelpBridge:boolean}}
 */
export function resolveAssists(state /* {profile, overrides:{}} */, levelIndex) {
  const profile = state && ASSIST_PROFILES[state.profile] ? state.profile : 'debutant';
  const base = ASSIST_PROFILES[profile];
  const overrides = (state && state.overrides && typeof state.overrides === 'object') ? state.overrides : {};
  const li = Number.isFinite(levelIndex) ? levelIndex : 0;
  const out = { profile };
  for (const key of ASSIST_KEYS) {
    const raw = Object.prototype.hasOwnProperty.call(overrides, key) ? overrides[key] : base[key];
    if (key === 'landingAssist') {
      out[key] = normalizeLanding(raw, base.landingAssist);
    } else {
      out[key] = resolveFlag(raw, li);
    }
  }
  return out;
}

function sanitizeAssistState(raw) {
  if (!raw || typeof raw !== 'object' || !ASSIST_PROFILES[raw.profile]) return null;
  const overrides = {};
  if (raw.overrides && typeof raw.overrides === 'object') {
    for (const key of ASSIST_KEYS) {
      if (!Object.prototype.hasOwnProperty.call(raw.overrides, key)) continue;
      const v = raw.overrides[key];
      if (key === 'landingAssist') {
        if (LANDING_ASSIST_VALUES.includes(v)) overrides[key] = v;
      } else if (typeof v === 'boolean' || v === 'early' || v === 'early2') {
        overrides[key] = v;
      }
    }
  }
  return { profile: raw.profile, overrides };
}

/**
 * Storage 'assists', or null => onboarding needed.
 * SPEC-QUESTION: the spec says both "storage 'assists' or null => onboarding needed" and
 * "assist_default ... localStorage still wins". We follow the first (literal) comment so that
 * every new device asks the one onboarding question; `bootstrapDefault` is only used by the
 * onboarding screen as the pre-focused answer (see main.js).
 */
export function loadAssistState(bootstrapDefault) {
  void bootstrapDefault;
  return sanitizeAssistState(storage.get('assists'));
}

export function saveAssistState(state) {
  const clean = sanitizeAssistState(state);
  if (clean) storage.set('assists', clean);
}

function prefersReducedMotion() {
  try {
    return !!(globalThis.matchMedia && globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches);
  } catch (_) {
    return false;
  }
}

/**
 * Merged with DEFAULT_SETTINGS; reducedMotion resolved to a boolean.
 * When the player never chose a value, `_reducedMotionAuto` is true so that saveSettings()
 * keeps following the OS preference.
 */
export function loadSettings() {
  const stored = storage.get('settings');
  const s = { ...DEFAULT_SETTINGS };
  if (stored && typeof stored === 'object') {
    for (const key of Object.keys(DEFAULT_SETTINGS)) {
      if (!Object.prototype.hasOwnProperty.call(stored, key)) continue;
      const v = stored[key];
      switch (key) {
        case 'reducedMotion': s.reducedMotion = (typeof v === 'boolean') ? v : null; break;
        case 'cameraDistance': if (CAMERA_DISTANCES.includes(v)) s.cameraDistance = v; break;
        case 'quality': if (QUALITY_VALUES.includes(v)) s.quality = v; break;
        case 'volume': if (typeof v === 'number' && Number.isFinite(v)) s.volume = Math.min(1, Math.max(0, v)); break;
        default: if (typeof v === 'boolean') s[key] = v; break;
      }
    }
  }
  if (!stored || !Object.prototype.hasOwnProperty.call(stored, 'quality')) {
    const q = storage.get('quality');
    if (QUALITY_VALUES.includes(q)) s.quality = q;
  }
  if (s.reducedMotion === null) {
    s.reducedMotion = prefersReducedMotion();
    s._reducedMotionAuto = true;
  }
  return s;
}

export function saveSettings(s) {
  if (!s || typeof s !== 'object') return;
  const out = {};
  for (const key of Object.keys(DEFAULT_SETTINGS)) {
    out[key] = Object.prototype.hasOwnProperty.call(s, key) ? s[key] : DEFAULT_SETTINGS[key];
  }
  if (s._reducedMotionAuto) out.reducedMotion = null;
  storage.set('settings', out);
  storage.set('quality', QUALITY_VALUES.includes(out.quality) ? out.quality : 'auto');
}

/** ['profile:debutant','landingAssist:fort','safeEdges',...] — sent with the result payload. */
export function assistsUsedList(resolved) {
  if (!resolved) return [];
  const list = ['profile:' + (resolved.profile || 'debutant')];
  for (const key of ASSIST_KEYS) {
    const v = resolved[key];
    if (key === 'landingAssist') {
      if (v && v !== 'off') list.push('landingAssist:' + v);
    } else if (v) {
      list.push(key);
    }
  }
  return list;
}

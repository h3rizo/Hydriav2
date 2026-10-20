// Hydria Quest 3D: safe localStorage wrapper (spec §2.6, §4.5). Three-free.
// Keys are prefixed 'hydria3d:v1:'. Values are JSON. Nothing here ever throws: when
// localStorage is unavailable (private mode, blocked site data, quota), values are kept
// in memory for the lifetime of the page so the game keeps working.
//
// Keys used by the game:
//   'assists'   {profile, overrides}
//   'settings'  settings object (see core/assists.js DEFAULT_SETTINGS)
//   'quality'   'auto'|'low'|'medium'|'high'
//   'best'      {"0":{"m":mask,"s":score,"t":ms}}
//   'pending'   one ResultPayload waiting to be sent
//   'hintsSeen' {id:count}

const PREFIX = 'hydria3d:v1:';
const memory = new Map(); // fallback copy, holds JSON strings

function localStore() {
  try {
    const ls = globalThis.localStorage;
    return ls || null;
  } catch (_) {
    return null;
  }
}

export const storage = {
  /** Returns a freshly parsed copy of the stored value, or `fallback`. */
  get(key, fallback = null) {
    const k = PREFIX + key;
    try {
      const ls = localStore();
      if (ls) {
        const raw = ls.getItem(k);
        if (raw !== null && raw !== undefined) return JSON.parse(raw);
      }
    } catch (_) { /* corrupt value or blocked access: fall through */ }
    if (memory.has(k)) {
      try { return JSON.parse(memory.get(k)); } catch (_) { /* ignore */ }
    }
    return fallback;
  },

  /** Stores `value` as JSON. Returns true when it reached localStorage. */
  set(key, value) {
    const k = PREFIX + key;
    let raw;
    try {
      raw = JSON.stringify(value === undefined ? null : value);
    } catch (_) {
      return false;
    }
    try {
      const ls = localStore();
      if (ls) {
        ls.setItem(k, raw);
        memory.delete(k);
        return true;
      }
    } catch (_) { /* quota or blocked: keep in memory */ }
    memory.set(k, raw);
    return false;
  },

  remove(key) {
    const k = PREFIX + key;
    memory.delete(k);
    try {
      const ls = localStore();
      if (ls) ls.removeItem(k);
    } catch (_) { /* ignore */ }
  },
};

// Hydria Quest 3D: tiny synchronous pub/sub (exact contract, spec §4.1).
// Three-free. One bus per page, created in main.js and passed to every constructor as `bus`.
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

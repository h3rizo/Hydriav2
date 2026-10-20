// gameplay/states.js — three-free (TF).
// Business states shared by the gameplay systems, the HUD and the views.
// Names and colours follow the 2D Phaser simulation (js/systems/GameState.js, scenes/GameScene.js).

export const FACILITY_STATE = Object.freeze({ HEALTHY: 'healthy', BROKEN: 'broken', REPAIRING: 'repairing' });

export const CITIZEN_STATE = Object.freeze({
  DUE: 'due',
  OVERDUE: 'overdue',
  CUT_OFF: 'cut_off',
  RESTORE_PENDING: 'restore_pending',
  PAID: 'paid',
});

// Exact Phaser state colours (spec §0). `paid` is the 3D-only state and reuses the healthy green.
// SPEC-QUESTION: render/palette.js (P2) also exposes STATE_COLORS, but its key names are not fixed by the
// spec; P4 keeps its own copy keyed by state value so icons and rings never depend on P2's naming.
export const STATE_TINT = Object.freeze({
  healthy: 0x22c55e,
  repairing: 0xfacc15,
  broken: 0xef4444,
  due: 0xeab308,
  overdue: 0xf97316,
  cut_off: 0xef4444,
  restore_pending: 0x38bdf8,
  paid: 0x22c55e,
});

// Neutral tints used by P4 for non-state icons (valves, NPC speech bubbles, locks).
export const ACCENT_TINT = 0x22d3ee;   // HYDRIA_CYAN
export const NEUTRAL_TINT = 0xe2e8f0;

// Short French status labels (same wording as the Phaser simulation), useful for tooltips and labels.
export const STATE_LABEL = Object.freeze({
  healthy: 'Opérationnel',
  repairing: 'En réparation',
  broken: 'Panne',
  due: 'Paiement attendu',
  overdue: 'Impayé',
  cut_off: 'Eau coupée',
  restore_pending: 'Remise en eau',
  paid: 'Payé',
});

// render/palette.js — three-free (TF). Colour tokens shared by rendering, UI and gameplay (spec §0, §12.5).
// All values are sRGB hex integers. Rendering code converts them to linear with THREE.Color.
// Blue is reserved for water and Hydria items; the village uses warm earth, greens and brick.

export const PALETTE = Object.freeze({
  // Hydria identity
  HYDRIA_BLUE: 0x1e6fd9,
  HYDRIA_BLUE_DARK: 0x1552a6,
  HYDRIA_BLUE_LIGHT: 0x5aa0f0,
  HYDRIA_CYAN: 0x22d3ee,
  HYDRIA_YELLOW: 0xffc53d,
  HYDRIA_YELLOW_DARK: 0xe0a321,
  GLOVE_ORANGE: 0xff8a2a,
  TOOLBOX_RED: 0xe5383b,

  // Earth and vegetation
  LATERITE: 0xc2502a,
  LATERITE_LIGHT: 0xd9733f,
  LATERITE_DARK: 0x8f3a22,
  EARTH_PATH: 0xcf6a3c,
  EARTH_PATH_DARK: 0xa9512d,
  GRASS: 0x7dbb4a,
  GRASS_LIGHT: 0x9fd25a,
  GRASS_DARK: 0x5b9a35,
  LEAF: 0x4f9a3a,
  LEAF_LIGHT: 0x8cc84b,
  LEAF_DARK: 0x37742a,
  TRUNK: 0x8a5a3b,
  TRUNK_DARK: 0x6a4229,
  BAOBAB_BARK: 0xb48c74,
  BAOBAB_BARK_DARK: 0x8f6b57,
  RICE_WATER: 0x7cc7b8,
  RICE_SHOOT: 0x8fd14f,

  // Minerals and building materials
  ROCK: 0x9a958c,
  ROCK_LIGHT: 0xb9b4aa,
  ROCK_DARK: 0x6f6a63,
  CONCRETE: 0xd8d4cc,
  CONCRETE_LIGHT: 0xebe7df,
  CONCRETE_DARK: 0xa9a49a,
  WOOD: 0xb07a4a,
  WOOD_LIGHT: 0xd19a63,
  WOOD_DARK: 0x7d5232,
  BRICK: 0xc8643c,
  BRICK_LIGHT: 0xd8784e,
  BRICK_DARK: 0xa84e2e,
  WALL_PLASTER: 0xf1e3c8,
  METAL: 0x8796a3,
  METAL_DARK: 0x5c6873,
  HAZARD_YELLOW: 0xffcc33,
  HAZARD_DARK: 0x2b2f38,
  PIPE: 0x3b8fe6,
  PIPE_LIGHT: 0x6fb2f2,
  PIPE_DARK: 0x2a6fbd,
  TIN: 0x4a8fd8,
  TIN_LIGHT: 0x6aa8e8,
  TIN_DARK: 0x346fb0,
  TIN_RUST: 0xb0623a,
  THATCH: 0xd9b25f,
  THATCH_LIGHT: 0xe8c878,
  THATCH_DARK: 0xa98440,
  WINDOW: 0x3d5a73,
  WINDOW_FRAME: 0xf4efe6,
  DOOR: 0x8a5532,
  CARDBOARD: 0xc9a06a,
  PAPER: 0xfaf7ef,
  JERRYCAN_YELLOW: 0xf2c230,

  // Water and sky
  WATER_SHALLOW: 0x5fd3f0,
  WATER_DEEP: 0x1f8fd6,
  WATER_FOAM: 0xf4fcff,
  SKY_ZENITH: 0x3a9bef,
  SKY_ZENITH_MIDI: 0x2f8fe8,
  SKY_HORIZON: 0xcfefff,
  SKY_GROUND: 0xf3e3c3,
  SUN_DISK: 0xfffbe8,
  CLOUD: 0xffffff,
  CLOUD_SHADE: 0xdbe9f7,

  // Lights
  HEMI_SKY: 0xcfe8ff,
  HEMI_GROUND: 0xb8784e,
  SUN: 0xfff1d6,
  RIM: 0xfff6e0,
  FOG: 0xcfefff,

  // Characters
  SKIN_TONES: Object.freeze([0x8d5524, 0xa0673a, 0xc68642, 0x6b4226, 0xb5774a]),
  HAIR: 0x1d1714,
  EYE: 0x1b1a22,
  CHEEK: 0xf08a7a,
  SHOE: 0x4a3426,
  WHITE: 0xffffff,
  INK: 0x1f2433,
  OUTLINE: 0x1b2130,
  CLOTH_TONES: Object.freeze([0xe85d75, 0x8e6fd8, 0x2fb5a3, 0xf0a63a, 0xd94f3d, 0x6cbf5a, 0xf2d0a4, 0x4f7cac]),

  // Effects
  SPARK: 0xfff2a8,
  DUST: 0xe8cfae,
  CONFETTI: Object.freeze([0xff5d73, 0xffc53d, 0x22d3ee, 0x7dd35a, 0xb98bff, 0xff9f43]),
  COIN: 0xffc53d,
  STEAM: 0xffffff,
});

// Exact business-state colours (spec §0, same as the Phaser simulation). `paid` reuses the healthy green.
export const STATE_COLORS = Object.freeze({
  healthy: 0x22c55e,
  repairing: 0xfacc15,
  broken: 0xef4444,
  due: 0xeab308,
  overdue: 0xf97316,
  cut_off: 0xef4444,
  restore_pending: 0x38bdf8,
  paid: 0x22c55e,
});

// Per-style colours used by platforms (spec §12.5 box styles). `top` = walkable face, `side` = walls,
// `bottom` = underside / lowest strata, `accent` = trims (bands, flanges, edges).
export const STYLE_COLORS = Object.freeze({
  grass: Object.freeze({ top: PALETTE.GRASS, side: PALETTE.LATERITE, bottom: PALETTE.LATERITE_DARK, accent: PALETTE.GRASS_DARK }),
  laterite: Object.freeze({ top: PALETTE.LATERITE_LIGHT, side: PALETTE.LATERITE, bottom: PALETTE.LATERITE_DARK, accent: PALETTE.EARTH_PATH }),
  rock: Object.freeze({ top: PALETTE.ROCK_LIGHT, side: PALETTE.ROCK, bottom: PALETTE.ROCK_DARK, accent: PALETTE.GRASS_DARK }),
  concrete: Object.freeze({ top: PALETTE.CONCRETE_LIGHT, side: PALETTE.CONCRETE, bottom: PALETTE.CONCRETE_DARK, accent: PALETTE.CONCRETE_DARK }),
  wood: Object.freeze({ top: PALETTE.WOOD_LIGHT, side: PALETTE.WOOD, bottom: PALETTE.WOOD_DARK, accent: PALETTE.WOOD_DARK }),
  brick: Object.freeze({ top: PALETTE.CONCRETE, side: PALETTE.BRICK, bottom: PALETTE.BRICK_DARK, accent: PALETTE.BRICK_LIGHT }),
  metal: Object.freeze({ top: PALETTE.METAL, side: PALETTE.METAL_DARK, bottom: PALETTE.METAL_DARK, accent: PALETTE.HAZARD_YELLOW }),
  pipe: Object.freeze({ top: PALETTE.PIPE_LIGHT, side: PALETTE.PIPE, bottom: PALETTE.PIPE_DARK, accent: PALETTE.PIPE_DARK }),
  house_tin: Object.freeze({ top: PALETTE.TIN, side: PALETTE.BRICK, bottom: PALETTE.BRICK_DARK, accent: PALETTE.TIN_DARK }),
  kiosque: Object.freeze({ top: PALETTE.CONCRETE_LIGHT, side: PALETTE.WALL_PLASTER, bottom: PALETTE.CONCRETE_DARK, accent: PALETTE.HYDRIA_BLUE }),
  invisible: Object.freeze({ top: 0xffffff, side: 0xffffff, bottom: 0xffffff, accent: 0xffffff }),
});

/** '#rrggbb' for CSS / canvas use. */
export function toCss(hex) {
  return '#' + (hex >>> 0).toString(16).padStart(6, '0').slice(-6);
}

/** 'rgba(r,g,b,a)' for canvas use. */
export function toRgba(hex, alpha = 1) {
  const h = hex >>> 0;
  return `rgba(${(h >> 16) & 255},${(h >> 8) & 255},${h & 255},${alpha})`;
}

export default Object.freeze({ PALETTE, STATE_COLORS, STYLE_COLORS, toCss, toRgba });

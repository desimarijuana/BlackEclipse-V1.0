// ── Ghost avatar model ───────────────────────────────────────────────────────
// Every bot gets a face. Instead of a random blob of shapes, a bot's identity is
// a *ghost*: a small, hand-authored parametric SVG character. This module owns
// the model (a plain, serializable spec), the closed option counts the
// customizer renders, and the deterministic randomizer that gives a new bot a
// repeatable face.
//
// The spec is pure data — no React, no colors assumptions beyond hex strings —
// so it round-trips through JSON and can be persisted or sent over the wire.

/** A bot's face: which authored option to draw, plus two colors. */
export interface GhostSpec {
  /** Body silhouette (0..GHOST_VARIANT_COUNT-1). */
  variant: number;
  /** Eye style (0..GHOST_EYE_COUNT-1). */
  eyes: number;
  /** Mouth / expression (0..GHOST_MOUTH_COUNT-1). */
  mouth: number;
  /** Head accessory (0..GHOST_ACCESSORY_COUNT-1); 0 is "none". */
  accessory: number;
  /** Body pattern (0..GHOST_PATTERN_COUNT-1); 0 is "none". */
  pattern: number;
  /** Ghost body color (hex). */
  bodyColor: string;
  /** Accent color for accessories/patterns (hex). */
  accentColor: string;
}

export const GHOST_VARIANT_COUNT = 4;
export const GHOST_EYE_COUNT = 6;
export const GHOST_MOUTH_COUNT = 5;
export const GHOST_ACCESSORY_COUNT = 7;
export const GHOST_PATTERN_COUNT = 4;

/** Curated body/accent pairs. The randomizer and the "Randomize" button use
 *  these so a fresh bot always looks intentional rather than clashing. */
export const GHOST_PALETTE: ReadonlyArray<{ body: string; accent: string }> = [
  { body: '#8b7cf6', accent: '#f6c177' }, // violet / amber
  { body: '#5eead4', accent: '#f472b6' }, // teal / pink
  { body: '#f7b8d8', accent: '#7c3aed' }, // rose / violet
  { body: '#93c5fd', accent: '#facc15' }, // sky / gold
  { body: '#c4b5fd', accent: '#34d399' }, // lavender / emerald
  { body: '#fca5a5', accent: '#60a5fa' }, // coral / blue
  { body: '#fde68a', accent: '#8b5cf6' }, // sand / violet
  { body: '#a7f3d0', accent: '#fb7185' }, // mint / rose
  { body: '#cbd5e1', accent: '#f97316' }, // slate / orange
  { body: '#f0abfc', accent: '#22d3ee' }, // orchid / cyan
];

/** A stable default face used before a bot has been customized. */
export const DEFAULT_GHOST_SPEC: GhostSpec = {
  variant: 0,
  eyes: 0,
  mouth: 0,
  accessory: 0,
  pattern: 0,
  bodyColor: GHOST_PALETTE[0].body,
  accentColor: GHOST_PALETTE[0].accent,
};

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** FNV-1a — a tiny, stable string hash. Not cryptographic; only used to seed a
 *  bot's deterministic face from its id. */
export function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** mulberry32 — a compact, deterministic PRNG. Same seed → same sequence, so a
 *  bot's random face is reproducible across reloads and machines. */
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return function next(): number {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A random RNG suitable for the interactive "Randomize" button. */
export function createRng(seed?: number): () => number {
  const s = seed ?? (Date.now() ^ Math.floor(Math.random() * 0xffffffff));
  return mulberry32(s >>> 0);
}

function pickIndex(rng: () => number, count: number): number {
  return Math.floor(rng() * count) % count;
}

/** A fresh random face. Pass a seeded RNG for deterministic output. */
export function randomGhostSpec(rng: () => number = createRng()): GhostSpec {
  const palette = GHOST_PALETTE[pickIndex(rng, GHOST_PALETTE.length)];
  return {
    variant: pickIndex(rng, GHOST_VARIANT_COUNT),
    eyes: pickIndex(rng, GHOST_EYE_COUNT),
    mouth: pickIndex(rng, GHOST_MOUTH_COUNT),
    // ~1 in 3 faces gets an accessory; ~1 in 4 gets a pattern.
    accessory: rng() < 0.55 ? pickIndex(rng, GHOST_ACCESSORY_COUNT) : 0,
    pattern: rng() < 0.4 ? pickIndex(rng, GHOST_PATTERN_COUNT) : 0,
    bodyColor: palette.body,
    accentColor: palette.accent,
  };
}

/** The deterministic face for a bot id — same id always yields the same ghost. */
export function ghostSpecFromId(id: string): GhostSpec {
  if (!id) return { ...DEFAULT_GHOST_SPEC };
  return randomGhostSpec(mulberry32(hashString(id)));
}

function clampIndex(value: unknown, count: number, fallback: number): number {
  const n = typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : fallback;
  if (n < 0 || n >= count) return fallback;
  return n;
}

function clampHex(value: unknown, fallback: string): string {
  return typeof value === 'string' && HEX_RE.test(value) ? value.toLowerCase() : fallback;
}

/** Coerce any (untrusted, possibly partial) stored value into a valid spec.
 *  Unknown indices fall back to the default face instead of throwing. */
export function normalizeGhostSpec(input: unknown): GhostSpec {
  if (!input || typeof input !== 'object') return { ...DEFAULT_GHOST_SPEC };
  const raw = input as Partial<GhostSpec>;
  return {
    variant: clampIndex(raw.variant, GHOST_VARIANT_COUNT, DEFAULT_GHOST_SPEC.variant),
    eyes: clampIndex(raw.eyes, GHOST_EYE_COUNT, DEFAULT_GHOST_SPEC.eyes),
    mouth: clampIndex(raw.mouth, GHOST_MOUTH_COUNT, DEFAULT_GHOST_SPEC.mouth),
    accessory: clampIndex(raw.accessory, GHOST_ACCESSORY_COUNT, DEFAULT_GHOST_SPEC.accessory),
    pattern: clampIndex(raw.pattern, GHOST_PATTERN_COUNT, DEFAULT_GHOST_SPEC.pattern),
    bodyColor: clampHex(raw.bodyColor, DEFAULT_GHOST_SPEC.bodyColor),
    accentColor: clampHex(raw.accentColor, DEFAULT_GHOST_SPEC.accentColor),
  };
}

/** Stable string key for a spec, so the store can dedupe / detect changes. */
export function ghostSpecKey(spec: GhostSpec): string {
  return [spec.variant, spec.eyes, spec.mouth, spec.accessory, spec.pattern, spec.bodyColor, spec.accentColor].join(':');
}

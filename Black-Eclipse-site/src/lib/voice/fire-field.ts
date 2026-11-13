// ── Fire field simulation ───────────────────────────────────────────────────
// Framework-free, DOM-free and deterministic (seeded RNG) so it can be unit
// tested and reused by the mobile renderer. It owns a small heat grid that is
// advected upward plus an ember pool; the canvas host only paints the result.
//
// Coordinates: x in columns (0..cols-1), y in rows where y = 0 is the BOTTOM
// (the coal bed) and y = rows-1 is the top of the flame.

export interface FireInput {
  /** 0..1 smoothed microphone loudness. */
  level: number;
  /** 0..1 smoothed spectral centroid. */
  centroid: number;
  /** Pointer position in 0..1 of the field, or null when outside. */
  pointerX: number | null;
  pointerY: number | null;
  /** Extra impulse (a tap in the field), 0..1, decays on its own. */
  flare?: number;
}

export interface Ember {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
  heat: number;
  seed: number;
  alive: boolean;
}

export interface FireField {
  cols: number;
  rows: number;
  /** Row-major heat, y = 0 at the bottom. Values 0..1. */
  heat: Float32Array;
  scratch: Float32Array;
  embers: Ember[];
  energy: number;
  flare: number;
  time: number;
  rand: () => number;
}

export interface FireOptions {
  cols?: number;
  rows?: number;
  maxEmbers?: number;
  seed?: number;
}

/** Mulberry32 — small, fast, good enough for sparks, and reproducible. */
export function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp01 = (v: number): number => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

export function createFireField(options: FireOptions = {}): FireField {
  const cols = Math.max(8, Math.round(options.cols ?? 96));
  const rows = Math.max(6, Math.round(options.rows ?? 34));
  const maxEmbers = Math.max(8, Math.round(options.maxEmbers ?? 140));
  const embers: Ember[] = Array.from({ length: maxEmbers }, () => ({
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
    life: 0,
    maxLife: 1,
    heat: 0,
    seed: 0,
    alive: false,
  }));
  const rand = seededRandom(options.seed ?? 0x9e3779b9);
  // A coal bed does not start cold: seed a little heat so the first frame reads
  // as embers rather than an empty grid.
  const heat = new Float32Array(cols * rows);
  for (let x = 0; x < cols; x += 1) heat[x] = 0.22 + (x % 3) * 0.01;
  return { cols, rows, heat, scratch: new Float32Array(cols * rows), embers, energy: 0, flare: 0, time: 0, rand };
}

function spawnEmber(field: FireField, drive: number): void {
  const slot = field.embers.find((e) => !e.alive);
  if (!slot) return;
  const { cols, rand } = field;
  // Sparks prefer the middle of the bed, where the flame is hottest.
  const centre = cols / 2 + (rand() - 0.5) * cols * 0.35;
  const life = 0.9 + rand() * 1.9;
  slot.alive = true;
  slot.x = Math.min(cols - 1, Math.max(0, centre));
  slot.y = rand() * 1.5;
  slot.vx = (rand() - 0.5) * 0.35;
  slot.vy = -(0.35 + rand() * 1.1) * (0.45 + drive * 0.9);
  slot.life = life;
  slot.maxLife = life;
  slot.heat = 0.4 + drive * 0.6 * rand();
  slot.seed = rand() * Math.PI * 2;
}

/**
 * Advance the field by `dt` seconds. Cheap enough for 30 fps on a phone:
 * cols × rows ≈ 3.3k cells plus at most `maxEmbers` particles.
 */
export function stepFire(field: FireField, dt: number, input: FireInput): void {
  const step = Number.isFinite(dt) ? Math.min(0.06, Math.max(0, dt)) : 0;
  if (step === 0) return;

  const { cols, rows, heat, scratch, rand } = field;
  field.time += step;
  field.flare = clamp01(Math.max(field.flare * (1 - step * 3.2), clamp01(input.flare ?? 0)));

  const drive = clamp01(clamp01(input.level) * (0.82 + field.flare * 0.6));
  // Smoothed energy keeps the bed from strobing when the level jitters.
  field.energy += (drive - field.energy) * Math.min(1, step * 7);

  const pointerX = input.pointerX;
  const pointerCol = pointerX == null ? null : clamp01(pointerX) * (cols - 1);
  const windSigma = cols * 0.14;

  // ── Bottom row: the coal bed ────────────────────────────────────────────
  const bed = 0.2 + field.energy * 0.8;
  for (let x = 0; x < cols; x += 1) {
    const flicker = 0.06 * Math.sin(field.time * 5.3 + x * 0.42) + 0.05 * Math.sin(field.time * 9.1 + x * 1.7);
    let value = bed + flicker;
    if (pointerCol != null) {
      const dx = x - pointerCol;
      // The pointer is wind: it pushes heat away instead of feeding it.
      value -= Math.exp(-(dx * dx) / (2 * windSigma * windSigma)) * 0.35;
    }
    heat[x] = clamp01(value);
  }

  // ── Advect upward with lateral sway and light diffusion ─────────────────
  for (let y = rows - 1; y >= 1; y -= 1) {
    const row = y * cols;
    const below = (y - 1) * cols;
    const sway = Math.sin(field.time * 1.6 + y * 0.19) * (0.35 + y * 0.02);
    for (let x = 0; x < cols; x += 1) {
      let sx = x + sway;
      if (pointerCol != null) {
        const dx = x - pointerCol;
        const push = Math.exp(-(dx * dx) / (2 * windSigma * windSigma)) * -Math.sign(dx || 1) * 1.8;
        sx += push;
      }
      const i0 = Math.min(cols - 1, Math.max(0, Math.floor(sx)));
      const i1 = Math.min(cols - 1, Math.max(0, i0 + 1));
      const f = sx - Math.floor(sx);
      const left = heat[below + (i0 === 0 ? 0 : i0 - 1)];
      const mid = heat[below + i0] * (1 - f) + heat[below + i1] * f;
      const right = heat[below + Math.min(cols - 1, i1 + 1)];
      // Slight horizontal diffusion stops single columns from looking digital.
      scratch[row + x] = (mid * 2 + left + right) * 0.25 * (0.9 - y * 0.004);
    }
  }
  heat.set(scratch.subarray(cols, rows * cols), cols);
  for (let x = 0; x < cols; x += 1) heat[rows * cols - cols + x] = 0; // no source at the cap

  // ── Embers ──────────────────────────────────────────────────────────────
  if (field.energy > 0.12) {
    const expected = field.energy * 55 * step;
    let count = Math.floor(expected);
    if (rand() < expected - count) count += 1;
    for (let i = 0; i < count; i += 1) spawnEmber(field, field.energy);
  }

  for (const ember of field.embers) {
    if (!ember.alive) continue;
    ember.life -= step;
    if (ember.life <= 0 || ember.y < -2) {
      ember.alive = false;
      continue;
    }
    // Buoyancy + curl drift.
    ember.vy -= 0.35 * step;
    ember.vx += Math.sin(ember.y * 0.55 + ember.seed + field.time * 2.1) * 0.5 * step;
    if (pointerCol != null) {
      const dx = ember.x - pointerCol;
      const dy = ember.y - (input.pointerY == null ? 0 : clamp01(input.pointerY) * rows);
      const d2 = dx * dx + dy * dy;
      if (d2 < 36) {
        const f = (1 - d2 / 36) * 6 * step;
        ember.vx += Math.sign(dx || 1) * f;
        ember.vy += Math.sign(dy || 1) * f * 0.5;
      }
    }
    ember.x += ember.vx * step;
    ember.y += ember.vy * step;
    if (ember.x < -1 || ember.x > cols + 1) ember.alive = false;
  }
}

const S0: readonly [number, number, number] = [92, 16, 4];
const S1: readonly [number, number, number] = [255, 94, 14];
const S2: readonly [number, number, number] = [255, 228, 156];

function mix(a: readonly [number, number, number], b: readonly [number, number, number], t: number): [number, number, number] {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

/**
 * Heat ramp for one cell. The centroid nudges the mid-stop toward yellow, so a
 * bright voice (sibilance, energy) visibly burns hotter.
 */
export function heatColor(value: number, centroid = 0.3): [number, number, number] {
  const t = clamp01(value);
  const warm = clamp01(centroid);
  const mid = mix(S1, [255, 150, 40], warm * 0.6);
  return t < 0.5 ? mix(S0, mid, t / 0.5) : mix(mid, S2, (t - 0.5) / 0.5);
}

/** Alpha for a heat cell — thin flame edges stay translucent, cores are solid. */
export function heatAlpha(value: number): number {
  return clamp01(Math.pow(clamp01(value), 0.8));
}

import { describe, expect, it } from 'vitest';
import {
  createFireField,
  heatAlpha,
  heatColor,
  seededRandom,
  stepFire,
  type FireInput,
} from './fire-field';

const silent: FireInput = { level: 0, centroid: 0.3, pointerX: null, pointerY: null };
const loud: FireInput = { level: 0.9, centroid: 0.7, pointerX: null, pointerY: null };

function run(steps: number, input: FireInput, seed = 7) {
  const field = createFireField({ cols: 40, rows: 16, maxEmbers: 24, seed });
  for (let i = 0; i < steps; i += 1) stepFire(field, 1 / 30, input);
  return field;
}

describe('seededRandom', () => {
  it('is reproducible and inside [0, 1)', () => {
    const a = seededRandom(42);
    const b = seededRandom(42);
    for (let i = 0; i < 20; i += 1) {
      const v = a();
      expect(v).toBe(b());
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });
});

describe('stepFire', () => {
  it('is deterministic for a seed and input', () => {
    const a = run(45, loud, 99);
    const b = run(45, loud, 99);
    expect(Array.from(a.heat)).toEqual(Array.from(b.heat));
    const embersA = a.embers.filter((e) => e.alive).length;
    const embersB = b.embers.filter((e) => e.alive).length;
    expect(embersA).toBe(embersB);
  });

  it('keeps heat finite and inside 0..1', () => {
    const field = run(80, loud);
    for (const value of field.heat) {
      expect(Number.isFinite(value)).toBe(true);
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(1);
    }
  });

  it('burns hotter when loud than when silent', () => {
    const quiet = run(60, silent);
    const hot = run(60, loud);
    const energy = (f: typeof quiet) => f.heat.reduce((sum, v) => sum + v, 0) / f.heat.length;
    expect(energy(hot)).toBeGreaterThan(energy(quiet));
    expect(hot.energy).toBeGreaterThan(quiet.energy);
  });

  it('decays energy after the voice stops', () => {
    const field = createFireField({ cols: 32, rows: 12, maxEmbers: 16, seed: 3 });
    for (let i = 0; i < 40; i += 1) stepFire(field, 1 / 30, loud);
    const peak = field.energy;
    for (let i = 0; i < 40; i += 1) stepFire(field, 1 / 30, silent);
    expect(field.energy).toBeLessThan(peak);
  });

  it('never exceeds the ember budget', () => {
    const field = run(300, loud);
    expect(field.embers.length).toBe(24);
    expect(field.embers.filter((e) => e.alive).length).toBeLessThanOrEqual(24);
  });

  it('ignores a zero or invalid dt instead of producing NaN', () => {
    const field = createFireField({ cols: 16, rows: 8, seed: 1 });
    const before = field.time;
    stepFire(field, 0, loud);
    stepFire(field, Number.NaN, loud);
    expect(field.time).toBe(before);
    expect(field.heat.every((v) => Number.isFinite(v))).toBe(true);
  });
});

describe('colour', () => {
  it('stays in byte range and brightens with heat', () => {
    const cold = heatColor(0.05, 0.1);
    const hot = heatColor(0.95, 0.9);
    for (const channel of [...cold, ...hot]) {
      expect(channel).toBeGreaterThanOrEqual(0);
      expect(channel).toBeLessThanOrEqual(255);
    }
    expect(hot[1]).toBeGreaterThan(cold[1]);
  });

  it('clamps out-of-range input', () => {
    expect(heatAlpha(-1)).toBe(0);
    expect(heatAlpha(2)).toBe(1);
    expect(heatColor(Number.NaN, Number.NaN)).toEqual([92, 16, 4]);
  });
});

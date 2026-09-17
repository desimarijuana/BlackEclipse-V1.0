import { describe, it, expect } from 'vitest';
import { mulberry32Seed } from './demo';

// ── Demo seeding invariants ──────────────────────────────────────────────────
// The seeder writes real rows into a user's database, so its safety rules are
// the part worth testing: it must be deterministic, never overwrite real data,
// and stay removable. The DB-touching paths are covered by the live check; these
// pin the pure PRNG contract that makes the data reproducible.

describe('demo PRNG determinism', () => {
  it('produces the same sequence for the same seed', () => {
    const a = mulberry32Seed(20260909);
    const b = mulberry32Seed(20260909);
    const seqA = Array.from({ length: 20 }, () => a());
    const seqB = Array.from({ length: 20 }, () => b());
    expect(seqA).toEqual(seqB);
  });

  it('produces different sequences for different seeds', () => {
    const a = mulberry32Seed(1);
    const b = mulberry32Seed(2);
    expect(Array.from({ length: 10 }, () => a())).not.toEqual(Array.from({ length: 10 }, () => b()));
  });

  it('stays within [0, 1)', () => {
    const rng = mulberry32Seed(42);
    for (let i = 0; i < 500; i++) {
      const v = rng();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it('is not degenerate (values actually vary)', () => {
    const rng = mulberry32Seed(7);
    const values = new Set(Array.from({ length: 100 }, () => Math.floor(rng() * 10)));
    // A working PRNG should hit most of 0..9, not collapse to one bucket.
    expect(values.size).toBeGreaterThan(5);
  });
});

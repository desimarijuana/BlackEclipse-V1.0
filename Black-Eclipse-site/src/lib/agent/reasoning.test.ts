import { describe, expect, it } from 'vitest';
import {
  REASONING_LEVELS,
  REASONING_OPTIONS,
  EFFORT_STOPS,
  DEFAULT_EFFORT_INDEX,
  effortAt,
  effortIndex,
  isReasoningLevel,
  levelForOption,
} from './reasoning';

// The reasoning-effort vocabulary is shared by the Settings UI, the settings
// vault and the run front door; these lock the mapping so the stored value, the
// picker label and the runtime override cannot drift.

describe('reasoning effort ("model variant")', () => {
  it('offers Auto first, then the four runtime levels in ascending order', () => {
    expect(REASONING_OPTIONS[0].value).toBeUndefined();
    expect(REASONING_OPTIONS.slice(1).map((o) => o.value)).toEqual([...REASONING_LEVELS]);
  });

  it('maps every level to a distinct human label', () => {
    const labels = REASONING_OPTIONS.map((o) => o.label);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels).toContain('Auto');
    expect(labels).toContain('Minimal');
    expect(labels).toContain('Ultra');
  });

  it('accepts only the runtime levels and rejects everything else', () => {
    expect(isReasoningLevel('high')).toBe(true);
    expect(isReasoningLevel('very_high')).toBe(true);
    expect(isReasoningLevel('none')).toBe(false); // not offered per-run
    expect(isReasoningLevel('max')).toBe(false);
    expect(isReasoningLevel('ultra')).toBe(false); // UI word, not a runtime value
    expect(isReasoningLevel(undefined)).toBe(false);
  });

  it('omits the value for Auto so it is never persisted', () => {
    const auto = REASONING_OPTIONS.find((o) => o.label === 'Auto')!;
    expect(levelForOption(auto)).toBeUndefined();
  });
});

// The composer slider (EffortControl) reads the SAME vocabulary as Settings, and
// these lock the index↔level mapping so a drag can never land on the wrong stop.
describe('effort slider mapping', () => {
  it('exposes the same stops as the picker, with a caption and skin on each', () => {
    expect(EFFORT_STOPS).toBe(REASONING_OPTIONS);
    for (const option of EFFORT_STOPS) {
      expect(option.caption.length).toBeGreaterThan(0);
      expect(['muted', 'violet', 'aurora']).toContain(option.skin);
    }
  });

  it('rests the thumb on Auto (index 0) with no override', () => {
    expect(DEFAULT_EFFORT_INDEX).toBe(0);
    expect(effortIndex(undefined)).toBe(0);
    expect(effortIndex(null)).toBe(0);
  });

  it('maps every level to its own index and back', () => {
    for (const [i, option] of EFFORT_STOPS.entries()) {
      expect(effortIndex(option.value)).toBe(i);
      expect(effortAt(i).value).toBe(option.value);
    }
  });

  it('clamps an out-of-range index rather than inventing a stop', () => {
    expect(effortAt(-3).value).toBe(EFFORT_STOPS[0].value);
    expect(effortAt(999).value).toBe(EFFORT_STOPS[EFFORT_STOPS.length - 1].value);
  });

  it('marks only the top stop with the aurora skin', () => {
    const aurora = EFFORT_STOPS.filter((o) => o.skin === 'aurora');
    expect(aurora).toHaveLength(1);
    expect(aurora[0].value).toBe('very_high');
  });
});

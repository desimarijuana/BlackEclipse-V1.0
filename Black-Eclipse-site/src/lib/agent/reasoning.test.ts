import { describe, expect, it } from 'vitest';
import {
  REASONING_LEVELS,
  REASONING_OPTIONS,
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

import { describe, expect, it } from 'vitest';
import {
  BOTS_FONT_SCALE_MAX,
  BOTS_FONT_SCALE_MIN,
  DEFAULT_BOTS_APPEARANCE,
  normalizeBotsAppearance,
} from './appearance';

describe('normalizeBotsAppearance', () => {
  it('falls back to 100% for junk input', () => {
    expect(normalizeBotsAppearance(null)).toEqual(DEFAULT_BOTS_APPEARANCE);
    expect(normalizeBotsAppearance('large')).toEqual(DEFAULT_BOTS_APPEARANCE);
    expect(normalizeBotsAppearance({ fontScale: 'big' })).toEqual(DEFAULT_BOTS_APPEARANCE);
    expect(normalizeBotsAppearance({ fontScale: Number.NaN })).toEqual(DEFAULT_BOTS_APPEARANCE);
  });

  it('keeps a valid multiplier', () => {
    expect(normalizeBotsAppearance({ fontScale: 1.3 })).toEqual({ fontScale: 1.3 });
  });

  it('clamps to the supported range', () => {
    expect(normalizeBotsAppearance({ fontScale: 9 })).toEqual({ fontScale: BOTS_FONT_SCALE_MAX });
    expect(normalizeBotsAppearance({ fontScale: 0.1 })).toEqual({ fontScale: BOTS_FONT_SCALE_MIN });
  });
});

import { describe, expect, it } from 'vitest';
import {
  ALIGN_CLASS,
  ALIGN_TOKENS,
  GAP_CLASS,
  PAD_CLASS,
  RADIUS_CLASS,
  RADIUS_TOKENS,
  SPACE_TOKENS,
  TONE_SURFACE,
  TONE_TOKENS,
} from './tokens';

describe('design tokens are closed vocabularies with complete maps', () => {
  it('every spacing token maps to a gap and pad class', () => {
    expect(Object.keys(GAP_CLASS).sort()).toEqual([...SPACE_TOKENS].sort());
    expect(Object.keys(PAD_CLASS).sort()).toEqual([...SPACE_TOKENS].sort());
  });
  it('every radius token maps', () => {
    expect(Object.keys(RADIUS_CLASS).sort()).toEqual([...RADIUS_TOKENS].sort());
  });
  it('every tone maps to a surface', () => {
    expect(Object.keys(TONE_SURFACE).sort()).toEqual([...TONE_TOKENS].sort());
  });
  it('every align token maps', () => {
    expect(Object.keys(ALIGN_CLASS).sort()).toEqual([...ALIGN_TOKENS].sort());
  });
  it('neutral tone contributes no surface class (the bare default)', () => {
    expect(TONE_SURFACE.neutral).toBe('');
  });
});

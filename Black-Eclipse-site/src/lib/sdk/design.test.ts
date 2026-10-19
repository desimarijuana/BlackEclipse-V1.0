import { describe, expect, it } from 'vitest';
import { DEFAULT_ECLIPSE_THEME } from '@/lib/theme/tokens';
import { baseDesignTheme, mergeThemePatch } from './design';

describe('Eclipse SDK design patch', () => {
  it('merges a partial color group without dropping the other tokens', () => {
    const next = mergeThemePatch(DEFAULT_ECLIPSE_THEME, {
      colors: { primary: '#77edfd' },
    });
    expect(next.colors.primary).toBe('#77edfd');
    expect(next.colors.bearish).toBe(DEFAULT_ECLIPSE_THEME.colors.bearish);
    expect(next.colors.background).toBe(DEFAULT_ECLIPSE_THEME.colors.background);
  });

  it('merges top-level and nested controls together', () => {
    const next = mergeThemePatch(DEFAULT_ECLIPSE_THEME, {
      radius: 1.1,
      glass: { blur: 30 },
      sidebar: { opacity: 0.6 },
      scheme: 'light',
    });
    expect(next.radius).toBe(1.1);
    expect(next.glass.blur).toBe(30);
    expect(next.glass.opacity).toBe(DEFAULT_ECLIPSE_THEME.glass.opacity);
    expect(next.sidebar.opacity).toBe(0.6);
    expect(next.scheme).toBe('light');
  });

  it('ignores unknown keys and invalid values instead of corrupting the theme', () => {
    const next = mergeThemePatch(DEFAULT_ECLIPSE_THEME, {
      nope: 'ignored',
      colors: { primary: 'not-a-color' },
    });
    expect(next.colors.primary).toBe(DEFAULT_ECLIPSE_THEME.colors.primary);
    expect('nope' in next).toBe(false);
  });

  it('falls back to the shipped default when no server theme exists', () => {
    expect(baseDesignTheme(null)).toEqual(DEFAULT_ECLIPSE_THEME);
  });
});

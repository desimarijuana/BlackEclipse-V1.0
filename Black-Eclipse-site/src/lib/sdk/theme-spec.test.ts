import { describe, expect, it } from 'vitest';
import { DEFAULT_ECLIPSE_THEME } from '@/lib/theme/tokens';
import { ThemeSpecError, buildThemeFromSpec, normalizeThemeSpec, themeToSpec } from './theme-spec';

describe('ThemeSpec', () => {
  it('builds a dark brand theme from a closed spec', () => {
    const theme = buildThemeFromSpec({
      basePreset: 'eclipse',
      brand: '#ff2bd6',
      scheme: 'dark',
      density: 'compact',
      radius: 0.25,
      shadow: 'dramatic',
      glass: { blur: 28, opacity: 0.4 },
    });
    expect(theme.colors.primary).toBe('#ff2bd6');
    expect(theme.colors.bullish).toBe('#ff2bd6');
    expect(theme.scheme).toBe('dark');
    expect(theme.density).toBe('compact');
    expect(theme.radius).toBe(0.25);
    expect(theme.shadow).toBe('dramatic');
    expect(theme.glass.blur).toBe(28);
    expect(theme.glass.opacity).toBe(0.4);
  });

  it('switches to a light base when the light scheme is requested', () => {
    const theme = buildThemeFromSpec({ brand: '#047857', scheme: 'light' });
    expect(theme.scheme).toBe('light');
    expect(theme.colors.background).not.toBe(DEFAULT_ECLIPSE_THEME.colors.background);
  });

  it('applies app identity, fonts and surfaces', () => {
    const theme = buildThemeFromSpec({
      appName: 'Neon Desk',
      logoText: 'ND',
      logoUrl: 'data:image/svg+xml,%3Csvg%3E%3C/svg%3E',
      fontUi: 'Inter, sans-serif',
      fontHeading: 'Georgia, serif',
      fontMono: 'Consolas, monospace',
      background: 'grid',
      sidebar: { tint: '#101820', opacity: 0.8, blur: 26 },
    });
    expect(theme.appName).toBe('Neon Desk');
    expect(theme.logoText).toBe('ND');
    expect(theme.logoUrl).toContain('data:image/svg+xml');
    expect(theme.fontUi).toBe('Inter, sans-serif');
    expect(theme.fontHeading).toBe('Georgia, serif');
    expect(theme.fontMono).toBe('Consolas, monospace');
    expect(theme.background).toBe('grid');
    expect(theme.sidebar).toEqual({ tint: '#101820', opacity: 0.8, blur: 26 });
  });

  it('projects a live theme onto the closed spec', () => {
    const spec = themeToSpec({
      ...DEFAULT_ECLIPSE_THEME,
      appName: 'Neon Desk',
      logoText: 'ND',
      fontUi: 'Inter, sans-serif',
      colors: { ...DEFAULT_ECLIPSE_THEME.colors, primary: '#ff2bd6' },
      density: 'compact',
      radius: 0.25,
      shadow: 'dramatic',
      background: 'grid',
      glass: { ...DEFAULT_ECLIPSE_THEME.glass, blur: 28, opacity: 0.4 },
    }, 'Neon');
    expect(spec.name).toBe('Neon');
    expect(spec.brand).toBe('#ff2bd6');
    expect(spec.appName).toBe('Neon Desk');
    expect(spec.logoText).toBe('ND');
    expect(spec.fontUi).toBe('Inter, sans-serif');
    expect(spec.density).toBe('compact');
    expect(spec.radius).toBe(0.25);
    expect(spec.shadow).toBe('dramatic');
    expect(spec.background).toBe('grid');
    expect(spec.glass?.blur).toBe(28);
    const rebuilt = buildThemeFromSpec(spec);
    expect(rebuilt.colors.primary).toBe('#ff2bd6');
    expect(rebuilt.appName).toBe('Neon Desk');
  });

  it('rejects unknown fields and invalid values', () => {
    expect(() => normalizeThemeSpec({ colors: { primary: '#fff' } })).toThrow(ThemeSpecError);
    expect(() => normalizeThemeSpec({ brand: 'not-a-color' })).toThrow(ThemeSpecError);
    expect(() => normalizeThemeSpec({ scheme: 'sepia' })).toThrow(ThemeSpecError);
    expect(() => normalizeThemeSpec({ logoUrl: 'javascript:alert(1)' })).toThrow(ThemeSpecError);
    expect(() => normalizeThemeSpec({ radius: 4 })).toThrow(ThemeSpecError);
  });
});

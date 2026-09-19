import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ECLIPSE_THEME,
  STRUCTURAL_THEME_VARS,
  THEME_PRESETS,
  buildFaviconDataUrl,
  normalizeHex,
  normalizeTheme,
  themeCssVars,
  themeFromBrandColor,
  themeMatchesPreset,
  themePresetId,
} from './tokens';

describe('normalizeTheme', () => {
  it('returns the default for junk input', () => {
    expect(normalizeTheme(null)).toEqual(DEFAULT_ECLIPSE_THEME);
    expect(normalizeTheme('nope')).toEqual(DEFAULT_ECLIPSE_THEME);
    expect(normalizeTheme(42)).toEqual(DEFAULT_ECLIPSE_THEME);
  });

  it('keeps valid fields and repairs invalid colors', () => {
    const t = normalizeTheme({
      appName: 'Acme',
      colors: { primary: 'not-a-color', bullish: '#ABC' },
      radius: 99,
    });
    expect(t.appName).toBe('Acme');
    expect(t.colors.primary).toBe(DEFAULT_ECLIPSE_THEME.colors.primary);
    expect(t.colors.bullish).toBe('#aabbcc');
    expect(t.radius).toBe(1.6);
  });

  it('clamps density to known values', () => {
    expect(normalizeTheme({ density: 'spacious' }).density).toBe('spacious');
    expect(normalizeTheme({ density: 'weird' }).density).toBe('comfortable');
  });
});

describe('presets', () => {
  it('every preset is self-consistent after normalization', () => {
    for (const p of THEME_PRESETS) {
      expect(normalizeTheme(p.theme)).toEqual(p.theme);
    }
  });

  it('identifies the default preset', () => {
    expect(themePresetId(DEFAULT_ECLIPSE_THEME)).toBe('eclipse');
    expect(themeMatchesPreset(DEFAULT_ECLIPSE_THEME, THEME_PRESETS[0].theme)).toBe(true);
  });

  it('reports custom themes as unmatched', () => {
    const custom = normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, primary: '#123456' } });
    expect(themePresetId(custom)).toBeNull();
  });
});

describe('themeCssVars', () => {
  it('emits the core brand + market tokens', () => {
    const vars = themeCssVars(DEFAULT_ECLIPSE_THEME);
    expect(vars['--primary']).toBe('#7aff78');
    expect(vars['--bullish']).toBe('#7aff78');
    expect(vars['--bearish']).toBe('#ff3e3e');
    expect(vars['--brand-rgb']).toBe('122 255 120');
    expect(vars['--radius']).toBe('0.6rem');
  });

  it('marks typography/shape as structural (mode-independent)', () => {
    for (const name of ['--font-sans', '--font-mono', '--radius', '--spacing', '--font-scale', '--logo-scale']) {
      expect(STRUCTURAL_THEME_VARS.has(name)).toBe(true);
    }
    expect(STRUCTURAL_THEME_VARS.has('--primary')).toBe(false);
  });

  it('emits font + logo scale tokens', () => {
    const vars = themeCssVars(normalizeTheme({ fontScale: 1.2, logoScale: 1.4 }));
    expect(vars['--font-scale']).toBe('1.2');
    expect(vars['--logo-scale']).toBe('1.4');
  });
});

describe('themeFromBrandColor', () => {
  it('derives primary/accent/bullish from one brand color', () => {
    const t = themeFromBrandColor('#ff6600');
    expect(t.colors.primary).toBe('#ff6600');
    expect(t.colors.bullish).toBe('#ff6600');
    expect(t.colors.accent).not.toBe('#ff6600');
    expect(t.colors.bearish).toBe(DEFAULT_ECLIPSE_THEME.colors.bearish);
  });

  it('honours explicit overrides', () => {
    const t = themeFromBrandColor('#1e90ff', DEFAULT_ECLIPSE_THEME, { bearish: '#ff0055' });
    expect(t.colors.bearish).toBe('#ff0055');
  });

  it('clamps out-of-range font/logo scales', () => {
    const t = normalizeTheme({ fontScale: 9, logoScale: 0.1 });
    expect(t.fontScale).toBe(1.4);
    expect(t.logoScale).toBe(0.6);
  });
});

describe('buildFaviconDataUrl', () => {
  it('produces an inline SVG favicon using the monogram', () => {
    const url = buildFaviconDataUrl({ ...DEFAULT_ECLIPSE_THEME, logoText: 'BE' });
    expect(url.startsWith('data:image/svg+xml,')).toBe(true);
    expect(decodeURIComponent(url)).toContain('>BE<');
  });
});

describe('normalizeHex', () => {
  it('expands shorthand and validates', () => {
    expect(normalizeHex('#abc')).toBe('#aabbcc');
    expect(normalizeHex('#AABBCC')).toBe('#aabbcc');
    expect(normalizeHex('red')).toBeNull();
  });
});

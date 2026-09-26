import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ECLIPSE_THEME,
  STRUCTURAL_THEME_VARS,
  THEME_PRESETS,
  buildFaviconDataUrl,
  deriveThemeColors,
  hexToRgb,
  normalizeHex,
  normalizeTheme,
  pageBackgroundImage,
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

describe('deriveThemeColors', () => {
  it('derives neutrals from the core colors when unpinned', () => {
    const d = deriveThemeColors(DEFAULT_ECLIPSE_THEME.colors);
    expect(d.secondary).toBeDefined();
    expect(d.muted).toBeDefined();
    expect(d.mutedForeground).toBeDefined();
    expect(d.accentSurface).toBeDefined();
    expect(d.primary).toBe(DEFAULT_ECLIPSE_THEME.colors.primary);
  });

  it('honours explicit overrides for derived tokens', () => {
    const d = deriveThemeColors({ ...DEFAULT_ECLIPSE_THEME.colors, muted: '#101010' });
    expect(d.muted).toBe('#101010');
  });

  it('drops an invalid optional override without failing', () => {
    const t = normalizeTheme({ colors: { muted: 'not-a-color' } });
    expect(t.colors.muted).toBeUndefined();
    const d = deriveThemeColors(t.colors);
    expect(d.muted).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('lets a pinned derived token override the computed CSS value', () => {
    const t = normalizeTheme({ colors: { mutedForeground: '#ff00ff' } });
    expect(themeCssVars(t)['--muted-foreground']).toBe('#ff00ff');
  });

  it('keeps the default theme equal after normalization (optional tokens omitted)', () => {
    const t = normalizeTheme(DEFAULT_ECLIPSE_THEME);
    expect(t).toEqual(DEFAULT_ECLIPSE_THEME);
    expect(t.colors.secondary).toBeUndefined();
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

describe('glass, shadow and background', () => {
  it('defaults to the shipped frosted recipe', () => {
    const t = normalizeTheme({});
    expect(t.glass).toEqual(DEFAULT_ECLIPSE_THEME.glass);
    expect(t.shadow).toBe('soft');
    expect(t.background).toBe('solid');
  });

  it('clamps glass blur and opacity', () => {
    const t = normalizeTheme({ glass: { blur: 999, opacity: 5, tint: 'nope' } });
    expect(t.glass.blur).toBe(48);
    expect(t.glass.opacity).toBe(1);
    expect(t.glass.tint).toBe(DEFAULT_ECLIPSE_THEME.glass.tint);
  });

  it('rejects unknown shadow/background values', () => {
    const t = normalizeTheme({ shadow: 'huge', background: 'plaid' });
    expect(t.shadow).toBe('soft');
    expect(t.background).toBe('solid');
  });

  it('emits glass tokens, disabling blur when off', () => {
    const on = themeCssVars(DEFAULT_ECLIPSE_THEME);
    expect(on['--glass-blur']).toBe('18px');
    expect(on['--glass-opacity']).toBe('0.55');
    expect(on['--glass-enabled']).toBe('1');
    const off = themeCssVars(normalizeTheme({ glass: { enabled: false } }));
    expect(off['--glass-blur']).toBe('0px');
    expect(off['--glass-enabled']).toBe('0');
  });

  it('builds a tinted page background image per treatment', () => {
    expect(pageBackgroundImage('solid', '#7aff78')).toBe('none');
    expect(pageBackgroundImage('gradient', '#7aff78')).toContain('radial-gradient');
    expect(pageBackgroundImage('grid', '#7aff78')).toContain('linear-gradient');
  });
});

describe('sidebar surface', () => {
  it('defaults to a grey, distinct-from-black rail', () => {
    const t = normalizeTheme({});
    expect(t.sidebar).toEqual(DEFAULT_ECLIPSE_THEME.sidebar);
    expect(t.sidebar.tint).not.toBe(t.colors.background);
  });

  it('emits dedicated sidebar tokens', () => {
    const vars = themeCssVars(DEFAULT_ECLIPSE_THEME);
    expect(vars['--sidebar-rgb']).toBe('26 26 28');
    expect(vars['--sidebar-opacity']).toBe('0.9');
    expect(vars['--sidebar-blur']).toBe('20px');
    expect(vars['--sidebar']).toBe('#1a1a1c');
    expect(STRUCTURAL_THEME_VARS.has('--sidebar-rgb')).toBe(true);
  });

  it('clamps sidebar values and collapses blur when glass is off', () => {
    const t = normalizeTheme({ sidebar: { tint: 'nope', opacity: 5, blur: 999 } });
    expect(t.sidebar.tint).toBe(DEFAULT_ECLIPSE_THEME.sidebar.tint);
    expect(t.sidebar.opacity).toBe(1);
    expect(t.sidebar.blur).toBe(48);
    const off = themeCssVars(normalizeTheme({ glass: { enabled: false } }));
    expect(off['--sidebar-blur']).toBe('0px');
    expect(off['--sidebar-opacity']).toBe('0.96');
  });

  it('keeps a per-preset sidebar when a preset is normalized', () => {
    const black = THEME_PRESETS.find((p) => p.id === 'eclipse')!.theme;
    expect(normalizeTheme(black).sidebar).toEqual(DEFAULT_ECLIPSE_THEME.sidebar);
  });

  it('ships a blue-tinted sidebar on the blue themes', () => {
    for (const id of ['ocean', 'blueprint', 'crystal', 'midnight']) {
      const theme = THEME_PRESETS.find((p) => p.id === id)!.theme;
      const { r, b } = hexToRgb(theme.sidebar.tint);
      expect(b).toBeGreaterThan(r);
      expect(theme.sidebar.tint).not.toBe(DEFAULT_ECLIPSE_THEME.sidebar.tint);
      expect(normalizeTheme(theme).sidebar).toEqual(theme.sidebar);
    }
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

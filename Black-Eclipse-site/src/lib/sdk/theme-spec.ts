import {
  DEFAULT_ECLIPSE_THEME,
  THEME_PRESETS,
  normalizeHex,
  normalizeTheme,
  themeFromBrandColor,
  type EclipseTheme,
  type ThemeBackground,
  type ThemeDensity,
  type ThemeShadow,
} from '@/lib/theme/tokens';

export interface ThemeSpec {
  name?: string;
  basePreset?: string;
  brand?: string;
  scheme?: 'dark' | 'light';
  density?: ThemeDensity;
  radius?: number;
  shadow?: ThemeShadow;
  background?: ThemeBackground;
  glass?: {
    enabled?: boolean;
    blur?: number;
    opacity?: number;
    tint?: string;
  };
  sidebar?: {
    tint?: string;
    opacity?: number;
    blur?: number;
  };
  fontUi?: string;
  fontHeading?: string;
  fontMono?: string;
  appName?: string;
  logoText?: string;
  logoUrl?: string;
}

export class ThemeSpecError extends Error {
  issues: string[];

  constructor(issues: string[]) {
    super(issues[0] || 'invalid theme specification');
    this.name = 'ThemeSpecError';
    this.issues = issues;
  }
}

const SPEC_KEYS = new Set([
  'name', 'basePreset', 'brand', 'scheme', 'density', 'radius', 'shadow',
  'background', 'glass', 'sidebar', 'fontUi', 'fontHeading', 'fontMono',
  'appName', 'logoText', 'logoUrl',
]);

const DENSITIES: readonly ThemeDensity[] = ['compact', 'comfortable', 'spacious'];
const SHADOWS: readonly ThemeShadow[] = ['none', 'soft', 'medium', 'dramatic'];
const BACKGROUNDS: readonly ThemeBackground[] = ['solid', 'gradient', 'grid'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function text(value: unknown, max: number): string | undefined {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, max) : undefined;
}

function logo(value: unknown, issues: string[]): string | undefined {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value !== 'string') {
    issues.push('logoUrl must be a string');
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) return '';
  if (trimmed.length > 200_000) {
    issues.push('logoUrl exceeds the 200 kB limit');
    return undefined;
  }
  if (!/^(https?:\/\/|data:image\/(?:png|jpeg|webp|gif|svg\+xml)[;,])/i.test(trimmed)) {
    issues.push('logoUrl must be an http(s) URL or a data:image URL');
    return undefined;
  }
  return trimmed;
}

export function normalizeThemeSpec(raw: unknown): ThemeSpec {
  if (!isRecord(raw)) throw new ThemeSpecError(['theme spec must be an object']);
  const issues: string[] = [];
  for (const key of Object.keys(raw)) {
    if (!SPEC_KEYS.has(key)) issues.push(`unknown theme field "${key}"`);
  }

  const spec: ThemeSpec = {};

  const name = text(raw.name, 80);
  if (name) spec.name = name;
  const basePreset = text(raw.basePreset, 60);
  if (basePreset) {
    if (!THEME_PRESETS.some((preset) => preset.id === basePreset)) {
      issues.push(`unknown basePreset "${basePreset}"`);
    } else {
      spec.basePreset = basePreset;
    }
  }

  if (raw.brand !== undefined) {
    const brand = normalizeHex(raw.brand);
    if (!brand) issues.push('brand must be a hex color such as #ff2bd6');
    else spec.brand = brand;
  }
  if (raw.scheme !== undefined) {
    if (raw.scheme !== 'dark' && raw.scheme !== 'light') issues.push('scheme must be "dark" or "light"');
    else spec.scheme = raw.scheme;
  }
  if (raw.density !== undefined) {
    if (!DENSITIES.includes(raw.density as ThemeDensity)) issues.push('density must be compact, comfortable or spacious');
    else spec.density = raw.density as ThemeDensity;
  }
  if (raw.radius !== undefined) {
    if (typeof raw.radius !== 'number' || !Number.isFinite(raw.radius) || raw.radius < 0 || raw.radius > 1.6) {
      issues.push('radius must be a number between 0 and 1.6');
    } else {
      spec.radius = raw.radius;
    }
  }
  if (raw.shadow !== undefined) {
    if (!SHADOWS.includes(raw.shadow as ThemeShadow)) issues.push('shadow must be none, soft, medium or dramatic');
    else spec.shadow = raw.shadow as ThemeShadow;
  }
  if (raw.background !== undefined) {
    if (!BACKGROUNDS.includes(raw.background as ThemeBackground)) issues.push('background must be solid, gradient or grid');
    else spec.background = raw.background as ThemeBackground;
  }

  if (raw.glass !== undefined) {
    if (!isRecord(raw.glass)) {
      issues.push('glass must be an object');
    } else {
      for (const key of Object.keys(raw.glass)) {
        if (!['enabled', 'blur', 'opacity', 'tint'].includes(key)) issues.push(`unknown glass field "${key}"`);
      }
      const glass: NonNullable<ThemeSpec['glass']> = {};
      if (raw.glass.enabled !== undefined) {
        if (typeof raw.glass.enabled !== 'boolean') issues.push('glass.enabled must be a boolean');
        else glass.enabled = raw.glass.enabled;
      }
      if (raw.glass.blur !== undefined) {
        if (typeof raw.glass.blur !== 'number' || !Number.isFinite(raw.glass.blur) || raw.glass.blur < 0 || raw.glass.blur > 60) {
          issues.push('glass.blur must be between 0 and 60');
        } else glass.blur = raw.glass.blur;
      }
      if (raw.glass.opacity !== undefined) {
        if (typeof raw.glass.opacity !== 'number' || !Number.isFinite(raw.glass.opacity) || raw.glass.opacity < 0 || raw.glass.opacity > 1) {
          issues.push('glass.opacity must be between 0 and 1');
        } else glass.opacity = raw.glass.opacity;
      }
      if (raw.glass.tint !== undefined) {
        const tint = normalizeHex(raw.glass.tint);
        if (!tint) issues.push('glass.tint must be a hex color');
        else glass.tint = tint;
      }
      if (Object.keys(glass).length) spec.glass = glass;
    }
  }

  if (raw.sidebar !== undefined) {
    if (!isRecord(raw.sidebar)) {
      issues.push('sidebar must be an object');
    } else {
      for (const key of Object.keys(raw.sidebar)) {
        if (!['tint', 'opacity', 'blur'].includes(key)) issues.push(`unknown sidebar field "${key}"`);
      }
      const sidebar: NonNullable<ThemeSpec['sidebar']> = {};
      if (raw.sidebar.tint !== undefined) {
        const tint = normalizeHex(raw.sidebar.tint);
        if (!tint) issues.push('sidebar.tint must be a hex color');
        else sidebar.tint = tint;
      }
      if (raw.sidebar.opacity !== undefined) {
        if (typeof raw.sidebar.opacity !== 'number' || !Number.isFinite(raw.sidebar.opacity) || raw.sidebar.opacity < 0 || raw.sidebar.opacity > 1) {
          issues.push('sidebar.opacity must be between 0 and 1');
        } else sidebar.opacity = raw.sidebar.opacity;
      }
      if (raw.sidebar.blur !== undefined) {
        if (typeof raw.sidebar.blur !== 'number' || !Number.isFinite(raw.sidebar.blur) || raw.sidebar.blur < 0 || raw.sidebar.blur > 60) {
          issues.push('sidebar.blur must be between 0 and 60');
        } else sidebar.blur = raw.sidebar.blur;
      }
      if (Object.keys(sidebar).length) spec.sidebar = sidebar;
    }
  }

  const fontUi = text(raw.fontUi, 240);
  if (fontUi) spec.fontUi = fontUi;
  const fontHeading = text(raw.fontHeading, 240);
  if (fontHeading) spec.fontHeading = fontHeading;
  const fontMono = text(raw.fontMono, 240);
  if (fontMono) spec.fontMono = fontMono;
  const appName = text(raw.appName, 80);
  if (appName) spec.appName = appName;
  const logoText = text(raw.logoText, 8);
  if (logoText) spec.logoText = logoText;
  const logoUrl = logo(raw.logoUrl, issues);
  if (logoUrl !== undefined) spec.logoUrl = logoUrl;

  if (issues.length) throw new ThemeSpecError(issues);
  return spec;
}

export function buildThemeFromSpec(raw: unknown): EclipseTheme {
  const spec = normalizeThemeSpec(raw);
  const preset = spec.basePreset
    ? THEME_PRESETS.find((candidate) => candidate.id === spec.basePreset)
    : undefined;
  let base = preset?.theme ?? DEFAULT_ECLIPSE_THEME;

  if (spec.scheme && base.scheme !== spec.scheme) {
    const sameScheme = THEME_PRESETS.find((candidate) => candidate.theme.scheme === spec.scheme);
    if (sameScheme) base = sameScheme.theme;
  }
  if (spec.brand) base = themeFromBrandColor(spec.brand, base);

  const next: Record<string, unknown> = { ...base };
  if (spec.appName !== undefined) next.appName = spec.appName;
  if (spec.logoText !== undefined) next.logoText = spec.logoText;
  if (spec.logoUrl !== undefined) next.logoUrl = spec.logoUrl;
  if (spec.fontUi !== undefined) next.fontUi = spec.fontUi;
  if (spec.fontHeading !== undefined) next.fontHeading = spec.fontHeading;
  if (spec.fontMono !== undefined) next.fontMono = spec.fontMono;
  if (spec.density !== undefined) next.density = spec.density;
  if (spec.radius !== undefined) next.radius = spec.radius;
  if (spec.shadow !== undefined) next.shadow = spec.shadow;
  if (spec.background !== undefined) next.background = spec.background;
  if (spec.scheme !== undefined) next.scheme = spec.scheme;
  if (spec.glass) next.glass = { ...base.glass, ...spec.glass };
  if (spec.sidebar) next.sidebar = { ...base.sidebar, ...spec.sidebar };

  return normalizeTheme(next);
}

export function themeSpecPresetName(raw: unknown): string | undefined {
  return normalizeThemeSpec(raw).name;
}

/**
 * Project a live `EclipseTheme` onto the closed `ThemeSpec`. This is the inverse
 * of `buildThemeFromSpec` for the fields the spec owns; presentation extras the
 * spec does not model (favicon, glow, animations, fontScale, chart palette)
 * stay local to the browser.
 */
export function themeToSpec(theme: EclipseTheme, name?: string): ThemeSpec {
  const spec: ThemeSpec = {
    brand: theme.colors.primary,
    scheme: theme.scheme,
    density: theme.density,
    radius: theme.radius,
    shadow: theme.shadow,
    background: theme.background,
    glass: {
      enabled: theme.glass.enabled,
      blur: theme.glass.blur,
      opacity: theme.glass.opacity,
      tint: theme.glass.tint,
    },
    sidebar: {
      tint: theme.sidebar.tint,
      opacity: theme.sidebar.opacity,
      blur: theme.sidebar.blur,
    },
    fontUi: theme.fontUi,
    fontHeading: theme.fontHeading,
    fontMono: theme.fontMono,
    appName: theme.appName,
    logoText: theme.logoText,
  };
  if (theme.logoUrl) spec.logoUrl = theme.logoUrl;
  if (name) spec.name = name;
  return spec;
}

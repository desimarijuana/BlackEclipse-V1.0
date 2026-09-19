// ── Eclipse Theme — centralized design tokens ────────────────────────────────
// The single source of truth for user customization (Settings › Customization).
// A theme is a plain, serializable object; `themeCssVars()` turns it into CSS
// custom properties applied to <html>, so every component that already reads
// `--primary`, `--background`, `--font-mono`, `--radius`, … recolors itself
// with no component-specific hacks.
//
// This module is pure (no React, no DOM) so it is safe to unit test and to
// import from server code. The live store lives in `store.ts`.

export type ThemeDensity = 'compact' | 'comfortable' | 'spacious';

export interface ThemeColors {
  /** Brand / interactive accent (buttons, highlights, chart line 1). */
  primary: string;
  /** Secondary brand tint (gradients, glows, hover). */
  accent: string;
  /** Page background. */
  background: string;
  /** Card / panel / popover surface. */
  surface: string;
  /** Hairline borders and input outlines. */
  border: string;
  /** Primary text color. */
  text: string;
  /** Positive market color (candles up, gains, bullish). */
  bullish: string;
  /** Negative market color (candles down, losses, bearish). */
  bearish: string;
}

/**
 * Shipped brand assets (in `public/branding/`). These are the default logo and
 * favicon; a user-uploaded `logoUrl` / `faviconUrl` in Settings › Customization
 * takes precedence over them.
 */
export const BRAND_MARK_SRC = '/branding/FAVICON.svg';
export const BRAND_WORDMARK_SRC = '/branding/LOGO-WORDMARK.svg';

export interface EclipseTheme {
  /** App / workspace name shown in the sidebar, header and page title. */
  appName: string;
  /** Monogram letter(s) used when no logo image is set. */
  logoText: string;
  /** Logo image (data URL or remote URL). Empty means use the icon/monogram. */
  logoUrl: string;
  /** Favicon image (data URL or remote URL). Empty means derive from logo. */
  faviconUrl: string;
  /** CSS font-family stacks. */
  fontUi: string;
  fontHeading: string;
  fontMono: string;
  colors: ThemeColors;
  /** Base corner radius in rem. */
  radius: number;
  density: ThemeDensity;
  /** Global text scale (multiplies the root font size). 1 = shipped default. */
  fontScale: number;
  /** Sidebar / header logo scale. 1 = shipped default. */
  logoScale: number;
  /** Ambient Aurora glow on/off. */
  glow: boolean;
  /** Interface animations on/off. */
  animations: boolean;
}

export const DEFAULT_ECLIPSE_THEME: EclipseTheme = {
  appName: 'BlackEclipse',
  logoText: '',
  logoUrl: '',
  faviconUrl: '',
  fontUi: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontHeading: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontMono: '"JetBrains Mono", "IBM Plex Mono", "SF Mono", Consolas, monospace',
  colors: {
    primary: '#7aff78',
    accent: '#34d399',
    background: '#000000',
    surface: '#0f0f0f',
    border: '#2a2a2e',
    text: '#f4f4f5',
    bullish: '#7aff78',
    bearish: '#ff3e3e',
  },
  radius: 0.6,
  density: 'comfortable',
  fontScale: 1,
  logoScale: 1,
  glow: true,
  animations: true,
};

// ── Font choices (curated stacks — no external font dependency) ──────────────

export interface FontOption {
  label: string;
  value: string;
}

export const UI_FONT_OPTIONS: FontOption[] = [
  { label: 'System', value: DEFAULT_ECLIPSE_THEME.fontUi },
  { label: 'Inter', value: 'Inter, "Segoe UI", system-ui, -apple-system, sans-serif' },
  { label: 'Helvetica', value: '"Helvetica Neue", Helvetica, Arial, sans-serif' },
  { label: 'Verdana', value: 'Verdana, Geneva, Tahoma, sans-serif' },
  { label: 'Georgia', value: 'Georgia, "Times New Roman", Times, serif' },
];

export const HEADING_FONT_OPTIONS: FontOption[] = [
  { label: 'System', value: DEFAULT_ECLIPSE_THEME.fontHeading },
  { label: 'Georgia (Serif)', value: 'Georgia, "Times New Roman", Times, serif' },
  { label: 'Palatino', value: '"Palatino Linotype", "Book Antiqua", Palatino, serif' },
  { label: 'Inter', value: 'Inter, "Segoe UI", system-ui, -apple-system, sans-serif' },
  { label: 'Trebuchet', value: '"Trebuchet MS", "Lucida Grande", Tahoma, sans-serif' },
];

export const MONO_FONT_OPTIONS: FontOption[] = [
  { label: 'JetBrains Mono', value: DEFAULT_ECLIPSE_THEME.fontMono },
  { label: 'Consolas', value: 'Consolas, "Courier New", monospace' },
  { label: 'Fira Code', value: '"Fira Code", "Cascadia Code", Consolas, monospace' },
  { label: 'Courier New', value: '"Courier New", Courier, monospace' },
  { label: 'SF Mono', value: '"SF Mono", "SFMono-Regular", Menlo, Monaco, monospace' },
];

export const DENSITY_OPTIONS: { id: ThemeDensity; label: string; hint: string }[] = [
  { id: 'compact', label: 'Compact', hint: 'Tighter spacing, more on screen' },
  { id: 'comfortable', label: 'Comfortable', hint: 'Balanced default' },
  { id: 'spacious', label: 'Spacious', hint: 'Roomier controls and gaps' },
];

// ── Presets ──────────────────────────────────────────────────────────────────

export interface ThemePreset {
  id: string;
  label: string;
  description: string;
  theme: EclipseTheme;
}

function preset(
  id: string,
  label: string,
  description: string,
  colors: Partial<ThemeColors>,
  extra?: Partial<EclipseTheme>,
): ThemePreset {
  return {
    id,
    label,
    description,
    theme: {
      ...DEFAULT_ECLIPSE_THEME,
      ...extra,
      colors: { ...DEFAULT_ECLIPSE_THEME.colors, ...colors },
    },
  };
}

/** Shipped Eclipse-family looks. The first is the brand default. */
/**
 * Neutral backgrounds shipped with the brand-color generator when the user
 * asks to derive a full theme from a single brand color (ServiceNow-style).
 */
export const BRAND_GENERATOR_BACKGROUND = '#000000';
export const BRAND_GENERATOR_SURFACE = '#0f0f0f';

export const THEME_PRESETS: ThemePreset[] = [
  { id: 'eclipse', label: 'Eclipse', description: 'The default green-on-black terminal.', theme: DEFAULT_ECLIPSE_THEME },
  preset('midnight', 'Midnight', 'Cool indigo accent on deep navy.',
    { primary: '#818cf8', accent: '#6366f1', background: '#05060f', surface: '#0d1020', border: '#26304a', text: '#e6e8f2', bullish: '#818cf8', bearish: '#fb7185' }),
  preset('matrix', 'Matrix', 'Phosphor-green terminal, minimal red.',
    { primary: '#00ff41', accent: '#22c55e', background: '#000400', surface: '#05130a', border: '#12351f', text: '#d7ffe4', bullish: '#00ff41', bearish: '#ff3b3b' }),
  preset('ocean', 'Ocean', 'Cold cyan brand with a coral bearish shift.',
    { primary: '#38bdf8', accent: '#22d3ee', background: '#02090f', surface: '#0a1622', border: '#1d3247', text: '#e2f3fb', bullish: '#38bdf8', bearish: '#fb7185' }),
  preset('solar', 'Solar', 'Warm amber brand on charcoal.',
    { primary: '#fbbf24', accent: '#f59e0b', background: '#0c0803', surface: '#17110a', border: '#3a2c14', text: '#fdf4e3', bullish: '#fbbf24', bearish: '#ff5c5c' }),
  preset('crimson', 'Crimson', 'Rose-forward brand for a warmer terminal.',
    { primary: '#fb7185', accent: '#f43f5e', background: '#0d0508', surface: '#190c12', border: '#3f1622', text: '#fdeef2', bullish: '#fb7185', bearish: '#ff2d55' }),
  preset('mono', 'Mono', 'Neutral greyscale with a white brand.',
    { primary: '#e5e5e5', accent: '#a3a3a3', background: '#000000', surface: '#0f0f0f', border: '#2a2a2e', text: '#fafafa', bullish: '#e5e5e5', bearish: '#737373' }),
];

// ── Color helpers ────────────────────────────────────────────────────────────

const HEX_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

export function isValidHex(value: unknown): value is string {
  return typeof value === 'string' && HEX_RE.test(value.trim());
}

/** Normalize a hex string to lowercase `#rrggbb`; null when invalid. */
export function normalizeHex(raw: unknown): string | null {
  if (!isValidHex(raw)) return null;
  let v = raw.trim().toLowerCase();
  if (v.length === 4) v = `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}`;
  return v;
}

export function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const v = normalizeHex(hex) ?? '#000000';
  return {
    r: parseInt(v.slice(1, 3), 16),
    g: parseInt(v.slice(3, 5), 16),
    b: parseInt(v.slice(5, 7), 16),
  };
}

/** "r g b" — the space-separated form used by modern rgb()/color-mix usage. */
export function hexToRgbTriplet(hex: string): string {
  const { r, g, b } = hexToRgb(hex);
  return `${r} ${g} ${b}`;
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/** Linear mix of two hex colors; `t` is the weight of `a` (0 = all b). */
export function mixHex(a: string, b: string, t: number): string {
  const A = hexToRgb(a);
  const B = hexToRgb(b);
  const w = clamp01(t);
  const to = (x: number, y: number) => Math.round(x * w + y * (1 - w));
  const h = (n: number) => n.toString(16).padStart(2, '0');
  return `#${h(to(A.r, B.r))}${h(to(A.g, B.g))}${h(to(A.b, B.b))}`;
}

/** Relative luminance (0–1) — used to pick readable text on a fill. */
export function luminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex);
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** Black or near-white, whichever is readable on `bg`. */
export function readableOn(bg: string): string {
  return luminance(bg) > 0.45 ? '#0a0a0a' : '#ffffff';
}

// ── Normalization ────────────────────────────────────────────────────────────

function str(raw: unknown, fallback: string, max = 120): string {
  return typeof raw === 'string' && raw.length <= max ? raw : fallback;
}

function color(raw: unknown, fallback: string): string {
  return normalizeHex(raw) ?? fallback;
}

export function normalizeTheme(raw: unknown): EclipseTheme {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  const colorsRaw = value.colors && typeof value.colors === 'object' && !Array.isArray(value.colors)
    ? (value.colors as Record<string, unknown>)
    : {};
  const d = DEFAULT_ECLIPSE_THEME;
  const density: ThemeDensity =
    value.density === 'compact' || value.density === 'spacious' || value.density === 'comfortable'
      ? value.density
      : d.density;
  const radiusNum = typeof value.radius === 'number' && Number.isFinite(value.radius)
    ? Math.min(1.6, Math.max(0, value.radius))
    : d.radius;
  const fontScaleNum = typeof value.fontScale === 'number' && Number.isFinite(value.fontScale)
    ? Math.min(1.4, Math.max(0.8, value.fontScale))
    : d.fontScale;
  const logoScaleNum = typeof value.logoScale === 'number' && Number.isFinite(value.logoScale)
    ? Math.min(1.8, Math.max(0.6, value.logoScale))
    : d.logoScale;
  return {
    appName: str(value.appName, d.appName, 48),
    logoText: str(value.logoText, d.logoText, 4),
    logoUrl: str(value.logoUrl, d.logoUrl, 400_000),
    faviconUrl: str(value.faviconUrl, d.faviconUrl, 400_000),
    fontUi: str(value.fontUi, d.fontUi, 300),
    fontHeading: str(value.fontHeading, d.fontHeading, 300),
    fontMono: str(value.fontMono, d.fontMono, 300),
    colors: {
      primary: color(colorsRaw.primary, d.colors.primary),
      accent: color(colorsRaw.accent, d.colors.accent),
      background: color(colorsRaw.background, d.colors.background),
      surface: color(colorsRaw.surface, d.colors.surface),
      border: color(colorsRaw.border, d.colors.border),
      text: color(colorsRaw.text, d.colors.text),
      bullish: color(colorsRaw.bullish, d.colors.bullish),
      bearish: color(colorsRaw.bearish, d.colors.bearish),
    },
    radius: radiusNum,
    density,
    fontScale: fontScaleNum,
    logoScale: logoScaleNum,
    glow: value.glow !== false,
    animations: value.animations !== false,
  };
}

/**
 * Derive a complete, coordinated theme from a single brand color. Mirrors the
 * "bring your brand color" flow enterprise consoles offer: the brand becomes
 * primary + bullish, the bearish color is a hue-shifted complement unless the
 * caller supplies one, and surfaces/text stay neutral so charts remain legible.
 */
export function themeFromBrandColor(
  brand: string,
  base: EclipseTheme = DEFAULT_ECLIPSE_THEME,
  overrides: Partial<ThemeColors> = {},
): EclipseTheme {
  const primary = normalizeHex(brand) ?? base.colors.primary;
  const accent = mixHex(primary, '#ffffff', 0.72);
  return normalizeTheme({
    ...base,
    colors: {
      ...base.colors,
      background: base.colors.background || BRAND_GENERATOR_BACKGROUND,
      surface: base.colors.surface || BRAND_GENERATOR_SURFACE,
      primary,
      accent,
      bullish: primary,
      bearish: overrides.bearish ?? base.colors.bearish,
      ...overrides,
    },
  });
}

/** True when `theme` can no longer be described by a shipped preset. */
export function themeMatchesPreset(theme: EclipseTheme, preset: EclipseTheme): boolean {
  return JSON.stringify(normalizeTheme(theme)) === JSON.stringify(normalizeTheme(preset));
}

export function themePresetId(theme: EclipseTheme): string | null {
  const n = normalizeTheme(theme);
  const hit = THEME_PRESETS.find((p) => themeMatchesPreset(n, p.theme));
  return hit ? hit.id : null;
}

// ── Token → CSS custom properties ────────────────────────────────────────────

const DENSITY_SPACING: Record<ThemeDensity, string> = {
  compact: '0.215rem',
  comfortable: '0.27rem',
  spacious: '0.34rem',
};

/**
 * Custom properties that are mode-independent: typography, shape and density.
 * These are applied under `:root`; the color tokens are applied under `.dark`
 * so the General › Theme light/dark switch keeps working.
 */
export const STRUCTURAL_THEME_VARS: ReadonlySet<string> = new Set([
  '--font-sans', '--font-serif', '--font-mono', '--radius', '--spacing',
  '--font-scale', '--logo-scale',
]);

/**
 * Flatten a theme to the CSS custom properties that drive the app. Injected
 * through a managed stylesheet, these override the shipped tokens, so one
 * object recolors every surface (including charts, which read these vars).
 */
export function themeCssVars(theme: EclipseTheme): Record<string, string> {
  const n = normalizeTheme(theme);
  const { primary, accent, background, surface, border, text, bullish, bearish } = n.colors;

  // Derived neutrals so the theme stays internally consistent.
  const secondary = mixHex(surface, background, 0.62);
  const muted = mixHex(surface, background, 0.72);
  const mutedForeground = mixHex(text, background, 0.45);
  const subtleAccent = mixHex(accent, background, 0.16);

  return {
    // Brand
    '--primary': primary,
    '--primary-foreground': readableOn(primary),
    '--ring': primary,
    '--chart-1': primary,
    '--sidebar-primary': primary,
    '--sidebar-ring': primary,
    '--sidebar-accent-foreground': primary,
    '--brand': primary,
    '--brand-rgb': hexToRgbTriplet(primary),
    '--brand-accent': accent,
    '--brand-accent-rgb': hexToRgbTriplet(accent),
    '--brand-hover': mixHex(primary, '#ffffff', 0.78),

    // Surfaces
    '--background': background,
    '--card': surface,
    '--card-foreground': text,
    '--popover': surface,
    '--popover-foreground': text,
    '--secondary': secondary,
    '--secondary-foreground': text,
    '--muted': muted,
    '--muted-foreground': mutedForeground,
    '--accent': subtleAccent,
    '--accent-foreground': text,
    '--border': border,
    '--input': border,
    '--sidebar': surface,
    '--sidebar-foreground': text,
    '--sidebar-accent': secondary,
    '--sidebar-border': border,

    // Text
    '--foreground': text,

    // Market semantics
    '--bullish': bullish,
    '--bullish-rgb': hexToRgbTriplet(bullish),
    '--bearish': bearish,
    '--bearish-rgb': hexToRgbTriplet(bearish),
    '--destructive': bearish,
    '--destructive-foreground': readableOn(bearish),

    // Typography
    '--font-sans': n.fontUi,
    '--font-serif': n.fontHeading,
    '--font-mono': n.fontMono,

    // Shape + density
    '--radius': `${n.radius}rem`,
    '--spacing': DENSITY_SPACING[n.density],
    '--font-scale': `${n.fontScale}`,
    '--logo-scale': `${n.logoScale}`,
  };
}

/** Build an inline SVG favicon from the theme (used when none is supplied). */
export function buildFaviconDataUrl(theme: EclipseTheme): string {
  const n = normalizeTheme(theme);
  const monogram = (n.logoText || n.appName.charAt(0) || 'E').slice(0, 2).toUpperCase();
  const bg = n.colors.primary;
  const fg = readableOn(bg);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">` +
    `<rect width="64" height="64" rx="14" fill="${bg}"/>` +
    `<text x="32" y="42" font-family="Segoe UI, sans-serif" font-size="32" font-weight="700" text-anchor="middle" fill="${fg}">${monogram}</text>` +
    `</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

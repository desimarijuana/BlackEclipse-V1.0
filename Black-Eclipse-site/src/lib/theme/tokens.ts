// ── Eclipse Theme — centralized design tokens ────────────────────────────────
// The single source of truth for user customization (Settings › General).
// A theme is a plain, serializable object; `themeCssVars()` turns it into CSS
// custom properties applied to <html>, so every component that already reads
// `--primary`, `--background`, `--font-mono`, `--radius`, … recolors itself
// with no component-specific hacks.
//
// This module is pure (no React, no DOM) so it is safe to unit test and to
// import from server code. The live store lives in `store.ts`.

import type { BackgroundPrefs } from '@/lib/backgrounds';
import type { AuroraPalette } from '@/lib/aurora-sentiment';

export type ThemeDensity = 'compact' | 'comfortable' | 'spacious';
export type ThemeShadow = 'none' | 'soft' | 'medium' | 'dramatic';
export type ThemeBackground = 'solid' | 'gradient' | 'grid';
/**
 * Color scheme. Drives the `dark` class on <html> and which shipped token
 * block (`.dark` vs `:root`) the theme's colors are scoped to. Distinct from
 * `background` (the page *treatment*: solid/gradient/grid). A light-scheme
 * preset is the proper way to ship a white look — a preset that merely sets a
 * light `colors.background` while `scheme` stays `dark` would fight the
 * hardcoded dark chrome.
 */
export type ThemeScheme = 'dark' | 'light';

/** Frosted-glass controls (Settings › Customization › Glass). */
export interface ThemeGlass {
  /** When false, glass surfaces become solid — no blur, opaque fill. */
  enabled: boolean;
  /** Backdrop blur radius in px. */
  blur: number;
  /** Surface tint opacity (0–1). Higher hides the blur behind a solid fill. */
  opacity: number;
  /** Surface tint color. */
  tint: string;
}

/**
 * Dedicated sidebar surface controls (Settings › Customization › Sidebar).
 * The sidebar reads its own tokens so it can stay a soft grey while the page
 * and cards remain black — independent of the global glass tint.
 */
export interface ThemeSidebar {
  /** Sidebar tint color. */
  tint: string;
  /** Tint opacity (0–1). Higher hides the blur behind a solid fill. */
  opacity: number;
  /** Backdrop blur radius in px. */
  blur: number;
}

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
  /**
   * Optional derived tokens. When omitted they are computed from the core
   * colors (see `deriveThemeColors`). Exposing them lets a user pin them
   * manually without fighting the auto-derivation.
   */
  secondary?: string;
  /** Muted surface fill (`--muted`). */
  muted?: string;
  /** Secondary / muted text (`--muted-foreground`). */
  mutedForeground?: string;
  /** Subtle accent wash used for `--accent` (hover backgrounds). */
  accentSurface?: string;
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
  /** Frosted-glass surface controls. */
  glass: ThemeGlass;
  /** Dedicated sidebar surface controls. */
  sidebar: ThemeSidebar;
  /** Surface drop-shadow weight. */
  shadow: ThemeShadow;
  /** Page background treatment. */
  background: ThemeBackground;
  /** Color scheme — toggles the `dark` class and scopes the color tokens. */
  scheme: ThemeScheme;
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
  glass: { enabled: true, blur: 18, opacity: 0.55, tint: '#121214' },
  // Sidebar ships a neutral grey a touch lighter than the black page/cards —
  // just enough to read as separate chrome, with no brand accent tint.
  sidebar: { tint: '#2a2a2e', opacity: 0.9, blur: 20 },
  shadow: 'soft',
  background: 'solid',
  scheme: 'dark',
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

export const SHADOW_OPTIONS: { id: ThemeShadow; label: string; hint: string }[] = [
  { id: 'none', label: 'Flat', hint: 'No surface shadows' },
  { id: 'soft', label: 'Soft', hint: 'Subtle depth (default)' },
  { id: 'medium', label: 'Medium', hint: 'More pronounced lift' },
  { id: 'dramatic', label: 'Dramatic', hint: 'Heavy, floating panels' },
];

export const BACKGROUND_OPTIONS: { id: ThemeBackground; label: string; hint: string }[] = [
  { id: 'solid', label: 'Solid', hint: 'Single flat color' },
  { id: 'gradient', label: 'Gradient', hint: 'Soft vertical wash' },
  { id: 'grid', label: 'Grid', hint: 'Faint technical grid' },
];

/** Ready-made glass presets users can apply and then fine-tune. */
export const GLASS_PRESETS: { id: string; label: string; hint: string; glass: ThemeGlass }[] = [
  { id: 'frosted', label: 'Frosted', hint: 'The shipped recipe', glass: { enabled: true, blur: 18, opacity: 0.55, tint: '#121214' } },
  { id: 'clear', label: 'Crystal', hint: 'Low tint, heavy blur', glass: { enabled: true, blur: 30, opacity: 0.32, tint: '#101014' } },
  { id: 'heavy', label: 'Smoked', hint: 'Opaque, dark glass', glass: { enabled: true, blur: 14, opacity: 0.80, tint: '#0a0a0c' } },
  { id: 'solid', label: 'Solid', hint: 'No blur — flat surfaces', glass: { enabled: false, blur: 18, opacity: 0.95, tint: '#0f0f0f' } },
];

/** Ready-made sidebar surface presets users can apply and then fine-tune. */
export const SIDEBAR_PRESETS: { id: string; label: string; hint: string; sidebar: ThemeSidebar }[] = [
  { id: 'grey', label: 'Grey', hint: 'Neutral grey chrome (default)', sidebar: { tint: '#2a2a2e', opacity: 0.9, blur: 20 } },
  { id: 'charcoal', label: 'Charcoal', hint: 'Dark grey with a hint of black', sidebar: { tint: '#1a1a1c', opacity: 0.9, blur: 20 } },
  { id: 'slate', label: 'Slate', hint: 'Cool blue-charcoal lift', sidebar: { tint: '#1e2228', opacity: 0.88, blur: 22 } },
  { id: 'smoke', label: 'Smoke', hint: 'Warm neutral charcoal', sidebar: { tint: '#1d1c1b', opacity: 0.9, blur: 18 } },
  { id: 'crystal', label: 'Crystal', hint: 'Translucent frost, heavy blur', sidebar: { tint: '#26262c', opacity: 0.55, blur: 34 } },
  { id: 'black', label: 'Black', hint: 'Match the black page', sidebar: { tint: '#0c0c0e', opacity: 0.9, blur: 18 } },
];

// ── Presets ──────────────────────────────────────────────────────────────────

export interface ThemePreset {
  id: string;
  label: string;
  description: string;
  theme: EclipseTheme;
  /**
   * Optional ChatBot-backdrop snapshot. A theme is more than its tokens: the
   * landing wallpaper and giant wordmark are part of the look, so a preset
   * carries them here and the customization panel pushes them to the background
   * store on preview/apply. The snapshot is PARTIAL — it is merged over the
   * live background prefs, so a preset that only sets the wordmark font keeps
   * the user's chosen wallpaper image (and vice versa).
   */
  background?: Partial<BackgroundPrefs>;
  /**
   * Optional Aurora-glow palette snapshot. The ambient Aurora glow is part of a
   * theme's identity, so a preset carries its three sentiment colors here; the
   * panel pushes them to the Aurora store on preview/apply. Derived from the
   * theme's own bullish/bearish colors when omitted.
   */
  aurora?: AuroraPalette;
}

/** The Aurora default brand glow, reused by the Eclipse preset. */
const ECLIPSE_AURORA: AuroraPalette = {
  bullish: { core: '#7aff78', edge: '#022c22' },
  neutral: { core: '#3d9e63', edge: '#02170f' },
  bearish: { core: '#ff0000', edge: '#3a0000' },
};

/** Derive an Aurora palette from a preset's palette: bullish→neutral ramp,
 *  bearish→neutral ramp, neutral between them. Keeps the glow coherent with the
 *  theme tokens when a preset does not pin its own `aurora`. */
export function auroraFromColors(colors: Partial<ThemeColors>): AuroraPalette {
  const bullish = colors.bullish ?? DEFAULT_ECLIPSE_THEME.colors.bullish;
  const bearish = colors.bearish ?? DEFAULT_ECLIPSE_THEME.colors.bearish;
  const background = colors.background ?? DEFAULT_ECLIPSE_THEME.colors.background;
  return {
    bullish: { core: bullish, edge: mixHex(bullish, background, 0.22) },
    neutral: { core: mixHex(bullish, bearish, 0.5), edge: mixHex(bullish, background, 0.12) },
    bearish: { core: bearish, edge: mixHex(bearish, background, 0.22) },
  };
}

function preset(
  id: string,
  label: string,
  description: string,
  colors: Partial<ThemeColors>,
  extra?: Partial<EclipseTheme>,
  background?: Partial<BackgroundPrefs>,
): ThemePreset {
  // Every shipped preset's ChatBot landing is a simple FLAT solid: a near-
  // neutral grey carrying only the faintest shade of the preset's ACCENT hue
  // (the Hermes look) — never a bright or over-saturated wash, never a
  // gradient. Dark-scheme presets mix toward a dark base with a whitish
  // wordmark; light-scheme presets (e.g. White) mix toward a light base with a
  // dark wordmark, so the landing stays legible in both schemes. A caller may
  // still pin an explicit `solidColor`/`textColor` to override.
  const scheme: ThemeScheme = extra?.scheme ?? DEFAULT_ECLIPSE_THEME.scheme;
  const isLight = scheme === 'light';
  const accent = colors.accent ?? DEFAULT_ECLIPSE_THEME.colors.accent;
  const tint = mixHex(accent, isLight ? LANDING_BASE_LIGHT : LANDING_BASE, isLight ? 0.04 : 0.05);
  const wordmark = isLight ? '#1f2937' : '#e8e8ea';
  const landing: Partial<BackgroundPrefs> = {
    ...(background ?? {}),
    mode: background?.mode ?? 'solid',
    solidFill: background?.solidFill ?? 'flat',
    solidColor: background?.solidColor?.trim() || tint,
    textColor: background?.textColor?.trim() || wordmark,
  };
  return {
    id,
    label,
    description,
    background: landing,
    aurora: auroraFromColors(colors),
    theme: {
      ...DEFAULT_ECLIPSE_THEME,
      ...extra,
      colors: { ...DEFAULT_ECLIPSE_THEME.colors, ...colors },
    },
  };
}

/**
 * Build a light-scheme preset from a brand + surface palette. Keeps the ~4
 * white-background presets consistent: dark ink text, white glass/sidebar, and
 * a light landing with a dark wordmark. `surfaces` overrides the page/surface/
 * border tones for warm/cool variants.
 */
function lightPreset(
  id: string,
  label: string,
  description: string,
  colors: Partial<ThemeColors>,
  surfaces: { page?: string; surface?: string; border?: string } = {},
): ThemePreset {
  return preset(
    id,
    label,
    description,
    {
      ...colors,
      background: surfaces.page ?? '#f6f6f7',
      surface: surfaces.surface ?? '#ffffff',
      border: surfaces.border ?? '#e4e4e7',
      text: '#18181b',
      secondary: surfaces.surface ?? '#ffffff',
      muted: surfaces.page ?? '#f6f6f7',
      mutedForeground: '#52525b',
    },
    {
      scheme: 'light',
      glass: { enabled: true, blur: 18, opacity: 0.62, tint: surfaces.surface ?? '#ffffff' },
      sidebar: { tint: surfaces.surface ?? '#ffffff', opacity: 0.85, blur: 20 },
      shadow: 'soft',
      background: 'solid',
    },
    {
      mode: 'solid', solidFill: 'flat',
      solidColor: surfaces.page ?? '#f0f0f2',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT,
      textUppercase: true, textScale: 7, textOpacity: 70, textAlign: 'center',
    },
  );
}

/** The shared ChatBot landing wordmark font for every shipped preset (Michroma). */
const PRESET_WORDMARK_FONT = 'var(--font-michroma), system-ui, sans-serif';

/**
 * The neutral base every preset's ChatBot landing is mixed toward: a darkish
 * grey. The preset's accent hue is mixed in at a low weight, so each landing is
 * a calm grey with a faint brand shade (the Hermes look), never a bright tint.
 */
const LANDING_BASE = '#0f0f11';

/**
 * The light-scheme counterpart of {@link LANDING_BASE}: a near-white grey the
 * White preset's landing is mixed toward, carrying the faintest accent shade.
 */
const LANDING_BASE_LIGHT = '#f1f1f4';

// Hex validation must precede the presets: `preset()` derives each landing tint
// at module-load, which calls down into `mixHex`.
const HEX_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** Shipped Eclipse-family looks. The first is the brand default. */
/**
 * Neutral backgrounds shipped with the brand-color generator when the user
 * asks to derive a full theme from a single brand color (ServiceNow-style).
 */
export const BRAND_GENERATOR_BACKGROUND = '#000000';
export const BRAND_GENERATOR_SURFACE = '#0f0f0f';

export const THEME_PRESETS: ThemePreset[] = [
  {
    id: 'eclipse',
    label: 'Eclipse',
    description: 'The default green-on-black terminal.',
    theme: DEFAULT_ECLIPSE_THEME,
    background: {
      mode: 'solid',
      solidFill: 'flat',
      solidColor: '#131615',
      textEnabled: true,
      text: 'ECLIPSE AGENT',
      textFont: PRESET_WORDMARK_FONT,
      textColor: '#e6ffe5',
      textUppercase: true,
      textScale: 7,
      textOpacity: 78,
      textAlign: 'center',
    },
  },
  preset('electric-blue', 'Electric Blue', 'Electric cyan-blue brand on a cold dark landing.',
    { primary: '#77edfd', accent: '#36c8d3', background: '#000000', surface: '#0f0f0f', border: '#2a2a2e', text: '#f4f4f5', bullish: '#7aff78', bearish: '#ff3e3e' },
    // Sidebar uses the translucent Crystal recipe (not the default Grey), so the
    // cold blue brand carries into the rail instead of a neutral grey chrome.
    { glass: { enabled: true, blur: 18, opacity: 0.55, tint: '#121214' }, shadow: 'dramatic', background: 'solid', sidebar: { tint: '#26262c', opacity: 0.55, blur: 34 } },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('midnight', 'Midnight', 'Cool indigo accent on deep navy.',
    { primary: '#818cf8', accent: '#6366f1', background: '#05060f', surface: '#0d1020', border: '#26304a', text: '#e6e8f2', bullish: '#818cf8', bearish: '#fb7185' },
    { sidebar: { tint: '#10142a', opacity: 0.9, blur: 20 } },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('matrix', 'Matrix', 'Phosphor-green terminal, minimal red.',
    { primary: '#00ff41', accent: '#22c55e', background: '#000400', surface: '#05130a', border: '#12351f', text: '#d7ffe4', bullish: '#00ff41', bearish: '#ff3b3b' },
    undefined,
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('ocean', 'Ocean', 'Cold cyan brand with a coral bearish shift.',
    { primary: '#38bdf8', accent: '#22d3ee', background: '#02090f', surface: '#0a1622', border: '#1d3247', text: '#e2f3fb', bullish: '#38bdf8', bearish: '#fb7185' },
    { sidebar: { tint: '#0b1a2a', opacity: 0.9, blur: 20 } },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('solar', 'Solar', 'Warm amber brand on charcoal.',
    { primary: '#fbbf24', accent: '#f59e0b', background: '#0c0803', surface: '#17110a', border: '#3a2c14', text: '#fdf4e3', bullish: '#fbbf24', bearish: '#ff5c5c' },
    undefined,
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('crimson', 'Crimson', 'Rose-forward brand for a warmer terminal.',
    { primary: '#fb7185', accent: '#f43f5e', background: '#0d0508', surface: '#190c12', border: '#3f1622', text: '#fdeef2', bullish: '#fb7185', bearish: '#ff2d55' },
    undefined,
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('mono', 'Mono', 'Neutral greyscale with a white brand.',
    { primary: '#e5e5e5', accent: '#a3a3a3', background: '#000000', surface: '#0f0f0f', border: '#2a2a2e', text: '#fafafa', bullish: '#e5e5e5', bearish: '#737373' },
    { glass: { enabled: false, blur: 0, opacity: 0.95, tint: '#0f0f0f' }, shadow: 'none' },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('crystal', 'Crystal', 'Bright, high-blur glass over a soft gradient.',
    { primary: '#60a5fa', accent: '#93c5fd', background: '#05070f', surface: '#0b1020', border: '#243047', text: '#eaf1ff', bullish: '#60a5fa', bearish: '#fb7185' },
    { glass: { enabled: true, blur: 34, opacity: 0.30, tint: '#0a0e1a' }, background: 'solid', shadow: 'dramatic', sidebar: { tint: '#101a2e', opacity: 0.8, blur: 26 } },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('blueprint', 'Blueprint', 'Technical grid, tight radius and flat surfaces.',
    { primary: '#38bdf8', accent: '#0ea5e9', background: '#03070d', surface: '#0a1119', border: '#183042', text: '#e0f2fe', bullish: '#38bdf8', bearish: '#f87171' },
    { glass: { enabled: false, blur: 0, opacity: 0.95, tint: '#0a1119' }, background: 'solid', shadow: 'none', radius: 0.25, sidebar: { tint: '#0a1826', opacity: 0.94, blur: 0 } },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('smoked', 'Smoked', 'Opaque dark glass with heavy depth.',
    { primary: '#f59e0b', accent: '#fbbf24', background: '#0a0805', surface: '#141009', border: '#3a2c14', text: '#fdf4e3', bullish: '#f59e0b', bearish: '#ef4444' },
    { glass: { enabled: true, blur: 12, opacity: 0.82, tint: '#0a0805' }, shadow: 'dramatic' },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('bloomberg', 'Bloomberg', 'Dense amber-on-black trading terminal with blue selection.',
    { primary: '#ffa028', accent: '#2d7ff9', background: '#000000', surface: '#0a0a0a', border: '#2b2b2b', text: '#e8e8e8', bullish: '#4ade80', bearish: '#ff4438' },
    { glass: { enabled: false, blur: 0, opacity: 0.96, tint: '#0a0a0a' }, shadow: 'none', density: 'compact', radius: 0.2 },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  preset('bubudoll', 'Bubudoll', 'Soft candy pink with a cute, rounded ambient glow.',
    { primary: '#ff9ecb', accent: '#ffd1e8', background: '#170b14', surface: '#261323', border: '#4d2540', text: '#ffeaf5', bullish: '#ff9ecb', bearish: '#ff4d6d' },
    { glass: { enabled: true, blur: 24, opacity: 0.45, tint: '#2a1426' }, background: 'solid', shadow: 'medium', radius: 1 },
    { mode: 'solid', solidFill: 'flat',
      textEnabled: true, text: 'ECLIPSE AGENT', textFont: PRESET_WORDMARK_FONT, textUppercase: true, textScale: 7, textOpacity: 78, textAlign: 'center' }),
  // ── Light / white-background presets (listed last; one click switches the
  // whole app to a light look). `scheme: 'light'` is what makes these work:
  // applying one removes the `dark` class, so every `html:not(.dark)` recipe
  // (glass, sidebar, calendar, ws-glass) and the `:root` light token block
  // activate together. `text` is dark ink so copy reads on the white page; the
  // wordmark is dark for the same reason. One shared factory keeps them
  // consistent.
  lightPreset('white', 'White', 'Crisp white page with an emerald brand.',
    { primary: '#047857', accent: '#34d399', bullish: '#16a34a', bearish: '#dc2626' }),
  lightPreset('paper', 'Paper', 'Warm off-white page with an amber brand.',
    { primary: '#b45309', accent: '#f59e0b', bullish: '#16a34a', bearish: '#dc2626' },
    { page: '#f7f3ec', surface: '#fffdf9', border: '#e7ddcd' }),
  lightPreset('snow', 'Snow', 'Cool white page with a slate-blue brand.',
    { primary: '#2563eb', accent: '#60a5fa', bullish: '#16a34a', bearish: '#dc2626' },
    { page: '#f4f7fb', surface: '#ffffff', border: '#d8e2ef' }),
  lightPreset('ivory', 'Ivory', 'Soft ivory page with a rose brand.',
    { primary: '#be123c', accent: '#fb7185', bullish: '#16a34a', bearish: '#e11d48' },
    { page: '#faf6f4', surface: '#fffdfd', border: '#ecdcd8' }),
];

// ── Color helpers ────────────────────────────────────────────────────────────

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

/** Emit `{ [key]: hex }` only when the raw value supplied a valid hex. */
function optionalColor<K extends keyof ThemeColors>(key: K, raw: unknown): Partial<ThemeColors> {
  const n = normalizeHex(raw);
  return n ? ({ [key]: n } as Partial<ThemeColors>) : {};
}

/** All theme colors with derivation resolved — every key is present. */
export type ResolvedThemeColors = Required<ThemeColors>;

/**
 * Resolve the optional derived tokens. Explicit user overrides win; otherwise
 * the neutrals are mixed from the core colors so the palette stays internally
 * consistent. Single source of truth for both `themeCssVars` and the editors.
 */
export function deriveThemeColors(colors: ThemeColors): ResolvedThemeColors {
  const { primary, accent, background, surface, border, text, bullish, bearish } = colors;
  return {
    primary, accent, background, surface, border, text, bullish, bearish,
    secondary: colors.secondary ?? mixHex(surface, background, 0.62),
    muted: colors.muted ?? mixHex(surface, background, 0.72),
    mutedForeground: colors.mutedForeground ?? mixHex(text, background, 0.45),
    accentSurface: colors.accentSurface ?? mixHex(accent, background, 0.16),
  };
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
  const glassRaw = value.glass && typeof value.glass === 'object' && !Array.isArray(value.glass)
    ? (value.glass as Record<string, unknown>)
    : {};
  const glass: ThemeGlass = {
    enabled: glassRaw.enabled !== false,
    blur: typeof glassRaw.blur === 'number' && Number.isFinite(glassRaw.blur)
      ? Math.min(48, Math.max(0, glassRaw.blur))
      : d.glass.blur,
    opacity: typeof glassRaw.opacity === 'number' && Number.isFinite(glassRaw.opacity)
      ? Math.min(1, Math.max(0, glassRaw.opacity))
      : d.glass.opacity,
    tint: color(glassRaw.tint, d.glass.tint),
  };
  const sidebarRaw = value.sidebar && typeof value.sidebar === 'object' && !Array.isArray(value.sidebar)
    ? (value.sidebar as Record<string, unknown>)
    : {};
  const sidebar: ThemeSidebar = {
    tint: color(sidebarRaw.tint, d.sidebar.tint),
    opacity: typeof sidebarRaw.opacity === 'number' && Number.isFinite(sidebarRaw.opacity)
      ? Math.min(1, Math.max(0, sidebarRaw.opacity))
      : d.sidebar.opacity,
    blur: typeof sidebarRaw.blur === 'number' && Number.isFinite(sidebarRaw.blur)
      ? Math.min(48, Math.max(0, sidebarRaw.blur))
      : d.sidebar.blur,
  };
  const shadow: ThemeShadow =
    value.shadow === 'none' || value.shadow === 'medium' || value.shadow === 'dramatic' || value.shadow === 'soft'
      ? value.shadow
      : d.shadow;
  const background: ThemeBackground =
    value.background === 'gradient' || value.background === 'grid' || value.background === 'solid'
      ? value.background
      : d.background;
  const scheme: ThemeScheme =
    value.scheme === 'light' || value.scheme === 'dark'
      ? value.scheme
      : d.scheme;
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
      // Optional derived tokens: kept only when the input actually supplied a
      // valid value, so an untouched theme stays equal to the shipped default
      // (which omits them) and derivation remains the default behavior.
      ...optionalColor('secondary', colorsRaw.secondary),
      ...optionalColor('muted', colorsRaw.muted),
      ...optionalColor('mutedForeground', colorsRaw.mutedForeground),
      ...optionalColor('accentSurface', colorsRaw.accentSurface),
    },
    radius: radiusNum,
    density,
    fontScale: fontScaleNum,
    logoScale: logoScaleNum,
    glass,
    sidebar,
    shadow,
    background,
    scheme,
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
 * A CSS `background-image` value for the page treatment. `none` for a flat
 * color; a subtle vertical wash for `gradient`; a faint technical grid for
 * `grid` (brand-tinted so it tracks the theme).
 */
export function pageBackgroundImage(kind: ThemeBackground, brand: string): string {
  const rgb = hexToRgbTriplet(brand);
  if (kind === 'gradient') {
    return `radial-gradient(1200px 600px at 50% -10%, rgb(${rgb} / 0.10), transparent 70%)`;
  }
  if (kind === 'grid') {
    return (
      `linear-gradient(rgb(${rgb} / 0.05) 1px, transparent 1px), ` +
      `linear-gradient(90deg, rgb(${rgb} / 0.05) 1px, transparent 1px)`
    );
  }
  return 'none';
}

/**
 * Custom properties that are mode-independent: typography, shape and density.
 * These are applied under `:root`; the color tokens are applied under `.dark`
 * so the General › Theme light/dark switch keeps working.
 */
export const STRUCTURAL_THEME_VARS: ReadonlySet<string> = new Set([
  '--font-sans', '--font-serif', '--font-heading', '--font-mono', '--radius', '--spacing',
  '--font-scale', '--logo-scale',
  '--glass-blur', '--glass-opacity', '--glass-shadow', '--glass-enabled',
  '--glass-tint-light', '--page-bg-image', '--page-bg-size',
  '--sidebar-rgb', '--sidebar-opacity', '--sidebar-blur',
]);
// NOTE: `--glass-tint` is deliberately a COLOR token (scoped to `html.dark`), so
// a custom dark tint never leaks into light mode — light keeps the shipped white
// frosted recipe unless the user switches to light and recolors there.

/**
 * Flatten a theme to the CSS custom properties that drive the app. Injected
 * through a managed stylesheet, these override the shipped tokens, so one
 * object recolors every surface (including charts, which read these vars).
 */
export function themeCssVars(theme: EclipseTheme): Record<string, string> {
  const n = normalizeTheme(theme);
  const { primary, accent, background, surface, border, text, bullish, bearish } = n.colors;

  // Derived neutrals so the theme stays internally consistent — unless the user
  // pinned them explicitly (then `deriveThemeColors` returns the override).
  const derived = deriveThemeColors(n.colors);
  const secondary = derived.secondary;
  const muted = derived.muted;
  const mutedForeground = derived.mutedForeground;
  const subtleAccent = derived.accentSurface;

  // Glass surfaces: when disabled the tint becomes (near) opaque and blur 0,
  // so every `.glass-*` recipe reads as a solid panel with no backdrop filter.
  const glass = n.glass;
  const glassOpacity = glass.enabled ? glass.opacity : 0.95;
  const glassBlur = glass.enabled ? glass.blur : 0;
  const glassTint = hexToRgbTriplet(glass.tint);

  // Sidebar surface: its own tint/blur so the rail can read grey while the page
  // stays black. When glass is disabled the sidebar becomes solid too.
  const sb = n.sidebar;
  const sidebarOpacity = glass.enabled ? sb.opacity : 0.96;
  const sidebarBlur = glass.enabled ? sb.blur : 0;

  // Surface shadow tiers. `none` keeps a hairline box for edge definition.
  const SHADOW: Record<ThemeShadow, string> = {
    none: '0 0 0 rgba(0,0,0,0)',
    soft: '0 8px 30px rgba(0,0,0,0.30)',
    medium: '0 14px 44px rgba(0,0,0,0.45)',
    dramatic: '0 24px 70px rgba(0,0,0,0.60)',
  };

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
    // Triplet form of the surface/card color so the frosted-glass tiers
    // (`.glass-card`, `-strong`, `-subtle`, tooltips, buttons) can build a
    // translucent tint from ONE theme color. Without this the glass recipe used
    // a hardcoded rgba(18,18,20) and the Surface control only recolored flat
    // `bg-card` blocks, so editing Surface barely changed the UI.
    '--card-rgb': hexToRgbTriplet(surface),
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
    '--sidebar': sb.tint,
    '--sidebar-foreground': text,
    '--sidebar-accent': secondary,
    '--sidebar-border': border,
    '--sidebar-rgb': hexToRgbTriplet(sb.tint),
    '--sidebar-opacity': `${sidebarOpacity}`,
    '--sidebar-blur': `${sidebarBlur}px`,

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
    '--font-heading': n.fontHeading,
    '--font-mono': n.fontMono,

    // Shape + density
    '--radius': `${n.radius}rem`,
    '--spacing': DENSITY_SPACING[n.density],
    '--font-scale': `${n.fontScale}`,
    '--logo-scale': `${n.logoScale}`,

    // Glass surfaces
    '--glass-blur': `${glassBlur}px`,
    '--glass-opacity': `${glassOpacity}`,
    '--glass-tint': glassTint,
    '--glass-shadow': SHADOW[n.shadow],
    '--glass-enabled': glass.enabled ? '1' : '0',
    // Light-mode tint: default white, or a lightened version of the custom tint.
    '--glass-tint-light': glass.enabled && glass.tint !== DEFAULT_ECLIPSE_THEME.glass.tint
      ? hexToRgbTriplet(mixHex(glass.tint, '#ffffff', 0.12))
      : '255 255 255',

    // Page background treatment (image layers over the `--background` color)
    '--page-bg-image': pageBackgroundImage(n.background, primary),
    '--page-bg-size': n.background === 'grid' ? '22px 22px' : 'auto',
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

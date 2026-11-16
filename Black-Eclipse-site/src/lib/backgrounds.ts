// ── App background (Settings › General › Background) ────────────────────────
// One place for the app's backdrop: none (the theme's own surface) or a full
// image wallpaper — the shipped Eclipse SVGs and a user's own picture.
//
// The old flat/gradient/grid "pattern" treatment is gone: it was the theme's
// job (Customization › Theme), the `solid` default rendered nothing, and a
// separate Pattern type in this card only confused — `None` already exposes the
// theme's pattern. This card now owns the wallpaper alone.
//
// Why its own store instead of the theme store: the theme is dark-mode-scoped
// tokens and a draft/preview apply model; a background is a single, immediately
// applied preference with its own (potentially large) payload. Keeping it
// separate lets the General tab stay simple and keeps theme previews from
// touching the wallpaper.
//
// Persistence split:
//   * Small prefs + the *reference* to a custom image → localStorage (`be_background_v1`).
//   * The custom image bytes → IndexedDB (`be_background` / `custom`), so a
//     full-res wallpaper never eats the ~5 MB localStorage budget shared with
//     themes and chats.
//
// The applied values are pure CSS custom properties (not a stylesheet), so they
// do not fight the theme's managed `<style id="eclipse-theme-overrides">`.
// `none` clears them so the theme's surface shows; `image` suppresses the theme
// pattern and feeds a full-viewport `.app-bg-layer` that `stock-chat.tsx`
// renders on the ChatBot landing only.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import { LEGACY_DARK_LANDING_COLORS, type FontOption } from '@/lib/theme/tokens';

// ── Model ────────────────────────────────────────────────────────────────────

/**
 * What kind of backdrop is active.
 *   * `image` — a shipped or uploaded wallpaper.
 *   * `solid` — a flat custom color with a customizable wordmark.
 */
export type BackgroundMode = 'image' | 'solid';
/** How the `solid` backdrop is painted. */
export type SolidFill = 'flat' | 'gradient' | 'pattern';
/** How the opt-in chat-conversation surface is painted. */
export type ChatSurfaceFill = 'flat' | 'gradient';
/** A texture overlaid when `solidFill === 'pattern'`. */
export type SolidPattern = 'grid' | 'dots' | 'diagonal' | 'ascii';
/** Gradient shape. */
export type SolidGradientType = 'linear' | 'radial';
/** How the image fills its box. */
export type BackgroundFit = 'cover' | 'contain' | 'tile';
/** Preset id, or `custom` when the user's own image is active. */
export type BackgroundPresetId = string;
/** Horizontal alignment of the giant ChatBot wordmark. */
export type WordmarkAlign = 'left' | 'center' | 'right';

/** The default giant wordmark painted on the ChatBot landing. */
export const DEFAULT_WORDMARK_TEXT = 'ECLIPSE AGENT';

/**
 * The ChatBot landing backdrop's default fill in DARK mode. When the user has
 * not picked an explicit solid color, the landing defaults to this near-black on
 * every theme (the theme background still applies in light mode), so the page
 * behind the wordmark reads the same regardless of the active theme.
 */
export const DEFAULT_SOLID_DARK_COLOR = '#0a0b0b';

/**
 * The default wordmark typeface — Michroma, a wide geometric sci-fi display
 * face, self-hosted via next/font as `--font-michroma`.
 */
export const DEFAULT_WORDMARK_FONT = 'var(--font-michroma), system-ui, sans-serif';

export interface BackgroundPrefs {
  mode: BackgroundMode;
  /** A shipped id (`eclipse-1`/`eclipse-4`/`eclipse-5`), or `custom`. */
  preset: BackgroundPresetId;
  /** Non-empty only for `preset: 'custom'`; a key into the custom-image store. */
  customKey: string;
  fit: BackgroundFit;
  /** Zoom, 50–300 (%). 100 = exactly the fit size; below 100 shrinks it. */
  scale: number;
  /** Horizontal focal point, 0–100 (%). 50 = centered. */
  positionX: number;
  /** Vertical focal point, 0–100 (%). 50 = centered. */
  positionY: number;
  /** Scrim strength over the image, 0–100, so text stays legible on any art. */
  dim: number;
  /**
   * How the solid backdrop is painted: a flat fill, a brand-tinted gradient, or
   * a flat fill with a texture overlay.
   */
  solidFill: SolidFill;
  /**
   * The base page color for `mode: 'solid'`. Empty = follow the theme's
   * `--background`, so a solid backdrop can stay theme-coordinated or be
   * overridden with an explicit pick.
   */
  solidColor: string;
  /** The second color for `solidFill: 'gradient'`. Empty = derive from brand. */
  solidColor2: string;
  /** Gradient shape. */
  solidGradientType: SolidGradientType;
  /** Gradient angle in degrees for `linear` (0–360). */
  solidGradientAngle: number;
  /** The texture overlay for `solidFill: 'pattern'`. */
  solidPattern: SolidPattern;
  /** Texture strength, 0–100. */
  solidPatternOpacity: number;
  /** Texture tile size in px (pattern pitch). 4–80. */
  solidPatternScale: number;
  /**
   * Whether the giant wordmark is painted behind the ChatBot landing. ON for the
   * `solid` mode (the wordmark IS the backdrop there); opt-in for `image` so a
   * wallpaper shows alone unless the user wants text over it. The `text` fields
   * below are retained while off so a user's authored wordmark survives toggling.
   */
  textEnabled: boolean;
  /** Optional giant wordmark painted behind the ChatBot landing (may be empty). */
  text: string;
  /** A `value` from `WORDMARK_FONT_OPTIONS`. */
  textFont: string;
  /** Wordmark color (any CSS color). Empty = follow `--foreground`. */
  textColor: string;
  /** Font weight, 100–900. */
  textWeight: number;
  /** Letter-spacing in em (can be negative to tighten). -0.1–0.5. */
  textLetterSpacing: number;
  /** Line-height multiplier. 0.7–2. */
  textLineHeight: number;
  /** Horizontal scale / width (font-stretch). 50–200 (%). */
  textWidth: number;
  /** Italic slant. */
  textItalic: boolean;
  /** Uppercase transform. */
  textUppercase: boolean;
  /** Wordmark size in viewport-width units (vw), 4–40. */
  textScale: number;
  /** Wordmark strength, 0–100 (100 = full foreground, low = ghosted). */
  textOpacity: number;
  /** Vertical placement of the wordmark, 0 (top) – 100 (bottom). */
  textPositionY: number;
  /** Horizontal alignment of the wordmark. */
  textAlign: WordmarkAlign;
  /**
   * Surface painted behind the ChatBot *conversation* (transcript + composer),
   * independent of the page backdrop. On by default so replies sit on a calm
   * surface (`#0a0b0b` dark / a matte off-white light) instead of a busy
   * wallpaper.
   */
  chatSurfaceEnabled: boolean;
  /** How the chat surface is painted: a flat color or a two-color gradient. */
  chatSurfaceFill: ChatSurfaceFill;
  /** Base color for the chat surface in DARK mode. Empty = theme's `--card`. */
  chatSurfaceColor: string;
  /** Base color for the chat surface in LIGHT mode. Empty = theme's `--card`. */
  chatSurfaceColorLight: string;
  /** Gradient end color (shared). Empty = derive from the brand color. */
  chatSurfaceColor2: string;
  /** Chat-surface strength, 0–100 (lets the backdrop show through). */
  chatSurfaceOpacity: number;
  /**
   * The prompt-bubble fill in DARK mode. Empty = a neutral translucent tint
   * (`color-mix(foreground 10%)`), the shipped look.
   */
  chatBubbleColor: string;
  /** The prompt-bubble fill in LIGHT mode. Empty = the neutral tint. */
  chatBubbleColorLight: string;
}

/** The wallpaper the Image picker selects by default (DEFAULT_BACKGROUND_ID). */
export const DEFAULT_BACKGROUND_ID = 'eclipse-1';

export const DEFAULT_BACKGROUND: BackgroundPrefs = {
  // A fresh install lands on a SOLID backdrop (with the giant wordmark), not a
  // wallpaper — no image paints until the user explicitly picks one from
  // Settings › General › Background. `preset` still carries the shipped Eclipse I
  // wallpaper so switching to Image mode pre-selects it.
  mode: 'solid',
  preset: DEFAULT_BACKGROUND_ID,
  customKey: '',
  fit: 'cover',
  scale: 100,
  positionX: 50,
  positionY: 50,
  dim: 45,
  // Solid type: a flat fill that follows the theme until the user picks a color.
  solidFill: 'flat',
  solidColor: '',
  solidColor2: '',
  solidGradientType: 'linear',
  solidGradientAngle: 160,
  solidPattern: 'grid',
  solidPatternOpacity: 18,
  solidPatternScale: 22,
  // The wordmark is opt-in for image mode (and forced on in solid mode, the
  // shipped default). At 7vw it reads as a modest centered label rather than a
  // full-bleed backdrop; the authored text is kept so a user can flip it on from
  // Settings › General › Background without retyping it.
  textEnabled: false,
  text: DEFAULT_WORDMARK_TEXT,
  textFont: DEFAULT_WORDMARK_FONT,
  textColor: '',
  textWeight: 600,
  textLetterSpacing: -0.01,
  textLineHeight: 0.9,
  textWidth: 100,
  textItalic: false,
  textUppercase: false,
  textScale: 7,
  textOpacity: 90,
  textPositionY: 50,
  textAlign: 'center',
  // Chat-conversation surface: ON by default — a near-black in dark mode and a
  // matte off-white in light mode, so the conversation sits on a calm surface.
  chatSurfaceEnabled: true,
  chatSurfaceFill: 'flat',
  chatSurfaceColor: '#0a0b0b',
  chatSurfaceColorLight: '#f4f4f5',
  chatSurfaceColor2: '',
  chatSurfaceOpacity: 100,
  chatBubbleColor: '',
  chatBubbleColorLight: '',
};

const MODES: readonly BackgroundMode[] = ['image', 'solid'];
const SOLID_FILLS: readonly SolidFill[] = ['flat', 'gradient', 'pattern'];
const SOLID_PATTERNS: readonly SolidPattern[] = ['grid', 'dots', 'diagonal', 'ascii'];
const GRADIENT_TYPES: readonly SolidGradientType[] = ['linear', 'radial'];
const FITS: readonly BackgroundFit[] = ['cover', 'contain', 'tile'];
const WORDMARK_ALIGNS: readonly WordmarkAlign[] = ['left', 'center', 'right'];
const CHAT_SURFACE_FILLS: readonly ChatSurfaceFill[] = ['flat', 'gradient'];
const MAX_WORDMARK_LENGTH = 64;

export const BACKGROUND_MODE_OPTIONS: { id: BackgroundMode; label: string; hint: string }[] = [
  { id: 'solid', label: 'Solid', hint: 'A color, gradient or pattern with a customizable wordmark' },
  { id: 'image', label: 'Image', hint: 'A shipped or uploaded wallpaper' },
];

export const SOLID_FILL_OPTIONS: { id: SolidFill; label: string; hint: string }[] = [
  { id: 'flat', label: 'Flat', hint: 'One solid color' },
  { id: 'gradient', label: 'Gradient', hint: 'A two-color wash' },
  { id: 'pattern', label: 'Pattern', hint: 'A color with a texture overlay' },
];

export const SOLID_PATTERN_OPTIONS: { id: SolidPattern; label: string; hint: string }[] = [
  { id: 'grid', label: 'Grid', hint: 'Faint technical grid' },
  { id: 'dots', label: 'Dots', hint: 'Even dot matrix' },
  { id: 'diagonal', label: 'Diagonal', hint: 'Diagonal hatching' },
  { id: 'ascii', label: 'ASCII', hint: 'Terminal character texture' },
];

export const GRADIENT_TYPE_OPTIONS: { id: SolidGradientType; label: string; hint: string }[] = [
  { id: 'linear', label: 'Linear', hint: 'Straight-angle wash' },
  { id: 'radial', label: 'Radial', hint: 'Center-out glow' },
];

export const CHAT_SURFACE_FILL_OPTIONS: { id: ChatSurfaceFill; label: string; hint: string }[] = [
  { id: 'flat', label: 'Flat', hint: 'One solid color' },
  { id: 'gradient', label: 'Gradient', hint: 'A two-color wash' },
];

export const BACKGROUND_FIT_OPTIONS: { id: BackgroundFit; label: string; hint: string }[] = [
  { id: 'cover', label: 'Cover', hint: 'Fill the screen, cropping if needed' },
  { id: 'contain', label: 'Contain', hint: 'Fit the whole image, letterboxed' },
  { id: 'tile', label: 'Tile', hint: 'Repeat the image at its native size' },
];

/**
 * Fonts offered for the giant ChatBot wordmark. Each value references a
 * next/font CSS variable loaded in `src/app/layout.tsx` (self-hosted, zero
 * runtime request) so the choices actually render differently. Curated for
 * range: elegant serif, sci-fi display, pixel and ASCII/mono faces. Keep this
 * list in sync with the imports in `layout.tsx`.
 */
export const WORDMARK_FONT_OPTIONS: FontOption[] = [
  { label: 'Bodoni', value: 'var(--font-bodoni), Georgia, serif' },
  { label: 'Playfair', value: 'var(--font-playfair), Georgia, serif' },
  { label: 'Cinzel', value: 'var(--font-cinzel), Georgia, serif' },
  { label: 'Cormorant', value: 'var(--font-cormorant), Georgia, serif' },
  { label: 'Orbitron', value: 'var(--font-orbitron), system-ui, sans-serif' },
  { label: 'Audiowide', value: 'var(--font-audiowide), system-ui, sans-serif' },
  { label: 'Michroma', value: 'var(--font-michroma), system-ui, sans-serif' },
  { label: 'Press Start (pixel)', value: 'var(--font-press-start), monospace' },
  { label: 'Silkscreen (pixel)', value: 'var(--font-silkscreen), monospace' },
  { label: 'VT323 (terminal)', value: 'var(--font-vt323), monospace' },
  { label: 'Major Mono (ASCII)', value: 'var(--font-major-mono), monospace' },
  { label: 'Space Mono', value: 'var(--font-space-mono), monospace' },
  { label: 'IBM Plex Mono', value: 'var(--font-plex-mono), monospace' },
  { label: 'Bebas', value: 'var(--font-bebas), system-ui, sans-serif' },
  { label: 'Blackletter', value: 'var(--font-blackletter), serif' },
  { label: 'Glitch', value: 'var(--font-glitch), system-ui, sans-serif' },
  { label: 'System', value: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' },
];

export const BACKGROUND_WORDMARK_ALIGN_OPTIONS: { id: WordmarkAlign; label: string }[] = [
  { id: 'left', label: 'Left' },
  { id: 'center', label: 'Center' },
  { id: 'right', label: 'Right' },
];

/** A shipped wallpaper. `url` is the public path (spaces encoded). */
export interface BackgroundAsset {
  id: string;
  label: string;
  url: string;
  /** Approximate file size, shown as a load-weight hint in the picker. */
  weight: string;
}

export const SHIPPED_BACKGROUNDS: BackgroundAsset[] = [
  { id: 'eclipse-1', label: 'Eclipse I', url: '/backgrounds/eclipse%20bg-1.svg', weight: '0.4 MB' },
  { id: 'eclipse-3', label: 'Eclipse III', url: '/backgrounds/eclipse%20bg-3.png', weight: '40 KB' },
  { id: 'eclipse-4', label: 'Eclipse IV', url: '/backgrounds/eclipse%20bg-4.svg', weight: '2.6 MB' },
  { id: 'eclipse-5', label: 'Eclipse V', url: '/backgrounds/eclipse%20bg-5.svg', weight: '0.9 MB' },
];

export const CUSTOM_BACKGROUND_ID = 'custom';

export function shippedBackground(id: string): BackgroundAsset | undefined {
  return SHIPPED_BACKGROUNDS.find((b) => b.id === id);
}

// ── Persistence (localStorage: prefs; IndexedDB: custom bytes) ───────────────

export const BACKGROUND_STORAGE_KEY = 'be_background_v1';
const IDB_NAME = 'be_background';
const IDB_STORE = 'custom';
const IDB_KEY = 'active';

export function normalizeBackgroundPrefs(raw: unknown): BackgroundPrefs {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  const mode = MODES.includes(value.mode as BackgroundMode)
    ? (value.mode as BackgroundMode)
    : DEFAULT_BACKGROUND.mode;
  const preset = typeof value.preset === 'string' && value.preset.length > 0
    ? value.preset
    : DEFAULT_BACKGROUND.preset;
  const customKey = typeof value.customKey === 'string' ? value.customKey : '';
  const fit = FITS.includes(value.fit as BackgroundFit)
    ? (value.fit as BackgroundFit)
    : DEFAULT_BACKGROUND.fit;
  const scale = typeof value.scale === 'number' && Number.isFinite(value.scale)
    ? Math.min(300, Math.max(50, Math.round(value.scale)))
    : DEFAULT_BACKGROUND.scale;
  const positionX = typeof value.positionX === 'number' && Number.isFinite(value.positionX)
    ? Math.min(100, Math.max(0, Math.round(value.positionX)))
    : DEFAULT_BACKGROUND.positionX;
  const positionY = typeof value.positionY === 'number' && Number.isFinite(value.positionY)
    ? Math.min(100, Math.max(0, Math.round(value.positionY)))
    : DEFAULT_BACKGROUND.positionY;
  const dim = typeof value.dim === 'number' && Number.isFinite(value.dim)
    ? Math.min(100, Math.max(0, Math.round(value.dim)))
    : DEFAULT_BACKGROUND.dim;
  // A CSS color string, or '' to follow the theme. Kept as-is (validated later
  // in CSS); a non-string is dropped to the default.
  const solidFill = SOLID_FILLS.includes(value.solidFill as SolidFill)
    ? (value.solidFill as SolidFill)
    : DEFAULT_BACKGROUND.solidFill;
  const solidColor = typeof value.solidColor === 'string' ? value.solidColor : '';
  const solidColor2 = typeof value.solidColor2 === 'string' ? value.solidColor2 : '';
  const solidGradientType = GRADIENT_TYPES.includes(value.solidGradientType as SolidGradientType)
    ? (value.solidGradientType as SolidGradientType)
    : DEFAULT_BACKGROUND.solidGradientType;
  const solidGradientAngle = typeof value.solidGradientAngle === 'number' && Number.isFinite(value.solidGradientAngle)
    ? Math.min(360, Math.max(0, Math.round(value.solidGradientAngle)))
    : DEFAULT_BACKGROUND.solidGradientAngle;
  const solidPattern = SOLID_PATTERNS.includes(value.solidPattern as SolidPattern)
    ? (value.solidPattern as SolidPattern)
    : DEFAULT_BACKGROUND.solidPattern;
  const solidPatternOpacity = typeof value.solidPatternOpacity === 'number' && Number.isFinite(value.solidPatternOpacity)
    ? Math.min(100, Math.max(0, Math.round(value.solidPatternOpacity)))
    : DEFAULT_BACKGROUND.solidPatternOpacity;
  const solidPatternScale = typeof value.solidPatternScale === 'number' && Number.isFinite(value.solidPatternScale)
    ? Math.min(80, Math.max(4, Math.round(value.solidPatternScale)))
    : DEFAULT_BACKGROUND.solidPatternScale;
  // Landing text: off unless enabled. In solid mode the wordmark IS the
  // backdrop, so it is forced on (see `isWordmarkVisible`).
  const textEnabled = value.textEnabled === true;
  const text = typeof value.text === 'string'
    ? value.text.slice(0, MAX_WORDMARK_LENGTH)
    : DEFAULT_BACKGROUND.text;
  const textFont = typeof value.textFont === 'string' && value.textFont.length > 0
    ? value.textFont
    : DEFAULT_BACKGROUND.textFont;
  const textColor = typeof value.textColor === 'string' ? value.textColor : '';
  const textWeight = typeof value.textWeight === 'number' && Number.isFinite(value.textWeight)
    ? Math.min(900, Math.max(100, Math.round(value.textWeight / 100) * 100))
    : DEFAULT_BACKGROUND.textWeight;
  const textLetterSpacing = typeof value.textLetterSpacing === 'number' && Number.isFinite(value.textLetterSpacing)
    ? Math.min(0.5, Math.max(-0.1, value.textLetterSpacing))
    : DEFAULT_BACKGROUND.textLetterSpacing;
  const textLineHeight = typeof value.textLineHeight === 'number' && Number.isFinite(value.textLineHeight)
    ? Math.min(2, Math.max(0.7, value.textLineHeight))
    : DEFAULT_BACKGROUND.textLineHeight;
  const textWidth = typeof value.textWidth === 'number' && Number.isFinite(value.textWidth)
    ? Math.min(200, Math.max(50, Math.round(value.textWidth)))
    : DEFAULT_BACKGROUND.textWidth;
  const textItalic = value.textItalic === true;
  const textUppercase = value.textUppercase === true;
  const textScale = typeof value.textScale === 'number' && Number.isFinite(value.textScale)
    ? Math.min(40, Math.max(4, Math.round(value.textScale)))
    : DEFAULT_BACKGROUND.textScale;
  const textOpacity = typeof value.textOpacity === 'number' && Number.isFinite(value.textOpacity)
    ? Math.min(100, Math.max(0, Math.round(value.textOpacity)))
    : DEFAULT_BACKGROUND.textOpacity;
  const textPositionY = typeof value.textPositionY === 'number' && Number.isFinite(value.textPositionY)
    ? Math.min(100, Math.max(0, Math.round(value.textPositionY)))
    : DEFAULT_BACKGROUND.textPositionY;
  const textAlign = WORDMARK_ALIGNS.includes(value.textAlign as WordmarkAlign)
    ? (value.textAlign as WordmarkAlign)
    : DEFAULT_BACKGROUND.textAlign;
  const chatSurfaceEnabled = typeof value.chatSurfaceEnabled === 'boolean'
    ? value.chatSurfaceEnabled
    : DEFAULT_BACKGROUND.chatSurfaceEnabled;
  const chatSurfaceFill = CHAT_SURFACE_FILLS.includes(value.chatSurfaceFill as ChatSurfaceFill)
    ? (value.chatSurfaceFill as ChatSurfaceFill)
    : DEFAULT_BACKGROUND.chatSurfaceFill;
  const chatSurfaceColor = typeof value.chatSurfaceColor === 'string' ? value.chatSurfaceColor : DEFAULT_BACKGROUND.chatSurfaceColor;
  const chatSurfaceColorLight = typeof value.chatSurfaceColorLight === 'string' ? value.chatSurfaceColorLight : DEFAULT_BACKGROUND.chatSurfaceColorLight;
  const chatSurfaceColor2 = typeof value.chatSurfaceColor2 === 'string' ? value.chatSurfaceColor2 : '';
  const chatSurfaceOpacity = typeof value.chatSurfaceOpacity === 'number' && Number.isFinite(value.chatSurfaceOpacity)
    ? Math.min(100, Math.max(0, Math.round(value.chatSurfaceOpacity)))
    : DEFAULT_BACKGROUND.chatSurfaceOpacity;
  const chatBubbleColor = typeof value.chatBubbleColor === 'string' ? value.chatBubbleColor : '';
  const chatBubbleColorLight = typeof value.chatBubbleColorLight === 'string' ? value.chatBubbleColorLight : '';
  return {
    mode, preset, customKey, fit, scale, positionX, positionY, dim,
    solidFill, solidColor, solidColor2, solidGradientType, solidGradientAngle,
    solidPattern, solidPatternOpacity, solidPatternScale,
    textEnabled, text, textFont, textColor, textWeight, textLetterSpacing,
    textLineHeight, textWidth, textItalic, textUppercase,
    textScale, textOpacity, textPositionY, textAlign,
    chatSurfaceEnabled, chatSurfaceFill, chatSurfaceColor, chatSurfaceColorLight, chatSurfaceColor2, chatSurfaceOpacity,
    chatBubbleColor, chatBubbleColorLight,
  };
}

/**
 * Validate a preset's partial background snapshot and return only the keys it
 * actually supplied, so merging it over the live prefs never invents values and
 * a preset that only themes the wordmark leaves the user's wallpaper alone.
 * Invalid snapshots collapse to `undefined` (the preset then carries no
 * background and the panel leaves the current backdrop untouched).
 */
export function normalizePresetBackground(raw: unknown): Partial<BackgroundPrefs> | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const src = raw as Record<string, unknown>;
  const full = normalizeBackgroundPrefs({ ...DEFAULT_BACKGROUND, ...src });
  const out: Partial<BackgroundPrefs> = {};
  for (const key of Object.keys(DEFAULT_BACKGROUND) as (keyof BackgroundPrefs)[]) {
    if (key in src) {
      (out as Record<string, unknown>)[key] = full[key];
    }
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

export function loadBackgroundPrefs(): BackgroundPrefs {
  if (typeof window === 'undefined') return DEFAULT_BACKGROUND;
  try {
    const raw = window.localStorage.getItem(BACKGROUND_STORAGE_KEY);
    if (!raw) return DEFAULT_BACKGROUND;
    const prefs = normalizeBackgroundPrefs(JSON.parse(raw));
    return migrateLegacyLandingColor(prefs);
  } catch {
    return DEFAULT_BACKGROUND;
  }
}

/**
 * One-time fix-up for a stored ChatBot landing color that came from an OLD dark
 * theme preset (an accent-tinted grey). Now that dark landings defer to the
 * scheme-aware `#0a0b0b` default, such a stored value is cleared to empty so the
 * default applies. An explicit, deliberately-picked color (not in the retired
 * palette) is preserved.
 */
export function migrateLegacyLandingColor(prefs: BackgroundPrefs): BackgroundPrefs {
  if (prefs.mode !== 'solid' || prefs.solidFill !== 'flat') return prefs;
  const color = prefs.solidColor.trim().toLowerCase();
  if (!color || !LEGACY_DARK_LANDING_COLORS.includes(color)) return prefs;
  return { ...prefs, solidColor: '' };
}

function persistBackgroundPrefs(prefs: BackgroundPrefs): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(BACKGROUND_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function openDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === 'undefined') return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) db.createObjectStore(IDB_STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

/** Read the stored custom image data URL, or null when none is present. */
export async function loadCustomImage(): Promise<string | null> {
  const db = await openDb();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(IDB_STORE, 'readonly');
      const req = tx.objectStore(IDB_STORE).get(IDB_KEY);
      req.onsuccess = () => resolve(typeof req.result === 'string' ? req.result : null);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

/** Store (or, with null, delete) the custom image data URL. */
export async function saveCustomImage(dataUrl: string | null): Promise<boolean> {
  const db = await openDb();
  if (!db) return false;
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      const store = tx.objectStore(IDB_STORE);
      if (dataUrl) store.put(dataUrl, IDB_KEY);
      else store.delete(IDB_KEY);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    } catch {
      resolve(false);
    }
  });
}

// ── Image optimisation (client-side, before storing) ─────────────────────────
// Users add a picture straight off their computer; phone photos can be 10–20 MB.
// We downscale on a canvas to a wallpaper-sized edge and re-encode, so the
// stored payload stays small. SVG/GIF (vector/animated) are passed through.

const MAX_EDGE = 2560;
const MAX_BYTES = 4_000_000;
export const MAX_UPLOAD_BYTES = 30_000_000;

export function isVectorImage(type: string, name: string): boolean {
  return type === 'image/svg+xml' || /\.svg$/i.test(name);
}

/** Re-encode an image file to a downscaled, compressed data URL (or original). */
export function optimizeImageFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read the file.'));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        reject(new Error('Could not read the file.'));
        return;
      }
      // Vector or animated art must not be rasterised.
      if (isVectorImage(file.type, file.name)) {
        resolve(result);
        return;
      }
      const img = new Image();
      img.onerror = () => resolve(result);
      img.onload = () => {
        try {
          const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            resolve(result);
            return;
          }
          ctx.drawImage(img, 0, 0, w, h);
          const isPng = file.type === 'image/png';
          const out = canvas.toDataURL(isPng ? 'image/png' : 'image/jpeg', isPng ? undefined : 0.85);
          resolve(out.length > 0 ? out : result);
        } catch {
          resolve(result);
        }
      };
      img.src = result;
    };
    reader.readAsDataURL(file);
  });
}

/** Guard the stored payload after optimisation; returns a friendly error. */
export function customImageError(dataUrl: string): string | null {
  if (dataUrl.startsWith('data:image/svg')) return null;
  if (dataUrl.length > MAX_BYTES * 1.4) {
    return 'That image is still too large after optimisation. Try a smaller picture.';
  }
  return null;
}

// ── CSS resolution ───────────────────────────────────────────────────────────

export interface BackgroundCss {
  /** The wallpaper URL (as a CSS `url(...)`) / gradient layers, or `none`. */
  url: string;
  /** The flat fill color for the host element (`background-color`). `transparent`
   * when a gradient/image layer covers the whole box. A flat backdrop uses this
   * rather than a `linear-gradient(color, color)` so it is a genuine solid fill
   * — no gradient function at all. */
  color: string;
  /**
   * The flat fill color for DARK mode (`html.dark`). Matches {@link color} except
   * for a flat solid backdrop with no explicit pick, where it defaults to
   * {@link DEFAULT_SOLID_DARK_COLOR} instead of the theme background.
   */
  colorDark: string;
  /** `background-image` for the host element's *pattern* layer (`--page-bg-image`). */
  pageImage: string;
  /** `background-size` for the image layer (fit). */
  size: string;
  /** `background-repeat` for the image layer. */
  repeat: string;
  /** `background-position` for the image layer (focal X/Y). */
  position: string;
  /** Zoom multiplier for the image layer (1 = fit as-is). */
  zoom: number;
  /** Whether a scrim should be rendered (image modes only). */
  scrim: boolean;
  /**
   * Scrim as a valid `background-image` *layer*. A bare color is not a valid
   * `background-image` value and would invalidate the whole multi-layer
   * declaration, so this is a solid-color linear-gradient instead.
   */
  scrimImage: string;
  /** True when the theme's pattern should be suppressed (image mode). */
  suppressPattern: boolean;
}

function sizeForFit(fit: BackgroundFit): string {
  return fit === 'cover' ? 'cover' : fit === 'contain' ? 'contain' : 'auto';
}

function scrimColorFor(dim: number): string {
  const a = Math.min(1, Math.max(0, dim / 100));
  return `rgba(0,0,0,${a})`;
}

/** A scrim that is valid inside `background-image` (a color is not). */
function scrimImageFor(dim: number): string {
  return `linear-gradient(${scrimColorFor(dim)}, ${scrimColorFor(dim)})`;
}

/** The base fill color for a solid backdrop (theme background when empty). */
function solidBaseColor(prefs: BackgroundPrefs): string {
  return prefs.solidColor.trim() || 'var(--background)';
}

/**
 * The `background-image` stack for a solid backdrop. Flat = a solid-color
 * gradient (a bare color is not valid `background-image`). Gradient = a
 * two-color wash (second stop falls back to a brand tint). Pattern = a texture
 * (grid / dots / diagonal / ASCII) drawn in the brand tint over the base fill.
 * `--brand-rgb` is written by the theme store.
 */
function solidBackgroundImage(prefs: BackgroundPrefs): string {
  const base = solidBaseColor(prefs);
  if (prefs.solidFill === 'gradient') {
    const to = prefs.solidColor2.trim() || 'rgb(var(--brand-rgb) / 0.55)';
    if (prefs.solidGradientType === 'radial') {
      return `radial-gradient(circle at 50% 50%, ${to} 0%, ${base} 100%)`;
    }
    return `linear-gradient(${prefs.solidGradientAngle}deg, ${base} 0%, ${to} 100%)`;
  }
  if (prefs.solidFill === 'pattern') {
    const a = Math.min(1, Math.max(0, prefs.solidPatternOpacity / 100));
    const ink = `rgb(var(--brand-rgb) / ${a})`;
    const pitch = prefs.solidPatternScale;
    const half = Math.round(pitch / 2);
    switch (prefs.solidPattern) {
      case 'dots':
        return `radial-gradient(${ink} ${Math.max(1, half)}px, transparent ${half + 0.5}px), linear-gradient(${base}, ${base})`;
      case 'diagonal':
        return `repeating-linear-gradient(135deg, ${ink} 0 1px, transparent 1px ${pitch}px), linear-gradient(${base}, ${base})`;
      case 'ascii': {
        // A faint character-cell lattice: a 0°/90° line grid at the pattern
        // pitch, reading as a terminal/ASCII texture behind the wordmark.
        const cell = `repeating-linear-gradient(0deg, ${ink} 0 1px, transparent 1px ${pitch}px), repeating-linear-gradient(90deg, ${ink} 0 1px, transparent 1px ${pitch}px)`;
        return `${cell}, linear-gradient(${base}, ${base})`;
      }
      case 'grid':
      default:
        return `linear-gradient(${ink} 1px, transparent 1px), linear-gradient(90deg, ${ink} 1px, transparent 1px), linear-gradient(${base}, ${base})`;
    }
  }
  return `linear-gradient(${base}, ${base})`;
}

/** The `background-size` list matching {@link solidBackgroundImage} layers. */
function solidBackgroundSize(prefs: BackgroundPrefs): string {
  if (prefs.solidFill !== 'pattern') return '100% 100%';
  const p = `${prefs.solidPatternScale}px ${prefs.solidPatternScale}px`;
  switch (prefs.solidPattern) {
    case 'dots':
      return `${p}, 100% 100%`;
    case 'grid':
      return `${p}, ${p}, 100% 100%`;
    case 'diagonal':
    case 'ascii':
    default:
      return '100% 100%';
  }
}

/**
 * Resolve prefs + the custom data URL into the concrete CSS the backdrop layer
 * needs.
 *
 * Semantics:
 *   * `image` → the theme pattern is suppressed so the wallpaper reads clean,
 *               and the wallpaper layer is fed the image + scrim.
 *   * `solid` → the layer is filled with a flat color, gradient or textured
 *               pattern (base color falls back to the theme `--background`).
 *
 * Fit picks `cover`/`contain`/`auto`; `scale` is a separate zoom multiplier and
 * `positionX/Y` set the focal point, so the two can be combined freely.
 */
export function resolveBackgroundCss(
  prefs: BackgroundPrefs,
  customUrl: string | null,
): BackgroundCss {
  const scrimImage = scrimImageFor(prefs.dim);
  const zoom = Math.min(3, Math.max(0.5, prefs.scale / 100));
  const position = `${prefs.positionX}% ${prefs.positionY}%`;
  if (prefs.mode === 'solid') {
    // A flat backdrop is a genuine solid fill: the color goes on the host's
    // `background-color` (via `--app-bg-color`) and NO `background-image` is
    // emitted, so the ChatBot page never paints a gradient function. Gradient /
    // pattern fills still use layered `background-image`; those layers cover the
    // whole box, so the host color stays transparent beneath them.
    const flat = prefs.solidFill === 'flat';
    return {
      url: flat ? 'none' : solidBackgroundImage(prefs),
      color: flat ? solidBaseColor(prefs) : 'transparent',
      colorDark: flat ? prefs.solidColor.trim() || DEFAULT_SOLID_DARK_COLOR : 'transparent',
      pageImage: 'none',
      size: solidBackgroundSize(prefs),
      repeat: 'no-repeat',
      position: 'center',
      zoom: 1,
      scrim: false,
      scrimImage,
      suppressPattern: true,
    };
  }
  const asset = prefs.preset === CUSTOM_BACKGROUND_ID ? null : shippedBackground(prefs.preset);
  const url = asset?.url ?? (customUrl || null);
  if (!url) {
    return { url: 'none', color: 'transparent', colorDark: 'transparent', pageImage: 'none', size: 'auto', repeat: 'no-repeat', position: 'center', zoom: 1, scrim: false, scrimImage, suppressPattern: false };
  }
  return {
    url: `url("${url}")`,
    color: 'transparent',
    colorDark: 'transparent',
    // Suppress the theme pattern so the wallpaper is the only backdrop.
    pageImage: 'none',
    size: sizeForFit(prefs.fit),
    repeat: prefs.fit === 'tile' ? 'repeat' : 'no-repeat',
    position,
    zoom,
    scrim: true,
    scrimImage,
    suppressPattern: true,
  };
}

/**
 * Whether the giant landing wordmark should paint. Solid mode always shows it
 * (the wordmark IS the backdrop); image mode only when the user opted in. Empty
 * text never paints.
 */
export function isWordmarkVisible(prefs: BackgroundPrefs): boolean {
  if (prefs.text.trim().length === 0) return false;
  return prefs.mode === 'solid' || prefs.textEnabled;
}

/** The concrete CSS for the chat-conversation surface. */
export interface ChatSurfaceCss {
  /** A CSS `background` value for LIGHT mode (a color or a gradient). */
  light: string;
  /** A CSS `background` value for DARK mode (a color or a gradient). */
  dark: string;
  /** Opacity 0–1, so the page backdrop can show through. */
  opacity: number;
}

/** One scheme's chat-surface background: a flat color, or a two-color gradient. */
function chatSurfaceBackground(prefs: BackgroundPrefs, color: string): string {
  const base = color.trim() || 'var(--card)';
  if (prefs.chatSurfaceFill === 'gradient') {
    const to = prefs.chatSurfaceColor2.trim() || 'rgb(var(--brand-rgb) / 0.55)';
    return `linear-gradient(160deg, ${base} 0%, ${to} 100%)`;
  }
  return base;
}

/**
 * Resolve the chat-conversation surface, or null when it is off. Returns a
 * scheme-specific `background` value for light and dark mode, so the surface
 * follows the active theme (dark `#0a0b0b` / light matte off-white by default).
 * Painted by `.chat-surface-layer` (globals.css) from these vars.
 */
export function resolveChatSurfaceCss(prefs: BackgroundPrefs): ChatSurfaceCss | null {
  if (!prefs.chatSurfaceEnabled) return null;
  const opacity = Math.min(1, Math.max(0, prefs.chatSurfaceOpacity / 100));
  return {
    dark: chatSurfaceBackground(prefs, prefs.chatSurfaceColor),
    light: chatSurfaceBackground(prefs, prefs.chatSurfaceColorLight),
    opacity,
  };
}

/** The concrete CSS for the prompt-bubble fill (always present; falls back to a
 *  neutral foreground tint). */
export interface ChatBubbleCss {
  /** A CSS `background` value for LIGHT mode. */
  light: string;
  /** A CSS `background` value for DARK mode. */
  dark: string;
}

/** The neutral bubble tint used when the user has not picked a color. */
export const DEFAULT_CHAT_BUBBLE_BG = 'color-mix(in srgb, var(--foreground) 10%, transparent)';
/** Dark-mode prompt bubble: a dedicated dark charcoal (#2e2e2e) so the user's
 *  own prompts sit just clear of the near-black conversation surface without
 *  the lighter grey of the old 24% foreground tint. */
export const DEFAULT_CHAT_BUBBLE_BG_DARK = '#2e2e2e';

/**
 * Resolve the prompt-bubble fill for light and dark mode. Empty picks fall back
 * to {@link DEFAULT_CHAT_BUBBLE_BG}, so the shipped look is unchanged.
 */
export function resolveChatBubbleCss(prefs: BackgroundPrefs): ChatBubbleCss {
  return {
    light: prefs.chatBubbleColorLight.trim() || DEFAULT_CHAT_BUBBLE_BG,
    dark: prefs.chatBubbleColor.trim() || DEFAULT_CHAT_BUBBLE_BG_DARK,
  };
}

// ── DOM application ──────────────────────────────────────────────────────────

/**
 * Push the resolved background onto the document as CSS variables. Purely a
 * custom-property write (no stylesheet), so it composes with the theme store's
 * managed `<style>` and survives theme changes. `--page-bg-image` is overridden
 * to suppress the theme pattern so the wallpaper / solid fill is the only
 * backdrop on the ChatBot landing.
 */
export function applyBackgroundToDocument(prefs: BackgroundPrefs, customUrl: string | null): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const css = resolveBackgroundCss(prefs, customUrl);
  root.style.setProperty('--page-bg-image', css.pageImage);
  root.style.setProperty('--app-bg-color', css.color);
  // Dark-mode fill, so the landing defaults to a near-black on every theme while
  // light mode follows the theme background.
  root.style.setProperty('--app-bg-color-dark', css.colorDark);
  root.style.setProperty('--app-bg-image', css.url);
  root.style.setProperty('--app-bg-size', css.size);
  root.style.setProperty('--app-bg-repeat', css.repeat);
  root.style.setProperty('--app-bg-position', css.position);
  root.style.setProperty('--app-bg-zoom', String(css.zoom));
  root.style.setProperty('--app-bg-scrim', css.scrim ? css.scrimImage : 'none');

  // Chat-conversation surface (independent of the page backdrop). Light/dark
  // pair so it follows the scheme.
  const surface = resolveChatSurfaceCss(prefs);
  root.style.setProperty('--chat-surface-bg-light', surface ? surface.light : 'transparent');
  root.style.setProperty('--chat-surface-bg-dark', surface ? surface.dark : 'transparent');
  root.style.setProperty('--chat-surface-opacity', String(surface ? surface.opacity : 0));

  // Prompt-bubble fill (light/dark pair). Defaults to a neutral tint.
  const bubble = resolveChatBubbleCss(prefs);
  root.style.setProperty('--chat-bubble-bg-light', bubble.light);
  root.style.setProperty('--chat-bubble-bg-dark', bubble.dark);
}

function clearBackgroundFromDocument(): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  for (const name of [
    '--page-bg-image', '--app-bg-color', '--app-bg-color-dark', '--app-bg-image', '--app-bg-size', '--app-bg-repeat',
    '--app-bg-position', '--app-bg-zoom', '--app-bg-scrim',
    '--chat-surface-bg-light', '--chat-surface-bg-dark', '--chat-surface-opacity',
    '--chat-bubble-bg-light', '--chat-bubble-bg-dark',
  ]) {
    root.style.removeProperty(name);
  }
}

// ── Store ────────────────────────────────────────────────────────────────────

export interface BackgroundStore {
  prefs: BackgroundPrefs;
  hydrated: boolean;
  /** The custom image data URL, once loaded from IndexedDB. */
  customUrl: string | null;
  /** True while saving an upload to IndexedDB. */
  saving: boolean;
  hydrate: () => Promise<void>;
  /** Patch prefs; applies immediately and persists. */
  setPrefs: (patch: Partial<BackgroundPrefs>) => void;
  /**
   * Show a preset's partial background (merged over the live prefs) on the
   * document WITHOUT persisting — the live/full-screen theme preview uses this
   * so selecting a theme preset also auditions its ChatBot backdrop. Reverting
   * is `cancelPreview`.
   */
  preview: (patch: Partial<BackgroundPrefs>) => void;
  /** Discard any active background preview, restoring the saved prefs. */
  cancelPreview: () => void;
  /** True while a non-persisted preview is on the document. */
  previewing: boolean;
  /**
   * The prefs to render from: the previewed snapshot while a preview is active,
   * otherwise the saved prefs. React consumers (the giant wordmark) read this so
   * a preset preview updates the glyphs, not just the CSS-variable layer.
   */
  previewPrefs: BackgroundPrefs | null;
  /** Optimise + store a user image and switch to it. Returns an error string. */
  setCustomImage: (file: File) => Promise<string | null>;
  /** Forget the stored custom image and fall back to a shipped preset. */
  clearCustomImage: () => Promise<void>;
  /** Restore shipped defaults. */
  reset: () => void;
}

export const useBackgroundStore = create<BackgroundStore>((set, get) => {
  /** Apply + persist the current prefs. */
  const apply = (prefs: BackgroundPrefs, customUrl = get().customUrl) => {
    applyBackgroundToDocument(prefs, customUrl);
  };

  const commit = (patch: Partial<BackgroundPrefs>) => {
    const next = normalizeBackgroundPrefs({ ...get().prefs, ...patch });
    set({ prefs: next });
    persistBackgroundPrefs(next);
    apply(next);
  };

  return {
    prefs: DEFAULT_BACKGROUND,
    hydrated: false,
    customUrl: null,
    saving: false,
    previewing: false,
    previewPrefs: null,

    hydrate: async () => {
      const prefs = loadBackgroundPrefs();
      let customUrl: string | null = null;
      if (prefs.mode === 'image' && prefs.preset === CUSTOM_BACKGROUND_ID) {
        customUrl = await loadCustomImage();
      }
      set({ prefs, customUrl, hydrated: true });
      apply(prefs, customUrl);
    },

    setPrefs: (patch) => {
      // An explicit edit supersedes any active preset preview, so a manual
      // change is not reverted by a later cancelPreview.
      set({ previewing: false, previewPrefs: null });
      commit(patch);
    },

    preview: (patch) => {
      // Merge over the SAVED prefs (never mutated by a preview), so
      // re-previewing a different preset never compounds on a previous one.
      const next = normalizeBackgroundPrefs({ ...get().prefs, ...patch });
      apply(next);
      set({ previewing: true, previewPrefs: next });
    },

    cancelPreview: () => {
      if (!get().previewing) return;
      apply(get().prefs);
      set({ previewing: false, previewPrefs: null });
    },

    setCustomImage: async (file) => {
      if (file.size > MAX_UPLOAD_BYTES) {
        return 'That image is larger than 30 MB. Please choose a smaller picture.';
      }
      set({ saving: true });
      try {
        const dataUrl = await optimizeImageFile(file);
        const error = customImageError(dataUrl);
        if (error) return error;
        const ok = await saveCustomImage(dataUrl);
        if (!ok) return 'Could not store the image on this device (storage unavailable).';
        set({ customUrl: dataUrl, saving: false });
        commit({ mode: 'image', preset: CUSTOM_BACKGROUND_ID });
        return null;
      } catch (err) {
        set({ saving: false });
        return err instanceof Error ? err.message : 'Could not process that image.';
      }
    },

    clearCustomImage: async () => {
      await saveCustomImage(null);
      set({ customUrl: null });
      if (get().prefs.preset === CUSTOM_BACKGROUND_ID) {
        commit({ preset: DEFAULT_BACKGROUND.preset, mode: 'image' });
      }
    },

    reset: () => {
      set({ prefs: DEFAULT_BACKGROUND, customUrl: get().customUrl });
      persistBackgroundPrefs(DEFAULT_BACKGROUND);
      apply(DEFAULT_BACKGROUND);
    },
  };
});

/**
 * Hydrate the background from storage and apply it, once, client-side. The
 * theme store re-applies it after every theme write (see `refreshBackground`),
 * so the wallpaper-suppression var stays authoritative over the theme's own
 * `--page-bg-image` without a store-to-store subscription.
 */
export function useHydrateBackground() {
  const hydrate = useBackgroundStore((s) => s.hydrate);
  const hydrated = useBackgroundStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) void hydrate();
  }, [hydrated, hydrate]);
}

/** True when any non-default backdrop is configured (drives the "Custom" badge). */
export function isBackgroundCustomized(prefs: BackgroundPrefs): boolean {
  return prefs.mode !== DEFAULT_BACKGROUND.mode;
}

export { clearBackgroundFromDocument };

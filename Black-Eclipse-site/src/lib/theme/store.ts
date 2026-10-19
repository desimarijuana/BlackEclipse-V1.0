// ── Eclipse theme store ──────────────────────────────────────────────────────
// Client-side zustand store holding the user's centralized customization. It
// hydrates from localStorage after mount (matching the Aurora / sidebar /
// chart-palette / i18n stores so SSR stays stable) and applies the flattened
// tokens to <html> as inline custom properties on every change, so the whole
// app recolors live with no component-level plumbing.
//
// Important: when the user has NOT customized anything we do not write inline
// overrides at all, so the shipped `globals.css` tokens (including the
// dark/light switch) keep working untouched. Overrides exist only once the
// user opts in via Settings › Customization.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import { sdkUnlockHeaders } from '@/lib/sdk';
import {
  DEFAULT_ECLIPSE_THEME,
  BRAND_MARK_SRC,
  STRUCTURAL_THEME_VARS,
  normalizeTheme,
  themeCssVars,
  type EclipseTheme,
  type ThemeColors,
  type ThemeGlass,
  type ThemeSidebar,
} from './tokens';
import { DEFAULT_CHART_PALETTE, normalizeChartPalette, type ChartPalette } from '@/lib/chart-palette';
import { useChartPaletteStore } from '@/lib/chart-palette-store';
import {
  applyBackgroundToDocument,
  normalizePresetBackground,
  useBackgroundStore,
  type BackgroundPrefs,
} from '@/lib/backgrounds';
import { useAuroraPaletteStore } from '@/lib/aurora/store';
import { parseAuroraPalette } from '@/lib/aurora/theme';
import { type AuroraPalette } from '@/lib/aurora-sentiment';
import { composeDocumentTitle } from '@/lib/notifications/title';

export const THEME_STORAGE_KEY = 'be_theme_v1';
export const THEME_PRESETS_STORAGE_KEY = 'be_theme_presets_v1';
const STYLE_ELEMENT_ID = 'eclipse-theme-overrides';

/** A named theme the user saved themselves. */
export interface UserThemePreset {
  id: string;
  label: string;
  theme: EclipseTheme;
  /**
   * The chart/heatmap palette captured alongside the theme, so re-applying a
   * preset restores candles, line primary and heatmap colors too. Optional for
   * presets saved before this field existed.
   */
  chartPalette?: ChartPalette;
  /**
   * The ChatBot-backdrop snapshot captured with the theme (wallpaper / solid
   * fill + giant wordmark), so re-applying a preset restores the WHOLE look.
   * Optional for presets saved before this field existed.
   */
  background?: Partial<BackgroundPrefs>;
  /** The Aurora-glow palette captured with the theme, so re-applying a preset
   *  restores the ambient glow too. Optional for presets saved before it existed. */
  aurora?: AuroraPalette;
  createdAt: number;
}

function loadTheme(): EclipseTheme | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (!raw) return null;
    return normalizeTheme(JSON.parse(raw));
  } catch {
    return null;
  }
}

function loadUserPresets(): UserThemePreset[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(THEME_PRESETS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((p) => p && typeof p === 'object')
      .map((p) => ({
        id: String(p.id ?? ''),
        label: String(p.label ?? 'Custom'),
        createdAt: Number(p.createdAt) || Date.now(),
        theme: normalizeTheme(p.theme),
        chartPalette: p.chartPalette ? normalizeChartPalette(p.chartPalette) : undefined,
        background: normalizePresetBackground(p.background),
        aurora: p.aurora ? parseAuroraPalette(p.aurora) : undefined,
      }))
      .filter((p) => p.id.length > 0);
  } catch {
    return [];
  }
}

function persistUserPresets(presets: UserThemePreset[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(THEME_PRESETS_STORAGE_KEY, JSON.stringify(presets));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function makePresetId(): string {
  return `u_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/** The chart/heatmap palette currently in effect (preview overlay included). */
function currentChartPalette(): ChartPalette {
  const s = useChartPaletteStore.getState();
  return s.previewPalette ?? s.palette ?? DEFAULT_CHART_PALETTE;
}

/** The ChatBot backdrop currently in effect, captured with a saved preset. */
function currentBackground(): Partial<BackgroundPrefs> {
  return { ...useBackgroundStore.getState().prefs };
}

/** Push a preset's backdrop snapshot onto the background store; no-op when none. */
function restoreBackground(background: Partial<BackgroundPrefs> | undefined): void {
  if (!background) return;
  useBackgroundStore.getState().setPrefs(background);
}

/**
 * Re-paint the saved backdrop after a theme write, so the background's
 * wallpaper-suppression / solid-fill vars stay authoritative over the theme's
 * own `--page-bg-image`. This replaces the old store-to-store subscription that
 * made the two modules import each other.
 */
export function refreshBackground(): void {
  const s = useBackgroundStore.getState();
  applyBackgroundToDocument(s.prefs, s.customUrl);
}

// A theme is "light" when it is NOT the shipped dark look. The `scheme` token
// drives both the `dark` class and which token block the colors land in, so the
// two can never disagree. Legacy/imported themes without a scheme default to
// dark (normalizeTheme fills it).
function isLightTheme(theme: EclipseTheme): boolean {
  return theme.scheme === 'light';
}

function buildOverrideCss(theme: EclipseTheme): string {
  const vars = themeCssVars(theme);
  const structural: string[] = [];
  const colors: string[] = [];
  for (const [name, value] of Object.entries(vars)) {
    (STRUCTURAL_THEME_VARS.has(name) ? structural : colors).push(`${name}: ${value};`);
  }
  // Colors are scoped to the active scheme so the `.dark` class and the token
  // block always agree: a dark theme writes `html.dark{}` (outranking the plain
  // `.dark` block in globals.css), a light theme writes `html:not(.dark){}` so
  // it outranks `:root`. Typography/shape stay global under `:root`.
  const colorBlock = isLightTheme(theme)
    ? `html:not(.dark){${colors.join('')}}`
    : `html.dark{${colors.join('')}}`;
  return `:root{${structural.join('')}}${colorBlock}`;
}

/**
 * Apply tokens through a managed <style> element so custom colors override the
 * shipped tokens while remaining scoped to dark mode. The last-applied CSS is
 * remembered so repeated applies with no change (e.g. a color picker emitting
 * the same value) skip the expensive app-wide restyle entirely.
 */
let lastAppliedCss: string | null = null;

export function applyThemeToDocument(theme: EclipseTheme) {
  if (typeof document === 'undefined') return;
  let el = document.getElementById(STYLE_ELEMENT_ID) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement('style');
    el.id = STYLE_ELEMENT_ID;
    document.head.appendChild(el);
  }
  const css = buildOverrideCss(theme);
  if (css !== lastAppliedCss) {
    el.textContent = css;
    lastAppliedCss = css;
  }
  const root = document.documentElement;
  // The scheme is the source of truth for the `dark` class. Nothing else in the
  // app toggles it (it is seeded `dark` in layout.tsx to prevent FOUC); the
  // store owns it from here so a white preset actually activates the
  // `html:not(.dark)` recipes in globals.css.
  root.classList.toggle('dark', !isLightTheme(theme));
  root.classList.add('theme-customized');
  root.classList.toggle('theme-no-anim', !theme.animations);
  root.classList.toggle('theme-no-glow', !theme.glow);
  // The token-driven glass override (which unifies the per-tier recipes) only
  // kicks in when the user changed glass settings or turned glass off. While
  // they match the shipped defaults, the hardcoded tier hierarchy stays intact.
  // Sidebar changes are excluded: they only ever drive the sidebar's own tokens.
  const dg = DEFAULT_ECLIPSE_THEME.glass;
  const surfacesTouched =
    !theme.glass.enabled ||
    theme.glass.blur !== dg.blur ||
    theme.glass.opacity !== dg.opacity ||
    theme.glass.tint !== dg.tint ||
    theme.shadow !== DEFAULT_ECLIPSE_THEME.shadow;
  root.classList.toggle('theme-glass-active', surfacesTouched);
  root.classList.toggle('theme-glass-off', !theme.glass.enabled);
}

/** Remove overrides so globals.css defaults take over again. */
function clearThemeFromDocument() {
  if (typeof document === 'undefined') return;
  document.getElementById(STYLE_ELEMENT_ID)?.remove();
  lastAppliedCss = null;
  document.documentElement.classList.remove(
    'theme-customized', 'theme-no-anim', 'theme-no-glow', 'theme-glass-active', 'theme-glass-off',
  );
  // The shipped default is dark; restore it so "Reset to Eclipse Default" from a
  // light scheme does not leave the app stuck in `html:not(.dark)`.
  document.documentElement.classList.add('dark');
}

function applyFavicon(theme: EclipseTheme) {
  if (typeof document === 'undefined') return;
  const href = theme.faviconUrl || BRAND_MARK_SRC;
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.href = href;
}

/** Keep the document title branded with the custom app name. */
function applyDocumentTitle(theme: EclipseTheme) {
  if (typeof document === 'undefined') return;
  const suffix = '\u2014 AI Stock Research & Screening Platform';
  // Compose through the notification prefix so an unread count is never
  // silently dropped by a branding title write.
  document.title = composeDocumentTitle(`${theme.appName} ${suffix}`);
}

/** Write this origin's instant first-paint cache only (no server round-trip). */
function persistLocal(theme: EclipseTheme) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(theme));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/**
 * Mirror the theme to the server so it is APP-WIDE. The DB is the source of
 * truth; every browser origin / device reads it back in `hydrateFromServer`.
 * `localStorage` stays only as this origin's first-paint cache. Best effort — a
 * failed write (offline, unauthenticated) never blocks the local edit; the next
 * successful edit re-syncs.
 */
function pushThemeToServer(theme: EclipseTheme) {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;
  const body = JSON.stringify({ theme });
  // `fetch(..., { keepalive: true })` is capped at 64 KiB by the browser (the
  // spec limit across all in-flight keepalive requests). A theme that carries an
  // embedded logo/favicon data URL easily exceeds that, so the request is
  // rejected outright and the app-wide theme silently never receives the logo —
  // then `hydrateFromServer` adopts the older, logo-less server theme on the next
  // load and the logo "keeps disappearing". Only use keepalive for small themes
  // that can actually survive a page unload; send larger ones as a normal
  // request (which may be aborted on unload, but the local cache still holds it
  // and the next edit re-syncs).
  const keepalive = body.length < 60_000;
  void window
    .fetch('/api/theme', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', ...sdkUnlockHeaders() },
      body,
      keepalive,
    })
    .catch(() => { /* local cache still holds it */ });
}

function clearServerTheme() {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;
  void window
    .fetch('/api/theme', { method: 'DELETE', headers: { ...sdkUnlockHeaders() }, keepalive: true })
    .catch(() => {});
}

function persist(theme: EclipseTheme) {
  persistLocal(theme);
  pushThemeToServer(theme);
}

export interface ThemeStore {
  theme: EclipseTheme;
  hydrated: boolean;
  /** True once the user has overrides stored (drives the "Custom" badge). */
  customized: boolean;
  /** User-saved themes, newest first. */
  userPresets: UserThemePreset[];
  /** When set, the document is showing a non-persisted preview of this theme. */
  previewTheme: EclipseTheme | null;
  /**
   * Full-screen preview mode: the Settings modal is closed so the user can
   * interact with the REAL app already wearing the preview, with a floating
   * Apply / Discard bar. Ephemeral — never persisted.
   */
  previewMode: boolean;
  /** Enter/leave full-screen preview mode. */
  setPreviewMode: (v: boolean) => void;
  hydrate: () => void;
  /**
   * Adopt the APP-WIDE theme from the server (the source of truth), if one is
   * saved. Runs after `hydrate` on every boot so every origin/device converges
   * on the same look regardless of its local cache.
   */
  hydrateFromServer: () => Promise<void>;
  /** Patch top-level fields (appName, fonts, radius, density, toggles, …). */
  setTheme: (patch: Partial<Omit<EclipseTheme, 'colors'>>) => void;
  /** Patch a single color token. */
  setColor: (key: keyof ThemeColors, value: string) => void;
  /** Patch the glass surface settings. */
  setGlass: (patch: Partial<ThemeGlass>) => void;
  /** Patch the dedicated sidebar surface settings. */
  setSidebar: (patch: Partial<ThemeSidebar>) => void;
  /**
   * Replace the theme wholesale (preset application). An optional background
   * snapshot is pushed to the background store in the same step, so applying a
   * preset restores its ChatBot backdrop alongside its tokens.
   */
  applyPreset: (theme: EclipseTheme, background?: Partial<BackgroundPrefs>, aurora?: AuroraPalette) => void;
  /**
   * Apply a theme to the document WITHOUT persisting it. Used by the Settings
   * preview toggle so the whole app can be auditioned before committing.
   */
  preview: (theme: EclipseTheme) => void;
  /** Discard any active preview and restore the saved theme. */
  cancelPreview: () => void;
  /** Persist the active preview (no-op when none). */
  commitPreview: () => void;
  /** Save the current theme as a named user preset; returns its id. */
  saveUserPreset: (label: string) => string;
  /** Overwrite an existing user preset with the current theme. */
  updateUserPreset: (id: string) => void;
  /**
   * Apply a saved user preset in one step — its theme AND the chart/heatmap
   * palette captured with it (falls back to theme-only for legacy presets).
   */
  applyUserPreset: (id: string) => void;
  /** Rename a user preset. */
  renameUserPreset: (id: string, label: string) => void;
  /** Delete a user preset. */
  deleteUserPreset: (id: string) => void;
  /** Replace a user preset's colors with the given theme (used by import). */
  importPreset: (theme: EclipseTheme, background?: Partial<BackgroundPrefs>) => void;
  /** Restore the shipped Eclipse default and drop inline overrides. */
  reset: () => void;
}

function commit(theme: EclipseTheme): EclipseTheme {
  const clean = normalizeTheme(theme);
  applyThemeToDocument(clean);
  applyFavicon(clean);
  applyDocumentTitle(clean);
  persist(clean);
  // Re-assert the saved backdrop so its suppression / solid-fill vars stay
  // authoritative over the theme's own `--page-bg-image`.
  refreshBackground();
  return clean;
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  theme: DEFAULT_ECLIPSE_THEME,
  hydrated: false,
  customized: false,
  userPresets: [],
  previewTheme: null,
  previewMode: false,

  setPreviewMode: (v) => set({ previewMode: v }),

  hydrate: () => {
    const stored = loadTheme();
    const userPresets = loadUserPresets();
    if (stored) {
      applyThemeToDocument(stored);
      applyFavicon(stored);
      applyDocumentTitle(stored);
      set({ theme: stored, hydrated: true, customized: true, userPresets });
    } else {
      set({ hydrated: true, customized: false, userPresets });
    }
  },

  hydrateFromServer: async () => {
    if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;
    let remote: EclipseTheme | null = null;
    let initialized = false;
    try {
      const res = await window.fetch('/api/theme', { method: 'GET' });
      if (!res.ok) return;
      const data = (await res.json().catch(() => null)) as
        | { theme?: unknown; initialized?: boolean }
        | null;
      remote = data && data.theme ? normalizeTheme(data.theme) : null;
      initialized = Boolean(data?.initialized);
    } catch {
      return; // server unreachable — keep this origin's cached theme
    }
    if (remote) {
      applyThemeToDocument(remote);
      applyFavicon(remote);
      applyDocumentTitle(remote);
      persistLocal(remote); // refresh this origin's instant first-paint cache
      set({ theme: remote, hydrated: true, customized: true });
    } else if (initialized) {
      // The app-wide theme was explicitly reset elsewhere → the shipped default
      // applies everywhere. Only a *successful, initialized* null clears local.
      if (get().customized) {
        clearThemeFromDocument();
        applyFavicon(DEFAULT_ECLIPSE_THEME);
        if (typeof window !== 'undefined') {
          try {
            window.localStorage.removeItem(THEME_STORAGE_KEY);
          } catch {
            /* ignore */
          }
        }
        set({ theme: DEFAULT_ECLIPSE_THEME, customized: false });
      }
    } else if (get().customized) {
      // First run of the app-wide theme: a pre-existing per-origin theme is
      // MIGRATED up to the server instead of being wiped, so the user keeps the
      // look they had. From then on every origin/device adopts it.
      pushThemeToServer(get().theme);
    }
  },

  setTheme: (patch) => {
    const next = normalizeTheme({ ...get().theme, ...patch });
    set({ theme: commit(next), customized: true });
  },

  setColor: (key, value) => {
    const next = normalizeTheme({
      ...get().theme,
      colors: { ...get().theme.colors, [key]: value },
    });
    set({ theme: commit(next), customized: true });
  },

  setGlass: (patch) => {
    const next = normalizeTheme({
      ...get().theme,
      glass: { ...get().theme.glass, ...patch },
    });
    set({ theme: commit(next), customized: true });
  },

  setSidebar: (patch) => {
    const next = normalizeTheme({
      ...get().theme,
      sidebar: { ...get().theme.sidebar, ...patch },
    });
    set({ theme: commit(next), customized: true });
  },

  applyPreset: (theme, background, aurora) => {
    restoreBackground(background);
    if (aurora) useAuroraPaletteStore.getState().setPalette(aurora);
    set({ theme: commit(theme), customized: true, previewTheme: null });
  },

  preview: (theme) => {
    const clean = normalizeTheme(theme);
    // Apply to the document for live auditioning, but do NOT persist.
    applyThemeToDocument(clean);
    applyDocumentTitle(clean);
    set({ previewTheme: clean });
  },

  cancelPreview: () => {
    const current = get().theme;
    applyThemeToDocument(current);
    applyFavicon(current);
    applyDocumentTitle(current);
    set({ previewTheme: null, previewMode: false });
  },

  commitPreview: () => {
    const preview = get().previewTheme;
    if (!preview) return;
    set({ theme: commit(preview), customized: true, previewTheme: null, previewMode: false });
  },

  saveUserPreset: (label) => {
    const id = makePresetId();
    const preset: UserThemePreset = {
      id,
      label: label.trim() || 'My Theme',
      theme: normalizeTheme(get().theme),
      chartPalette: currentChartPalette(),
      background: currentBackground(),
      aurora: useAuroraPaletteStore.getState().palette,
      createdAt: Date.now(),
    };
    const userPresets = [preset, ...get().userPresets];
    persistUserPresets(userPresets);
    set({ userPresets });
    return id;
  },

  updateUserPreset: (id) => {
    const userPresets = get().userPresets.map((p) =>
      p.id === id
        ? {
            ...p,
            theme: normalizeTheme(get().theme),
            chartPalette: currentChartPalette(),
            background: currentBackground(),
            aurora: useAuroraPaletteStore.getState().palette,
            createdAt: Date.now(),
          }
        : p,
    );
    persistUserPresets(userPresets);
    set({ userPresets });
  },

  applyUserPreset: (id) => {
    const preset = get().userPresets.find((p) => p.id === id);
    if (!preset) return;
    get().applyPreset(preset.theme, preset.background, preset.aurora);
    if (preset.chartPalette) {
      useChartPaletteStore.getState().setPalette(preset.chartPalette);
    }
  },

  renameUserPreset: (id, label) => {
    const userPresets = get().userPresets.map((p) =>
      p.id === id ? { ...p, label: label.trim() || p.label } : p,
    );
    persistUserPresets(userPresets);
    set({ userPresets });
  },

  deleteUserPreset: (id) => {
    const userPresets = get().userPresets.filter((p) => p.id !== id);
    persistUserPresets(userPresets);
    set({ userPresets });
  },

  importPreset: (theme, background) => {
    // Import stores a new named user preset rather than replacing the active
    // theme, so an import is always non-destructive.
    get().applyPreset(theme, background);
    get().saveUserPreset(theme.appName || 'Imported Theme');
  },

  reset: () => {
    clearThemeFromDocument();
    applyFavicon(DEFAULT_ECLIPSE_THEME);
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(THEME_STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
    // Reset the APP-WIDE theme too, so every origin/device returns to default.
    clearServerTheme();
    // Restore the shipped backdrop too, so "Reset to Eclipse Default" resets the
    // ChatBot landing alongside the tokens.
    useBackgroundStore.getState().reset();
    set({ theme: DEFAULT_ECLIPSE_THEME, customized: false });
  },
}));

/** Hydrate the theme from localStorage + apply it to <html>, once, client-side. */
export function useHydrateTheme() {
  const hydrate = useThemeStore((s) => s.hydrate);
  const hydrateFromServer = useThemeStore((s) => s.hydrateFromServer);
  const hydrated = useThemeStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) {
      hydrate();
      // The server theme is app-wide and authoritative; adopt it after the local
      // cache so every origin/device converges on the same look.
      void hydrateFromServer();
    }
  }, [hydrated, hydrate, hydrateFromServer]);
}

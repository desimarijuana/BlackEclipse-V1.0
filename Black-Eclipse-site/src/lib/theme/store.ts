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
import {
  DEFAULT_ECLIPSE_THEME,
  BRAND_MARK_SRC,
  STRUCTURAL_THEME_VARS,
  normalizeTheme,
  themeCssVars,
  type EclipseTheme,
  type ThemeColors,
  type ThemeGlass,
} from './tokens';
import { DEFAULT_CHART_PALETTE, normalizeChartPalette, type ChartPalette } from '@/lib/chart-palette';
import { useChartPaletteStore } from '@/lib/chart-palette-store';

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

function buildOverrideCss(theme: EclipseTheme): string {
  const vars = themeCssVars(theme);
  const structural: string[] = [];
  const colors: string[] = [];
  for (const [name, value] of Object.entries(vars)) {
    (STRUCTURAL_THEME_VARS.has(name) ? structural : colors).push(`${name}: ${value};`);
  }
  // Colors are scoped to `.dark` so the General › Theme light/dark toggle still
  // works; typography/shape are global. `html.dark` outranks the plain `.dark`
  // block in globals.css, and both outrank `:root`.
  return (
    `:root{${structural.join('')}}` +
    `html.dark{${colors.join('')}}`
  );
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
  root.classList.add('theme-customized');
  root.classList.toggle('theme-no-anim', !theme.animations);
  root.classList.toggle('theme-no-glow', !theme.glow);
  // The token-driven glass override (which unifies the per-tier recipes) only
  // kicks in when the user changed glass settings or turned glass off. While
  // they match the shipped defaults, the hardcoded tier hierarchy stays intact.
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
  document.title = `${theme.appName} ${suffix}`;
}

function persist(theme: EclipseTheme) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(theme));
  } catch {
    /* quota / private mode — in-memory only */
  }
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
  /** Patch top-level fields (appName, fonts, radius, density, toggles, …). */
  setTheme: (patch: Partial<Omit<EclipseTheme, 'colors'>>) => void;
  /** Patch a single color token. */
  setColor: (key: keyof ThemeColors, value: string) => void;
  /** Patch the glass surface settings. */
  setGlass: (patch: Partial<ThemeGlass>) => void;
  /** Replace the theme wholesale (preset application). */
  applyPreset: (theme: EclipseTheme) => void;
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
  importPreset: (theme: EclipseTheme) => void;
  /** Restore the shipped Eclipse default and drop inline overrides. */
  reset: () => void;
}

function commit(theme: EclipseTheme): EclipseTheme {
  const clean = normalizeTheme(theme);
  applyThemeToDocument(clean);
  applyFavicon(clean);
  applyDocumentTitle(clean);
  persist(clean);
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

  applyPreset: (theme) => {
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
        ? { ...p, theme: normalizeTheme(get().theme), chartPalette: currentChartPalette(), createdAt: Date.now() }
        : p,
    );
    persistUserPresets(userPresets);
    set({ userPresets });
  },

  applyUserPreset: (id) => {
    const preset = get().userPresets.find((p) => p.id === id);
    if (!preset) return;
    get().applyPreset(preset.theme);
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

  importPreset: (theme) => {
    // Import stores a new named user preset rather than replacing the active
    // theme, so an import is always non-destructive.
    get().applyPreset(theme);
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
    set({ theme: DEFAULT_ECLIPSE_THEME, customized: false });
  },
}));

/** Hydrate the theme from localStorage + apply it to <html>, once, client-side. */
export function useHydrateTheme() {
  const hydrate = useThemeStore((s) => s.hydrate);
  const hydrated = useThemeStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}

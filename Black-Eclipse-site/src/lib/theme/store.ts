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
} from './tokens';

export const THEME_STORAGE_KEY = 'be_theme_v1';
const STYLE_ELEMENT_ID = 'eclipse-theme-overrides';

function loadTheme(): EclipseTheme | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (!raw) return null;
    return normalizeTheme(JSON.parse(raw));
  } catch {
    return null;
  }
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
 * shipped tokens while remaining scoped to dark mode.
 */
export function applyThemeToDocument(theme: EclipseTheme) {
  if (typeof document === 'undefined') return;
  let el = document.getElementById(STYLE_ELEMENT_ID) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement('style');
    el.id = STYLE_ELEMENT_ID;
    document.head.appendChild(el);
  }
  el.textContent = buildOverrideCss(theme);
  const root = document.documentElement;
  root.classList.toggle('theme-no-anim', !theme.animations);
  root.classList.toggle('theme-no-glow', !theme.glow);
}

/** Remove overrides so globals.css defaults take over again. */
function clearThemeFromDocument() {
  if (typeof document === 'undefined') return;
  document.getElementById(STYLE_ELEMENT_ID)?.remove();
  document.documentElement.classList.remove('theme-no-anim', 'theme-no-glow');
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
    localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(theme));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export interface ThemeStore {
  theme: EclipseTheme;
  hydrated: boolean;
  /** True once the user has overrides stored (drives the "Custom" badge). */
  customized: boolean;
  hydrate: () => void;
  /** Patch top-level fields (appName, fonts, radius, density, toggles, …). */
  setTheme: (patch: Partial<Omit<EclipseTheme, 'colors'>>) => void;
  /** Patch a single color token. */
  setColor: (key: keyof ThemeColors, value: string) => void;
  /** Replace the theme wholesale (preset application). */
  applyPreset: (theme: EclipseTheme) => void;
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

  hydrate: () => {
    const stored = loadTheme();
    if (stored) {
      applyThemeToDocument(stored);
      applyFavicon(stored);
      applyDocumentTitle(stored);
      set({ theme: stored, hydrated: true, customized: true });
    } else {
      set({ hydrated: true, customized: false });
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

  applyPreset: (theme) => {
    set({ theme: commit(theme), customized: true });
  },

  reset: () => {
    clearThemeFromDocument();
    applyFavicon(DEFAULT_ECLIPSE_THEME);
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(THEME_STORAGE_KEY);
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

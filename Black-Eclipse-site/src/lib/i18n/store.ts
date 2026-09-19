// ── Locale store ─────────────────────────────────────────────────────────────
// Client-side zustand store holding the user's chosen interface language.
// Persisted to localStorage and hydrated after mount, mirroring the sidebar
// and Aurora stores so SSR stays stable. The store also owns the document
// `lang`/`dir` side effects (RTL for Arabic, Urdu, Persian, Hebrew) and the
// accessibility preferences that live alongside language.

'use client';

import { create } from 'zustand';
import { DEFAULT_LOCALE, resolveLocale, type LocaleCode, type TextDirection } from './locales';
import { createTranslator, type TranslateFn } from './translate';

export const LOCALE_STORAGE_KEY = 'be_locale_v1';
export const A11Y_STORAGE_KEY = 'be_a11y_v1';

export interface A11yPreferences {
  reduceMotion: boolean;
  highContrast: boolean;
  largeText: boolean;
}

export const DEFAULT_A11Y: A11yPreferences = {
  reduceMotion: false,
  highContrast: false,
  largeText: false,
};

function readLocale(): LocaleCode {
  if (typeof window === 'undefined') return DEFAULT_LOCALE;
  try {
    return resolveLocale(localStorage.getItem(LOCALE_STORAGE_KEY)).code;
  } catch {
    return DEFAULT_LOCALE;
  }
}

function readA11y(): A11yPreferences {
  if (typeof window === 'undefined') return DEFAULT_A11Y;
  try {
    const raw = localStorage.getItem(A11Y_STORAGE_KEY);
    if (!raw) return DEFAULT_A11Y;
    const parsed = JSON.parse(raw) as Partial<A11yPreferences>;
    return {
      reduceMotion: parsed.reduceMotion === true,
      highContrast: parsed.highContrast === true,
      largeText: parsed.largeText === true,
    };
  } catch {
    return DEFAULT_A11Y;
  }
}

function persist(key: string, value: unknown) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** Apply locale + a11y choices to the document root (idempotent). */
function applyDocument(locale: LocaleCode, a11y: A11yPreferences) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const { dir } = resolveLocale(locale);
  root.lang = locale;
  root.dir = dir;
  root.classList.toggle('a11y-reduce-motion', a11y.reduceMotion);
  root.classList.toggle('a11y-high-contrast', a11y.highContrast);
  root.classList.toggle('a11y-large-text', a11y.largeText);
}

export interface LocaleStore {
  locale: LocaleCode;
  dir: TextDirection;
  a11y: A11yPreferences;
  hydrated: boolean;
  /** Load persisted choices and apply them to the document (client only). */
  hydrate: () => void;
  setLocale: (locale: LocaleCode) => void;
  setA11y: (patch: Partial<A11yPreferences>) => void;
  /** Bound translator for the active locale. */
  t: TranslateFn;
}

export const useLocaleStore = create<LocaleStore>((set, get) => ({
  // SSR-consistent defaults; real values load on mount (no hydration mismatch).
  locale: DEFAULT_LOCALE,
  dir: resolveLocale(DEFAULT_LOCALE).dir,
  a11y: DEFAULT_A11Y,
  hydrated: false,
  t: createTranslator(DEFAULT_LOCALE),

  hydrate: () => {
    const locale = readLocale();
    const a11y = readA11y();
    applyDocument(locale, a11y);
    set({ locale, dir: resolveLocale(locale).dir, a11y, hydrated: true, t: createTranslator(locale) });
  },

  setLocale: (locale) => {
    const a11y = get().a11y;
    persist(LOCALE_STORAGE_KEY, locale);
    applyDocument(locale, a11y);
    set({ locale, dir: resolveLocale(locale).dir, t: createTranslator(locale) });
  },

  setA11y: (patch) => {
    const next = { ...get().a11y, ...patch };
    persist(A11Y_STORAGE_KEY, next);
    applyDocument(get().locale, next);
    set({ a11y: next });
  },
}));

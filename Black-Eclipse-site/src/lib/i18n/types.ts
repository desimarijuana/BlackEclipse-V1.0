// ── i18n types ───────────────────────────────────────────────────────────────

import type { en } from './dictionaries/en';
import type { LocaleCode } from './locales';

/** The full set of translatable keys, derived from the English source. */
export type TranslationKey = keyof typeof en;

/** A locale's overrides. Any missing key falls back to English. */
export type Dictionary = Partial<Record<TranslationKey, string>>;

/** Lookup values may be substituted into `{placeholders}` in a string. */
export type TranslationVars = Record<string, string | number>;

export interface I18nCatalog {
  [locale: string]: Dictionary | undefined;
}

export type { LocaleCode };

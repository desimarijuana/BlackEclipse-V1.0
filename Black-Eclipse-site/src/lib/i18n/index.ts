// i18n + accessibility — public surface.
export { LOCALES, DEFAULT_LOCALE, resolveLocale, localeDirection } from './locales';
export type { LocaleCode, LocaleDef, TextDirection } from './locales';
export type { TranslationKey, TranslationVars, Dictionary } from './types';
export { createTranslator } from './translate';
export type { TranslateFn } from './translate';
export {
  useLocaleStore,
  LOCALE_STORAGE_KEY,
  A11Y_STORAGE_KEY,
  DEFAULT_A11Y,
} from './store';
export type { A11yPreferences, LocaleStore } from './store';
export { useT, useLocale, useHydrateI18n } from './use-t';
export { navLabelKey } from './nav';

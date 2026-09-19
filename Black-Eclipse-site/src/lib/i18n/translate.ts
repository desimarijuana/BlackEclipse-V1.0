// ── Translator core ──────────────────────────────────────────────────────────
// Pure, framework-free lookup so it is trivially testable and usable outside
// React (e.g. in the keybind system). Resolution order per key:
//   1. the active locale's dictionary
//   2. the English source (never show a raw key when we have a fallback)
//   3. the key itself (last resort, so a missing key is visible not blank)

import { en } from './dictionaries/en';
import { catalog } from './dictionaries';
import { resolveLocale } from './locales';
import type { TranslationKey, TranslationVars } from './types';

function interpolate(template: string, vars?: TranslationVars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match,
  );
}

export type TranslateFn = (key: TranslationKey, vars?: TranslationVars) => string;

/** Build a translate function bound to a locale code. */
export function createTranslator(locale: string | null | undefined): TranslateFn {
  const code = resolveLocale(locale).code as keyof typeof catalog;
  const dict = catalog[code];
  return (key, vars) => {
    const value = dict[key] ?? en[key] ?? key;
    return interpolate(value, vars);
  };
}

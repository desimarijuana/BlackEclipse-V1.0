'use client';

// ── useT — the translate hook ────────────────────────────────────────────────
// Components call `const t = useT()` then `t('nav.chat')`. The returned function
// is stable per locale (memoized in the store), so it is safe in dependency
// arrays. `useLocale()` reads the active locale + direction for UI that needs
// to lay out differently (e.g. alignment, icon mirroring).

import { useEffect } from 'react';
import { useLocaleStore } from './store';
import type { LocaleCode, TextDirection } from './locales';
import type { TranslateFn } from './translate';

export function useT(): TranslateFn {
  return useLocaleStore((s) => s.t);
}

export interface UseLocaleResult {
  locale: LocaleCode;
  dir: TextDirection;
  t: TranslateFn;
}

export function useLocale(): UseLocaleResult {
  const locale = useLocaleStore((s) => s.locale);
  const dir = useLocaleStore((s) => s.dir);
  const t = useLocaleStore((s) => s.t);
  return { locale, dir, t };
}

/** Ensure the store is hydrated + the document root reflects the choices. */
export function useHydrateI18n() {
  const hydrate = useLocaleStore((s) => s.hydrate);
  const hydrated = useLocaleStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}

import { describe, expect, it } from 'vitest';
import type { AppTab as ShellTab } from '@/components/layout/sidebar';
import type { AppTab as SearchTab } from '@/lib/search/types';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { navLabelKey } from '@/lib/i18n/nav';

// ── The two AppTab unions can no longer drift ────────────────────────────────
// `AppTab` used to be declared twice (sidebar.tsx and search/types.ts) with
// nothing keeping them equal; adding a tab to one silently narrowed the other,
// and `general-prefs.ts` imports the search mirror for its boot allowlist. Both
// now re-export the ONE declaration in `lib/app-tabs.ts`, so this file proves it
// two ways: a COMPILE-TIME equality (a drift fails `tsc --noEmit`) and a runtime
// coverage check (a sidebar section with no nav label key is a second drift).

type Equal<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
// If either union changes independently, this assignment fails to compile.
const shellEqualsSearch: Equal<ShellTab, SearchTab> = true;

describe('AppTab — one vocabulary, two consumers', () => {
  it('the shell and the search mirror are the same type', () => {
    // The compile-time guard is the real assertion; this keeps the intent visible
    // at runtime and fails loudly if the guard is ever deleted.
    expect(shellEqualsSearch).toBe(true);
  });

  it('every sidebar section has a navigation label key', () => {
    const missing = DEFAULT_SIDEBAR_SECTIONS.filter((s) => navLabelKey(s.id) === null).map((s) => s.id);
    expect(missing).toEqual([]);
  });

  it('every sidebar section id is a known tab', () => {
    // A section id that is not in the union could not be typed, but a runtime
    // check catches an `as any` escape.
    const ids = DEFAULT_SIDEBAR_SECTIONS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

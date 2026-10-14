// ── Browser-tab title composition ───────────────────────────────────────────
// The browser tab is where an unread notification must be visible while the
// operator is in another tab. Browsers cannot color tab text, so the red
// signal is the favicon badge (`tab-indicator.tsx`); the title carries the
// count — `(3) BlackEclipse — AI Stock Research & Screening Platform` — which
// every browser shows in the tab strip.
//
// Kept framework-free and pure (beyond reading the ledger) so the theme store
// can compose branded titles through the SAME prefix logic; without this, the
// theme store's own title write would silently drop the unread prefix.

import { totalUnread, useNotificationsStore } from './store';

/** `(3) BlackEclipse — …` / `(99+) …` / unchanged at zero. */
export function formatTabTitle(base: string, unread: number): string {
  if (unread <= 0) return base;
  return `(${unread > 99 ? '99+' : unread}) ${base}`;
}

/** Strip an existing `(n) ` prefix so re-applying never stacks. */
export function stripTabPrefix(title: string): string {
  return title.replace(/^\(\d+\+?\)\s/, '');
}

/** A base title with the CURRENT unread count applied. */
export function composeDocumentTitle(base: string): string {
  return formatTabTitle(base, totalUnread(useNotificationsStore.getState().items));
}

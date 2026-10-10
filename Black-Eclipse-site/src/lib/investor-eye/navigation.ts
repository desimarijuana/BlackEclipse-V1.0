// ── Investor Eye — navigation helpers ────────────────────────────────────────
// Panels reach the app's SPA shell the same way every other workspace panel
// does: by dispatching the `be:navigate` CustomEvent the shell listens for. This
// wrapper keeps the event shape in one place and is SSR-safe (no window at
// build time), so a panel never hand-rolls the event and drifts.

/** Settings section ids (subset we deep-link to). */
export const AI_SETTINGS_SECTION = 'ai';

/**
 * Open the Settings modal at a section. The shell's `be:navigate` handler now
 * understands `{ tab: 'settings', section }` (settings is a modal, not a tab).
 * A no-op outside the browser — callers never need a guard.
 */
export function openSettingsSection(section: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent('be:navigate', { detail: { tab: 'settings', section } }));
  } catch {
    /* nothing to do — navigation is best-effort */
  }
}

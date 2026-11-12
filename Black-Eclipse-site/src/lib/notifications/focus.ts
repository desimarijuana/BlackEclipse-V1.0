'use client';

// ── "Can the operator see this right now?" ──────────────────────────────────
// One definition shared by three decisions that must agree:
//   * the notification ledger — an item is unread if it arrived while the
//     operator could not see it, even on the tab they left open;
//   * the agent run hook — a finished reply deserves an alert when the app is in
//     the background, even if the ChatBot is the selected tab;
//   * the taskbar badge — a new arrival may flash only when nobody is looking.
//
// A minimized, background or hidden window is exactly the case all three exist
// for; treating "this tab is selected" as "this was seen" made all three wrong.

export function isViewerFocused(): boolean {
  if (typeof document === 'undefined') return true;
  try {
    if (document.visibilityState === 'hidden') return false;
    return document.hasFocus();
  } catch {
    return true;
  }
}

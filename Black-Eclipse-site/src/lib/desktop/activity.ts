'use client';

// ── Desktop activity (taskbar progress) ─────────────────────────────────────
// A process-wide count of streams that are actually doing work. The taskbar
// shows an indeterminate progress bar while the count is above zero and clears
// it when the last stream settles.
//
// Kept outside React because more than one run surface can be mounted at once
// (several Chat tabs, a recovered run, a second session): the taskbar reflects
// the process, not one component. Counted rather than owned by a single run, so
// one stream settling cannot clear the bar for another that is still going.

let active = 0;
const listeners = new Set<() => void>();

function publish(): void {
  for (const listener of listeners) {
    try {
      listener();
    } catch {
      /* a broken subscriber must not stop the others */
    }
  }
}

/** Register one in-flight stream. The returned release is idempotent. */
export function beginDesktopActivity(): () => void {
  active += 1;
  publish();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    active = Math.max(0, active - 1);
    publish();
  };
}

export function desktopActivityCount(): number {
  return active;
}

export function isDesktopActivity(): boolean {
  return active > 0;
}

export function subscribeDesktopActivity(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

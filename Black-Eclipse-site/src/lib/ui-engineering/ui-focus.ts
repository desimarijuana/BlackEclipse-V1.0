'use client';

// ── UI focus — the page the user is currently working on ─────────────────────
// A tiny module-level store the Pages / UI Builder surfaces write when they open
// a blueprint, and the chat reads when it starts a run. It lets the agent
// resolve "my widgets"/"this page" to a concrete blueprint id without the user
// repeating it. Presentation-only: it carries no capability and the front door
// sanitizes + bounds it before it reaches the runtime.

import type { UiFocus } from '@/lib/agent/types';

let current: UiFocus | undefined;
const listeners = new Set<(focus: UiFocus | undefined) => void>();

/** Set (or clear) the focused UI page. Notifies subscribers. */
export function setUiFocus(focus: UiFocus | undefined): void {
  current = focus;
  for (const listener of listeners) listener(focus);
}

/** The current focus, read at run-start time. */
export function getUiFocus(): UiFocus | undefined {
  return current;
}

export function clearUiFocus(): void {
  setUiFocus(undefined);
}

export function subscribeUiFocus(listener: (focus: UiFocus | undefined) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

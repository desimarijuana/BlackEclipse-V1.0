// ─── Plan mode: the composer's Auto / Plan / Off preference ──────────────────
//
// This is a PRESENTATION preference, not a grant. "on" asks the runtime to put a
// short block in front of the model telling it to lay out a concrete plan and
// wait for approval before it starts the work. "off" suppresses that nudge.
// "auto" leaves the base guidance in charge. Nothing here widens the tool
// surface, hard-blocks a call, or authorizes an effect.

export type PlanMode = 'auto' | 'on' | 'off';

const STORAGE_KEY = 'eclipse.plan-mode';
const CHANGE_EVENT = 'eclipse.plan-mode-change';

const MODES: readonly PlanMode[] = ['auto', 'on', 'off'];

function normalize(value: unknown): PlanMode {
  return value === 'on' || value === 'off' ? value : 'auto';
}

/** The saved mode. SSR-safe: returns "auto" when there is no window. */
export function getPlanMode(): PlanMode {
  if (typeof window === 'undefined') return 'auto';
  try {
    return normalize(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'auto';
  }
}

/** Persist the mode and notify every mounted control. */
export function setPlanMode(mode: PlanMode): void {
  if (typeof window === 'undefined') return;
  const next = normalize(mode);
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // A blocked localStorage must not break the composer; the in-memory state
    // still updates for this session.
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: next }));
}

/** Subscribe to changes made by another control or another tab. */
export function subscribePlanMode(listener: (mode: PlanMode) => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const onLocal = (event: Event) => {
    listener(normalize((event as CustomEvent<unknown>).detail));
  };
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) listener(normalize(event.newValue));
  };
  window.addEventListener(CHANGE_EVENT, onLocal);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onLocal);
    window.removeEventListener('storage', onStorage);
  };
}

export function nextPlanMode(mode: PlanMode): PlanMode {
  const index = MODES.indexOf(normalize(mode));
  return MODES[(index + 1) % MODES.length];
}

export function planModeLabel(mode: PlanMode): string {
  return mode === 'on' ? 'Plan' : mode === 'off' ? 'Plan off' : 'Plan auto';
}

export function planModeTitle(mode: PlanMode): string {
  if (mode === 'on') {
    return 'Plan mode: On — Eclipse lays out a plan and waits for your approval before starting the work. Click for Off.';
  }
  if (mode === 'off') {
    return 'Plan mode: Off — Eclipse acts without presenting a plan first. Click for Auto.';
  }
  return 'Plan mode: Auto — Eclipse plans first when the work is complex enough to need it. Click for On.';
}

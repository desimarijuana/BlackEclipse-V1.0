// ─── Quant mode: the composer's Auto / Quant / Off preference ────────────────
//
// This is a PRESENTATION preference, not a grant. The runtime's deterministic
// classifier still decides what a turn is; "on" only opts that turn into the
// quant protocol, and "off" only suppresses it. The server validates the value
// and the Python quant layer grants nothing it did not already have.

export type QuantMode = 'auto' | 'on' | 'off';

const STORAGE_KEY = 'eclipse.quant-mode';
const CHANGE_EVENT = 'eclipse.quant-mode-change';

const MODES: readonly QuantMode[] = ['auto', 'on', 'off'];

function normalize(value: unknown): QuantMode {
  return value === 'on' || value === 'off' ? value : 'auto';
}

/** The saved mode. SSR-safe: returns "auto" when there is no window. */
export function getQuantMode(): QuantMode {
  if (typeof window === 'undefined') return 'auto';
  try {
    return normalize(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'auto';
  }
}

/** Persist the mode and notify every mounted control. */
export function setQuantMode(mode: QuantMode): void {
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
export function subscribeQuantMode(listener: (mode: QuantMode) => void): () => void {
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

export function nextQuantMode(mode: QuantMode): QuantMode {
  const index = MODES.indexOf(normalize(mode));
  return MODES[(index + 1) % MODES.length];
}

export function quantModeLabel(mode: QuantMode): string {
  return mode === 'on' ? 'Quant' : mode === 'off' ? 'Quant off' : 'Quant auto';
}

export function quantModeTitle(mode: QuantMode): string {
  if (mode === 'on') {
    return 'Quant mode: On — quantitative turns get the full research protocol. Click for Off.';
  }
  if (mode === 'off') {
    return 'Quant mode: Off — no quant protocol is added. Click for Auto.';
  }
  return 'Quant mode: Auto — the classifier decides when a turn is quantitative. Click for On.';
}

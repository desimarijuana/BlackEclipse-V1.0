// ─── Choices mode: the composer's Auto / Choices / Off preference ────────────
//
// This is a PRESENTATION preference, not a grant. "on" asks the runtime to put a
// short block in front of the model telling it to use the existing `clarify` tool
// (one question, 2–4 clickable options) before it starts an ambiguous turn. "off"
// suppresses that nudge. "auto" leaves the base act-don't-ask guidance in charge.
// Nothing here widens the tool surface or authorizes an effect.

export type ChoicesMode = 'auto' | 'on' | 'off';

const STORAGE_KEY = 'eclipse.choices-mode';
const CHANGE_EVENT = 'eclipse.choices-mode-change';

const MODES: readonly ChoicesMode[] = ['auto', 'on', 'off'];

function normalize(value: unknown): ChoicesMode {
  return value === 'on' || value === 'off' ? value : 'auto';
}

/** The saved mode. SSR-safe: returns "auto" when there is no window. */
export function getChoicesMode(): ChoicesMode {
  if (typeof window === 'undefined') return 'auto';
  try {
    return normalize(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'auto';
  }
}

/** Persist the mode and notify every mounted control. */
export function setChoicesMode(mode: ChoicesMode): void {
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
export function subscribeChoicesMode(listener: (mode: ChoicesMode) => void): () => void {
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

export function nextChoicesMode(mode: ChoicesMode): ChoicesMode {
  const index = MODES.indexOf(normalize(mode));
  return MODES[(index + 1) % MODES.length];
}

export function choicesModeLabel(mode: ChoicesMode): string {
  return mode === 'on' ? 'Choices' : mode === 'off' ? 'Choices off' : 'Choices auto';
}

export function choicesModeTitle(mode: ChoicesMode): string {
  if (mode === 'on') {
    return 'Choices mode: On — Eclipse asks one short question with clickable options when a request is ambiguous. Click for Off.';
  }
  if (mode === 'off') {
    return 'Choices mode: Off — Eclipse acts on its best interpretation. Click for Auto.';
  }
  return 'Choices mode: Auto — Eclipse asks only when the choice genuinely changes what it will produce. Click for On.';
}

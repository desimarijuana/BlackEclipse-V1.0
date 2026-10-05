// ── Terminal panel store ─────────────────────────────────────────────────────
// One source of truth for whether the terminal is open, WHERE it docks, and which
// shell generation is active. The header button, the floating panel, the
// bottom/right/full-page placement control and the keyboard shortcut all read and
// write THIS store, so they can never disagree.
//
// Persisted so the panel reopens the way it was left, matching the rest of the
// shell's preferences.

'use client';

import { create } from 'zustand';

const OPEN_KEY = 'black-eclipse:terminal-open';
const PLACEMENT_KEY = 'black-eclipse:terminal-placement';

/** Where the terminal docks. `full` is a full-page overlay. */
export type TerminalPlacement = 'bottom' | 'right' | 'full';

const PLACEMENTS: readonly TerminalPlacement[] = ['bottom', 'right', 'full'];

function isPlacement(value: string | null): value is TerminalPlacement {
  return value != null && (PLACEMENTS as readonly string[]).includes(value);
}

function readOpen(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(OPEN_KEY) === '1';
  } catch {
    return false;
  }
}

function writeOpen(open: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(OPEN_KEY, open ? '1' : '0');
  } catch {
    /* private mode: in-memory only */
  }
}

function readPlacement(): TerminalPlacement {
  if (typeof window === 'undefined') return 'bottom';
  try {
    const stored = window.localStorage.getItem(PLACEMENT_KEY);
    return isPlacement(stored) ? stored : 'bottom';
  } catch {
    return 'bottom';
  }
}

function writePlacement(placement: TerminalPlacement): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PLACEMENT_KEY, placement);
  } catch {
    /* private mode: in-memory only */
  }
}

interface TerminalState {
  open: boolean;
  placement: TerminalPlacement;
  /** Bumped to open a fresh shell instead of reattaching to the current one. */
  generation: number;
  /** Reattach to the same shell (the default). */
  setOpen: (open: boolean) => void;
  toggle: () => void;
  setPlacement: (placement: TerminalPlacement) => void;
  /** Rotate the durable owner so the next mount opens a NEW shell. */
  newShell: () => void;
}

export const useTerminalStore = create<TerminalState>((set, get) => ({
  open: false,
  placement: 'bottom',
  generation: 0,
  setOpen: (open) => {
    writeOpen(open);
    set({ open });
  },
  toggle: () => {
    const next = !get().open;
    writeOpen(next);
    set({ open: next });
  },
  setPlacement: (placement) => {
    writePlacement(placement);
    set({ placement, open: true });
    writeOpen(true);
  },
  newShell: () => set((s) => ({ generation: s.generation + 1, open: true })),
}));

const OWNER_KEY = 'eclipse-terminal-owner';

/**
 * A stable per-browser terminal id. The dock and a pop-out/new-window terminal
 * share it, so they all attach to the SAME running shell instead of each opening
 * a fresh one.
 */
export function terminalOwnerId(): string {
  if (typeof window === 'undefined') return 'terminal-ui';
  try {
    const existing = window.localStorage.getItem(OWNER_KEY);
    if (existing) return existing;
    const created = `terminal-ui-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(OWNER_KEY, created);
    return created;
  } catch {
    return 'terminal-ui';
  }
}

/**
 * Hydrate the persisted open state and placement ONCE on the client, after mount,
 * so SSR and the first client render agree (no hydration mismatch).
 */
export function hydrateTerminalStore(): void {
  const open = readOpen();
  const placement = readPlacement();
  const current = useTerminalStore.getState();
  if (open !== current.open || placement !== current.placement) {
    useTerminalStore.setState({ open, placement });
  }
}

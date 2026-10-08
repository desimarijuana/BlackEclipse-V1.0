// ── Agent Workspace store ────────────────────────────────────────────────────
// Owns the LIVE normalized workspace for the active run, plus the user's panel
// preferences. This is a UI store, not an agent engine: it never talks to the
// runtime directly except through the existing SSE relay (`stream.ts`).
//
// Performance contract (docs: agent-workspace.md):
//   * `useAgentRun` pushes frames on every read; this store folds them into an
//     immer draft and commits at most once per `FLUSH_MS`. A burst of 10k events
//     produces a handful of renders, not 10k.
//   * Duplicate event ENVELOPES are dropped by id at ingest (bounded set);
//     out-of-order frames are still applied and counted, so no row is lost or
//     duplicated just because the transport reordered it.
//   * Components subscribe with selectors, so only panels reading a changed
//     slice re-render (the activity list is capped in the reducer).

'use client';

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { applyWorkspaceEvents, initialWorkspaceState } from './reducer';
import type { AgentWorkspaceState, WorkspaceEvent } from './types';

/** Panel ids. `changes` is pinned by default; others auto-focus on activity. */
export type WorkspacePanel =
  | 'overview'
  | 'activity'
  | 'tasks'
  | 'changes'
  | 'context'
  | 'terminal'
  | 'research'
  | 'browser'
  | 'computer'
  | 'artifacts'
  | 'permissions'
  | 'telemetry'
  | 'history';

const OPEN_KEY = 'black-eclipse:workspace-open';
const PANEL_KEY = 'black-eclipse:workspace-panel';
const PIN_KEY = 'black-eclipse:workspace-pinned';

const FLUSH_MS = 150;
const MAX_SEEN_FRAMES = 100_000;

const ALL_PANELS: readonly WorkspacePanel[] = [
  'overview', 'activity', 'tasks', 'changes', 'context', 'terminal',
  'research', 'browser', 'computer', 'artifacts', 'permissions', 'telemetry', 'history',
];

function isPanel(value: unknown): value is WorkspacePanel {
  return typeof value === 'string' && (ALL_PANELS as readonly string[]).includes(value);
}

function readBool(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw == null ? fallback : raw === '1';
  } catch {
    return fallback;
  }
}
function writeBool(key: string, value: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* private mode */
  }
}
function readPanel(): WorkspacePanel {
  if (typeof window === 'undefined') return 'overview';
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    return isPanel(raw) ? raw : 'overview';
  } catch {
    return 'overview';
  }
}
function readPinned(): WorkspacePanel[] {
  if (typeof window === 'undefined') return ['changes'];
  try {
    const raw = window.localStorage.getItem(PIN_KEY);
    if (!raw) return ['changes'];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return ['changes'];
    return parsed.filter(isPanel);
  } catch {
    return ['changes'];
  }
}

interface WorkspaceStoreState {
  open: boolean;
  /** The run the live workspace is bound to, or null. */
  runId: string | null;
  state: AgentWorkspaceState;
  activePanel: WorkspacePanel;
  /** Panels the user pinned (auto-focus may not override these). */
  pinned: WorkspacePanel[];
  /** True once the user manually picked a panel — auto-focus then backs off. */
  userChosen: boolean;

  setOpen: (open: boolean) => void;
  toggle: () => void;
  setActivePanel: (panel: WorkspacePanel) => void;
  togglePinned: (panel: WorkspacePanel) => void;
  bindRun: (runId: string) => void;
  ingest: (events: WorkspaceEvent[], frame: { id?: string; seq?: number }) => void;
  clear: () => void;
}

// ── Non-React batching singletons ─────────────────────────────────────────────
interface QueuedFrame {
  id?: string;
  seq?: number;
}
let flushTimer: ReturnType<typeof setTimeout> | null = null;
const queuedEvents: WorkspaceEvent[] = [];
const queuedFrames: QueuedFrame[] = [];
const seenFrameIds = new Set<string>();

function resetBatch(): void {
  queuedEvents.length = 0;
  queuedFrames.length = 0;
  seenFrameIds.clear();
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
}

/** The "auto-active" rule: a running subsystem claims the view, gently. */
function pickAutoFocus(s: WorkspaceStoreState): WorkspacePanel | null {
  const st = s.state;
  if (st.permissions.some((p) => p.status === 'pending')) return 'permissions';
  if (st.research?.active) return 'research';
  if (st.browser?.active) return 'browser';
  if (st.computer?.active) return 'computer';
  return null;
}

export const useWorkspaceStore = create<WorkspaceStoreState>()(
  immer((set, get) => ({
    open: false,
    runId: null,
    state: initialWorkspaceState(),
    activePanel: 'overview',
    pinned: ['changes'],
    userChosen: false,

    setOpen: (open) => {
      writeBool(OPEN_KEY, open);
      set((s) => {
        s.open = open;
      });
    },
    toggle: () => {
      const next = !get().open;
      writeBool(OPEN_KEY, next);
      set((s) => {
        s.open = next;
      });
    },
    setActivePanel: (panel) => {
      if (typeof window !== 'undefined') {
        try {
          window.localStorage.setItem(PANEL_KEY, panel);
        } catch {
          /* ignore */
        }
      }
      set((s) => {
        s.activePanel = panel;
        s.userChosen = true;
      });
    },
    togglePinned: (panel) =>
      set((s) => {
        const idx = s.pinned.indexOf(panel);
        if (idx === -1) s.pinned.push(panel);
        else s.pinned.splice(idx, 1);
        if (typeof window !== 'undefined') {
          try {
            window.localStorage.setItem(PIN_KEY, JSON.stringify(s.pinned));
          } catch {
            /* ignore */
          }
        }
      }),

    bindRun: (runId) => {
      if (get().runId === runId) return;
      resetBatch();
      set((s) => {
        s.runId = runId;
        s.state = initialWorkspaceState(runId);
        s.userChosen = false;
      });
    },

    ingest: (events, frame) => {
      // Drop duplicate envelopes at ingest so a replayed stream cannot double-apply.
      if (frame.id) {
        if (seenFrameIds.has(frame.id)) return;
        if (seenFrameIds.size < MAX_SEEN_FRAMES) seenFrameIds.add(frame.id);
      }
      for (const event of events) queuedEvents.push(event);
      queuedFrames.push({ id: frame.id, seq: frame.seq });

      if (flushTimer) return;
      flushTimer = setTimeout(() => {
        flushTimer = null;
        const batch = queuedEvents.splice(0, queuedEvents.length);
        const frames = queuedFrames.splice(0, queuedFrames.length);
        if (batch.length === 0) return;
        set((s) => {
          applyWorkspaceEvents(s.state, batch);
          for (const f of frames) {
            if (f.seq != null) {
              if (f.seq < s.state.lastSeq) s.state.outOfOrder += 1;
              else s.state.lastSeq = f.seq;
            }
          }
          const focus = pickAutoFocus(s);
          if (focus && !s.userChosen && s.pinned.indexOf(focus) === -1) {
            s.activePanel = focus;
          }
        });
      }, FLUSH_MS);
    },

    clear: () => {
      resetBatch();
      set((s) => {
        s.runId = null;
        s.state = initialWorkspaceState();
        s.userChosen = false;
      });
    },
  })),
);

/** Hydrate the persisted open/panel/pinned preferences once on the client. */
export function hydrateWorkspaceStore(): void {
  if (typeof window === 'undefined') return;
  const open = readBool(OPEN_KEY, false);
  const activePanel = readPanel();
  const pinned = readPinned();
  useWorkspaceStore.setState((s) => {
    s.open = open;
    s.activePanel = activePanel;
    s.pinned = pinned;
  });
}

export { ALL_PANELS };

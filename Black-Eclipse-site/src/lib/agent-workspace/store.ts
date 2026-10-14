// â”€â”€ Agent Workspace store â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

/** Panel ids for the right sidebar. `context` is the first/default panel. */
export type WorkspacePanel = 'output' | 'context' | 'changes' | 'permissions' | 'history' | 'explain';

const OPEN_KEY = 'black-eclipse:workspace-open';
const PANEL_KEY = 'black-eclipse:workspace-panel';

const FLUSH_MS = 150;
const MAX_SEEN_FRAMES = 100_000;

const ALL_PANELS: readonly WorkspacePanel[] = ['output', 'context', 'changes', 'permissions', 'history', 'explain'];

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
  if (typeof window === 'undefined') return 'context';
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    return isPanel(raw) ? raw : 'context';
  } catch {
    return 'context';
  }
}

interface WorkspaceStoreState {
  open: boolean;
  /** The run the live workspace is bound to, or null. */
  runId: string | null;
  state: AgentWorkspaceState;
  activePanel: WorkspacePanel;

  setOpen: (open: boolean) => void;
  toggle: () => void;
  setActivePanel: (panel: WorkspacePanel) => void;
  bindRun: (runId: string) => void;
  /** Present a fully-built snapshot (a replayed finished run) as the state. */
  loadRun: (runId: string, state: AgentWorkspaceState) => void;
  ingest: (events: WorkspaceEvent[], frame: { id?: string; seq?: number }) => void;
  clear: () => void;
}

// â”€â”€ Non-React batching singletons â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

export const useWorkspaceStore = create<WorkspaceStoreState>()(
  immer((set, get) => ({
    open: false,
    runId: null,
    state: initialWorkspaceState(),
    activePanel: 'context',

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
      });
    },

    bindRun: (runId) => {
      if (get().runId === runId) return;
      resetBatch();
      set((s) => {
        s.runId = runId;
        s.state = initialWorkspaceState(runId);
      });
    },

    loadRun: (runId, state) => {
      resetBatch();
      set((s) => {
        s.runId = runId;
        s.state = state;
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
        });
      }, FLUSH_MS);
    },

    clear: () => {
      resetBatch();
      set((s) => {
        s.runId = null;
        s.state = initialWorkspaceState();
      });
    },
  })),
);

/** Hydrate the persisted open/panel preferences once on the client. */
export function hydrateWorkspaceStore(): void {
  if (typeof window === 'undefined') return;
  const open = readBool(OPEN_KEY, false);
  const activePanel = readPanel();
  useWorkspaceStore.setState((s) => {
    s.open = open;
    s.activePanel = activePanel;
  });
}

export { ALL_PANELS };

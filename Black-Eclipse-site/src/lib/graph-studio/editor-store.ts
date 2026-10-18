// ── Graph editor state (transient) ────────────────────────────────────────────
// The editor's OWN state, deliberately kept apart from the persistent IR. This
// store owns: the working copy of the IR, selection, undo/redo history, the
// dirty flag, live diagnostics and the error from the last rejected patch.
//
// Every semantic mutation goes through `dispatch(patch)`, which routes through
// the pure `applyPatch` validator. A rejected patch changes nothing — so an
// invalid edit can never leave the document half-updated.

import { create } from 'zustand';
import type { Diagnostic, NodePosition, WorkflowIR, WorkflowSettings } from './types';
import { applyPatch, applyPatches, type Patch, type PatchResult } from './patches';
import { validateWorkflow } from './validation';
import { autoLayout } from './layout';
import type { GraphRunRecord } from './execution-client';

const MAX_HISTORY = 100;

export interface EditorSelection {
  nodeIds: string[];
  edgeIds: string[];
}

interface LoadOptions {
  workflowId: string;
  baseVersion?: number;
  contentHash?: string | null;
}

export interface GraphEditorState {
  ir: WorkflowIR | null;
  workflowId: string | null;
  baseVersion: number;
  serverContentHash: string | null;
  dirty: boolean;
  past: WorkflowIR[];
  future: WorkflowIR[];
  selection: EditorSelection;
  diagnostics: Diagnostic[];
  lastError: string | null;
  /** The run currently displayed on the canvas. Transient: never persisted. */
  run: GraphRunRecord | null;
  /**
   * A node that should be inserted at a sensible spot by whoever owns the
   * viewport (the canvas). Requested from the mode panel's node library; also
   * the seam Chat-to-Graph (Phase 7) will use to place generated nodes.
   */
  pendingInsert: { type: string; version: string; nonce: number } | null;

  load: (ir: WorkflowIR, opts: LoadOptions) => void;
  setRun: (run: GraphRunRecord | null) => void;
  requestInsert: (type: string, version: string) => void;
  consumeInsert: () => void;
  dispatch: (patch: Patch) => boolean;
  dispatchMany: (patches: Patch[]) => boolean;
  undo: () => void;
  redo: () => void;
  setSelection: (selection: Partial<EditorSelection>) => void;
  recomputeDiagnostics: () => Diagnostic[];
  applyAutoLayout: () => void;
  markSaved: (version: number, contentHash: string) => void;
  reset: () => void;
}

const EMPTY_SELECTION: EditorSelection = { nodeIds: [], edgeIds: [] };

export const useGraphEditor = create<GraphEditorState>((set, get) => ({
  ir: null,
  workflowId: null,
  baseVersion: 0,
  serverContentHash: null,
  dirty: false,
  past: [],
  future: [],
  selection: EMPTY_SELECTION,
  diagnostics: [],
  lastError: null,
  run: null,
  pendingInsert: null,

  load: (ir, opts) => {
    set({
      ir,
      workflowId: opts.workflowId,
      baseVersion: opts.baseVersion ?? 0,
      serverContentHash: opts.contentHash ?? null,
      dirty: false,
      past: [],
      future: [],
      selection: EMPTY_SELECTION,
      diagnostics: validateWorkflow(ir),
      lastError: null,
      run: null,
    });
  },

  setRun: (run) => set({ run }),

  requestInsert: (type, version) => set({ pendingInsert: { type, version, nonce: Date.now() } }),
  consumeInsert: () => set({ pendingInsert: null }),

  dispatch: (patch) => {
    const { ir, past } = get();
    if (!ir) return false;
    const result = applyPatch(ir, patch);
    if (!result.ok) {
      set({ lastError: result.error });
      return false;
    }
    set({
      ir: result.ir,
      past: [...past, ir].slice(-MAX_HISTORY),
      future: [],
      dirty: true,
      diagnostics: validateWorkflow(result.ir),
      lastError: null,
    });
    return true;
  },

  dispatchMany: (patches) => {
    const { ir, past } = get();
    if (!ir) return false;
    const result = applyPatches(ir, patches);
    if (!result.ok) {
      set({ lastError: result.error });
      return false;
    }
    set({
      ir: result.ir,
      past: [...past, ir].slice(-MAX_HISTORY),
      future: [],
      dirty: true,
      diagnostics: validateWorkflow(result.ir),
      lastError: null,
    });
    return true;
  },

  undo: () => {
    const { ir, past, future } = get();
    if (!ir || past.length === 0) return;
    const previous = past[past.length - 1];
    set({
      ir: previous,
      past: past.slice(0, -1),
      future: [ir, ...future].slice(0, MAX_HISTORY),
      dirty: true,
      diagnostics: validateWorkflow(previous),
      lastError: null,
    });
  },

  redo: () => {
    const { ir, past, future } = get();
    if (!ir || future.length === 0) return;
    const next = future[0];
    set({
      ir: next,
      past: [...past, ir].slice(-MAX_HISTORY),
      future: future.slice(1),
      dirty: true,
      diagnostics: validateWorkflow(next),
      lastError: null,
    });
  },

  setSelection: (selection) => {
    set({
      selection: {
        nodeIds: selection.nodeIds ?? get().selection.nodeIds,
        edgeIds: selection.edgeIds ?? get().selection.edgeIds,
      },
    });
  },

  recomputeDiagnostics: () => {
    const { ir } = get();
    const diagnostics = ir ? validateWorkflow(ir) : [];
    set({ diagnostics });
    return diagnostics;
  },

  applyAutoLayout: () => {
    const { ir } = get();
    if (!ir) return;
    const positions = autoLayout(ir);
    const nodes = ir.nodes.map((n) => ({ ...n, layout: positions[n.id] ?? n.layout }));
    const next: WorkflowIR = { ...ir, nodes, meta: { ...ir.meta, updatedAt: new Date().toISOString() } };
    set({
      ir: next,
      past: [...get().past, ir].slice(-MAX_HISTORY),
      future: [],
      dirty: true,
      diagnostics: validateWorkflow(next),
    });
  },

  markSaved: (version, contentHash) => {
    set({ baseVersion: version, serverContentHash: contentHash, dirty: false });
  },

  reset: () => {
    set({
      ir: null,
      workflowId: null,
      baseVersion: 0,
      serverContentHash: null,
      dirty: false,
      past: [],
      future: [],
      selection: EMPTY_SELECTION,
      diagnostics: [],
      lastError: null,
      run: null,
      pendingInsert: null,
    });
  },
}));

export type { Patch, PatchResult, WorkflowSettings, NodePosition };

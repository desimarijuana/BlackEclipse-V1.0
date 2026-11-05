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
import { buildClipboard, buildDuplicateNodes, buildPaste, type EditClipboard } from './edit-ops';
import { validateWorkflow } from './validation';
import { autoLayout } from './layout';
import type { GraphRunRecord } from './execution-client';

const MAX_HISTORY = 100;

export interface EditorSelection {
  nodeIds: string[];
  edgeIds: string[];
}

/**
 * `coalesceKey` groups consecutive edits of the same control into ONE undo
 * entry (e.g. typing in a config field). Time-bounded so a later, separate edit
 * to the same field is still its own step.
 */
export interface DispatchOptions {
  coalesceKey?: string;
}

const COALESCE_WINDOW_MS = 1_200;
let lastCoalesceKey: string | null = null;
let lastCoalesceAt = 0;

function clearCoalesce() {
  lastCoalesceKey = null;
  lastCoalesceAt = 0;
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
  /** Increments on every `load`; the workspace uses it to open the editor. */
  loadNonce: number;
  /** Live canvas zoom, used only to render the zoom readout. */
  canvasZoom: number;
  dirty: boolean;
  past: WorkflowIR[];
  future: WorkflowIR[];
  selection: EditorSelection;
  diagnostics: Diagnostic[];
  lastError: string | null;
  /** Internal copy buffer for canvas copy/paste. Never persisted. */
  clipboard: EditClipboard | null;
  /** The run currently displayed on the canvas. Transient: never persisted. */
  run: GraphRunRecord | null;
  /**
   * A node that should be inserted at a sensible spot by whoever owns the
   * viewport (the canvas). Requested from the mode panel's node library; also
   * the seam Chat-to-Graph (Phase 7) will use to place generated nodes.
   */
  pendingInsert: { type: string; version: string; nonce: number } | null;
  /**
   * Nodes the viewport should centre after an assistant edit. The canvas owns
   * the React Flow instance, so it consumes this request and clears it.
   */
  focusRequest: { nodeIds: string[]; nonce: number } | null;

  load: (ir: WorkflowIR, opts: LoadOptions) => void;
  setRun: (run: GraphRunRecord | null) => void;
  requestInsert: (type: string, version: string) => void;
  consumeInsert: () => void;
  requestFocus: (nodeIds: string[]) => void;
  consumeFocus: () => void;
  dispatch: (patch: Patch, opts?: DispatchOptions) => boolean;
  dispatchMany: (patches: Patch[]) => boolean;
  undo: () => void;
  redo: () => void;
  setSelection: (selection: Partial<EditorSelection>) => void;
  setCanvasZoom: (zoom: number) => void;
  selectAll: () => void;
  clearSelection: () => void;
  duplicateSelection: () => boolean;
  copySelection: () => boolean;
  pasteClipboard: () => boolean;
  recomputeDiagnostics: () => Diagnostic[];
  applyAutoLayout: (heights?: Record<string, number>) => void;
  markSaved: (version: number, contentHash: string) => void;
  reset: () => void;
}

const EMPTY_SELECTION: EditorSelection = { nodeIds: [], edgeIds: [] };

export const useGraphEditor = create<GraphEditorState>((set, get) => ({
  ir: null,
  workflowId: null,
  baseVersion: 0,
  serverContentHash: null,
  loadNonce: 0,
  canvasZoom: 1,
  dirty: false,
  past: [],
  future: [],
  selection: EMPTY_SELECTION,
  diagnostics: [],
  lastError: null,
  clipboard: null,
  run: null,
  pendingInsert: null,
  focusRequest: null,

  load: (ir, opts) => {
    clearCoalesce();
    set({
      ir,
      workflowId: opts.workflowId,
      baseVersion: opts.baseVersion ?? 0,
      serverContentHash: opts.contentHash ?? null,
      loadNonce: get().loadNonce + 1,
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
  requestFocus: (nodeIds) => {
    if (nodeIds.length === 0) return;
    set({ focusRequest: { nodeIds, nonce: Date.now() } });
  },
  consumeFocus: () => set({ focusRequest: null }),

  dispatch: (patch, opts) => {
    const { ir, past } = get();
    if (!ir) return false;
    const result = applyPatch(ir, patch);
    if (!result.ok) {
      set({ lastError: result.error });
      return false;
    }
    const now = Date.now();
    const coalesce = Boolean(
      opts?.coalesceKey
      && opts.coalesceKey === lastCoalesceKey
      && now - lastCoalesceAt < COALESCE_WINDOW_MS,
    );
    lastCoalesceKey = opts?.coalesceKey ?? null;
    lastCoalesceAt = now;
    set({
      ir: result.ir,
      past: coalesce ? past : [...past, ir].slice(-MAX_HISTORY),
      future: [],
      dirty: true,
      diagnostics: validateWorkflow(result.ir),
      lastError: null,
    });
    return true;
  },

  dispatchMany: (patches) => {
    clearCoalesce();
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
    clearCoalesce();
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
    clearCoalesce();
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
    const current = get().selection;
    const nodeIds = selection.nodeIds ?? current.nodeIds;
    const edgeIds = selection.edgeIds ?? current.edgeIds;
    const same =
      nodeIds.length === current.nodeIds.length &&
      edgeIds.length === current.edgeIds.length &&
      nodeIds.every((id, index) => id === current.nodeIds[index]) &&
      edgeIds.every((id, index) => id === current.edgeIds[index]);
    if (same) return;
    set({ selection: { nodeIds, edgeIds } });
  },

  selectAll: () => {
    const { ir } = get();
    if (!ir) return;
    set({ selection: { nodeIds: ir.nodes.map((node) => node.id), edgeIds: [] } });
  },

  setCanvasZoom: (zoom) => set({ canvasZoom: zoom }),

  clearSelection: () => set({ selection: EMPTY_SELECTION }),

  duplicateSelection: () => {
    const { ir, selection } = get();
    if (!ir || selection.nodeIds.length === 0) return false;
    const { patches, nodeIds } = buildDuplicateNodes(ir, selection.nodeIds);
    if (patches.length === 0) return false;
    const ok = get().dispatchMany(patches);
    if (ok) set({ selection: { nodeIds, edgeIds: [] } });
    return ok;
  },

  copySelection: () => {
    const { ir, selection } = get();
    if (!ir || selection.nodeIds.length === 0) return false;
    set({ clipboard: buildClipboard(ir, selection.nodeIds) });
    return true;
  },

  pasteClipboard: () => {
    const { ir, clipboard } = get();
    if (!ir || !clipboard) return false;
    const { patches, nodeIds } = buildPaste(ir, clipboard);
    if (patches.length === 0) return false;
    const ok = get().dispatchMany(patches);
    if (ok) set({ selection: { nodeIds, edgeIds: [] } });
    return ok;
  },

  recomputeDiagnostics: () => {
    const { ir } = get();
    const diagnostics = ir ? validateWorkflow(ir) : [];
    set({ diagnostics });
    return diagnostics;
  },

  applyAutoLayout: (heights) => {
    clearCoalesce();
    const { ir } = get();
    if (!ir) return;
    const positions = autoLayout(ir, { heights });
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
    clearCoalesce();
    set({
      ir: null,
      workflowId: null,
      baseVersion: 0,
      serverContentHash: null,
      canvasZoom: 1,
      dirty: false,
      past: [],
      future: [],
      selection: EMPTY_SELECTION,
      diagnostics: [],
      lastError: null,
      run: null,
      pendingInsert: null,
      focusRequest: null,
    });
  },
}));

export type { Patch, PatchResult, WorkflowSettings, NodePosition };
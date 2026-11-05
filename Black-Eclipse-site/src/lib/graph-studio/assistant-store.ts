// ── Graph assistant state (transient + per-workflow transcript) ─────────────
// A chat thread over the CURRENT editor document. The proposal itself is never
// persisted (an op list can go stale), but the transcript is kept per workflow
// in sessionStorage so closing the dock or reloading does not lose context.

import { create } from 'zustand';
import { useGraphEditor } from './editor-store';
import {
  assistGraphStream,
  type AssistantRequest,
  type AssistantResult,
  type AssistantRunResult,
  type AssistantTurn,
} from './assistant-client';
import { graphEditOpsToPatches } from './assistant-ops';

export interface AssistantChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  applied?: boolean;
  error?: boolean;
  runs?: AssistantRunResult[];
}

export interface AssistantStep {
  id: string;
  label: string;
  state: 'running' | 'ok' | 'error';
}

interface AssistantState {
  messages: AssistantChatMessage[];
  status: 'idle' | 'thinking';
  pending: AssistantResult | null;
  /** The IR id the proposal was computed against. Guards cross-workflow apply. */
  pendingDocumentId: string | null;
  error: string | null;
  progressLabel: string | null;
  steps: AssistantStep[];
  autoApply: boolean;
  setAutoApply: (value: boolean) => void;
  hydrate: (workflowId: string | null) => void;
  send: (instruction: string, mode?: 'edit' | 'ask') => Promise<void>;
  cancel: () => void;
  applyPending: () => boolean;
  discardPending: () => void;
  reset: () => void;
}

const STORAGE_PREFIX = 'be_graph_assistant_v1:';
const AUTO_APPLY_KEY = 'be_graph_assistant_autoapply_v1';
let counter = 0;
let activeController: AbortController | null = null;

function nextId(prefix = 'm'): string {
  counter += 1;
  return `${prefix}_${Date.now().toString(36)}_${counter}`;
}

function storageKey(workflowId: string | null | undefined): string | null {
  return workflowId ? `${STORAGE_PREFIX}${workflowId}` : null;
}

function persist(workflowId: string | null | undefined, messages: AssistantChatMessage[]) {
  const key = storageKey(workflowId);
  if (!key) return;
  try {
    const clean = messages
      .filter((message) => !message.pending)
      .slice(-30)
      .map(({ id, role, content, applied, error }) => ({ id, role, content, applied, error }));
    window.sessionStorage.setItem(key, JSON.stringify(clean));
  } catch {
    /* storage can be unavailable; the in-memory thread still works */
  }
}

function initialAutoApply(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(AUTO_APPLY_KEY) !== 'off';
  } catch {
    return true;
  }
}

function lastRunContext(): AssistantRequest['lastRun'] {
  const run = useGraphEditor.getState().run;
  if (!run) return null;
  const failed = run.nodeRuns?.find((node) => node.status === 'failed');
  return {
    status: run.status,
    failedNodeId: failed?.nodeId ?? null,
    error: failed?.error ?? run.error ?? null,
    events: (run.events ?? [])
      .slice(-10)
      .map((event) => `${event.kind}${event.nodeId ? ` ${event.nodeId}` : ''}: ${event.message}`),
  };
}

export const useGraphAssistant = create<AssistantState>((set, get) => ({
  messages: [],
  status: 'idle',
  pending: null,
  pendingDocumentId: null,
  error: null,
  progressLabel: null,
  steps: [],
  autoApply: initialAutoApply(),

  setAutoApply: (value) => {
    try {
      window.localStorage.setItem(AUTO_APPLY_KEY, value ? 'on' : 'off');
    } catch {
      /* ignore */
    }
    set({ autoApply: value });
  },

  hydrate: (workflowId) => {
    const key = storageKey(workflowId);
    if (!key) {
      set({ messages: [], pending: null, pendingDocumentId: null, error: null, steps: [], progressLabel: null });
      return;
    }
    let messages: AssistantChatMessage[] = [];
    try {
      const raw = window.sessionStorage.getItem(key);
      const parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed)) {
        messages = parsed
          .filter((item) => item && (item.role === 'user' || item.role === 'assistant') && typeof item.content === 'string')
          .slice(-30);
      }
    } catch {
      messages = [];
    }
    set({ messages, pending: null, pendingDocumentId: null, error: null, steps: [], progressLabel: null, status: 'idle' });
  },

  send: async (instruction, mode = 'edit') => {
    const text = instruction.trim();
    if (!text || get().status === 'thinking') return;
    const editor = useGraphEditor.getState();
    if (!editor.ir) {
      set({ error: 'Open a workflow before asking the assistant to change it.' });
      return;
    }

    const history: AssistantTurn[] = get()
      .messages.filter((message) => !message.pending && !message.error)
      .slice(-8)
      .map((message) => ({ role: message.role, content: message.content }));

    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;

    set((state) => ({
      status: 'thinking',
      error: null,
      pending: null,
      pendingDocumentId: null,
      progressLabel: 'Reading the workflow',
      steps: [],
      messages: [...state.messages, { id: nextId(), role: 'user', content: text }],
    }));

    try {
      const result = await assistGraphStream(
        {
          instruction: text,
          ir: editor.ir,
          mode,
          selection: editor.selection,
          history,
          lastRun: lastRunContext(),
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            if (event.type === 'status') {
              set({ progressLabel: event.label });
            } else if (event.type === 'tool_start') {
              set((state) => ({
                progressLabel: event.label,
                steps: [...state.steps, { id: nextId('s'), label: event.label, state: 'running' }],
              }));
            } else if (event.type === 'tool_end') {
              set((state) => {
                const steps = [...state.steps];
                for (let index = steps.length - 1; index >= 0; index -= 1) {
                  if (steps[index].label === event.label && steps[index].state === 'running') {
                    steps[index] = { ...steps[index], state: event.ok ? 'ok' : 'error' };
                    break;
                  }
                }
                return { steps, progressLabel: event.label };
              });
            }
          },
        },
      );

      const reply = result.summary || result.answer || 'Done.';
      const hasEdits = result.ops.length > 0 && result.mode === 'edit';
      const autoApply = get().autoApply
        && hasEdits
        && result.ok
        && result.errors.length === 0
        && result.warnings.length === 0;
      set((state) => ({
        status: 'idle',
        progressLabel: null,
        steps: [],
        pending: hasEdits ? result : null,
        pendingDocumentId: hasEdits ? editor.ir?.id ?? null : null,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: 'assistant',
            content: reply,
            pending: hasEdits,
            runs: result.runs ?? [],
          },
        ],
      }));
      if (autoApply) get().applyPending();
      if (result.errors.length > 0 && !autoApply) {
        set({ error: result.errors[0]?.message ?? 'The proposal is not valid yet.' });
      }
      persist(useGraphEditor.getState().workflowId, get().messages);
    } catch (err) {
      const aborted = err instanceof DOMException
        ? err.name === 'AbortError'
        : err instanceof Error && err.name === 'AbortError';
      if (aborted) {
        set((state) => ({
          status: 'idle',
          progressLabel: null,
          pending: null,
          pendingDocumentId: null,
          steps: [],
          messages: [...state.messages, { id: nextId(), role: 'assistant', content: 'Stopped.' }],
        }));
      } else {
        const message = err instanceof Error ? err.message : 'The assistant failed';
        set((state) => ({
          status: 'idle',
          progressLabel: null,
          pending: null,
          pendingDocumentId: null,
          steps: [],
          error: message,
          messages: [...state.messages, { id: nextId(), role: 'assistant', content: message, error: true }],
        }));
      }
      persist(useGraphEditor.getState().workflowId, get().messages);
    } finally {
      if (activeController === controller) activeController = null;
    }
  },

  cancel: () => {
    activeController?.abort();
  },

  applyPending: () => {
    const { pending, pendingDocumentId } = get();
    if (!pending || pending.ops.length === 0) return false;
    const currentId = useGraphEditor.getState().ir?.id ?? null;
    if (pendingDocumentId && currentId !== pendingDocumentId) {
      set({
        pending: null,
        pendingDocumentId: null,
        error: 'The assistant proposal belongs to a different workflow. Ask again on this one.',
      });
      return false;
    }
    const patches = graphEditOpsToPatches(pending.ops);
    if (patches.length === 0) {
      set({ pending: null });
      return false;
    }
    const editor = useGraphEditor.getState();
    const ok = editor.dispatchMany(patches);
    if (!ok) {
      set({ error: editor.lastError ?? 'The graph changed while the assistant was working. Ask again.' });
      return false;
    }
    const focus = pending.focusNodeIds.filter((id) => useGraphEditor.getState().ir?.nodes.some((n) => n.id === id));
    if (focus.length > 0) {
      useGraphEditor.getState().setSelection({ nodeIds: focus, edgeIds: [] });
      useGraphEditor.getState().requestFocus(focus);
    }
    set((state) => {
      const messages = [...state.messages];
      for (let index = messages.length - 1; index >= 0; index -= 1) {
        if (messages[index].role === 'assistant') {
          messages[index] = { ...messages[index], pending: false, applied: true };
          break;
        }
      }
      return { pending: null, pendingDocumentId: null, error: null, messages };
    });
    persist(useGraphEditor.getState().workflowId, get().messages);
    return true;
  },

  discardPending: () => {
    set((state) => ({
      pending: null,
      pendingDocumentId: null,
      error: null,
      messages: state.messages.map((message) => (message.pending ? { ...message, pending: false } : message)),
    }));
    persist(useGraphEditor.getState().workflowId, get().messages);
  },

  reset: () => {
    activeController?.abort();
    activeController = null;
    const key = storageKey(useGraphEditor.getState().workflowId);
    if (key) {
      try {
        window.sessionStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    }
    set({
      messages: [],
      pending: null,
      pendingDocumentId: null,
      error: null,
      status: 'idle',
      steps: [],
      progressLabel: null,
    });
  },
}));

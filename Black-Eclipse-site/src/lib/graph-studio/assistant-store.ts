// ── Graph assistant state (transient + per-workflow transcript) ─────────────
// A chat thread over the CURRENT editor document. The proposal itself is never
// persisted (an op list can go stale), but the transcript is kept per workflow
// in sessionStorage so closing the dock or reloading does not lose context.

import { create } from 'zustand';
import { useGraphEditor } from './editor-store';
import {
  answerAssistantClarification,
  assistGraphStream,
  cancelAssistRun,
  decideAssistantApproval,
  pauseAssistRun,
  resumeAssistRun,
  type AssistantRequest,
  type AssistantResult,
  type AssistantRunResult,
  type AssistantTurn,
  type AssistantApproval,
} from './assistant-client';
import { MAX_THREADS, loadStored, newThreadId, persist, saveStored, storageKey } from './assistant-storage';
import { graphEditOpsToPatches } from './assistant-ops';

export interface AssistantChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  applied?: boolean;
  error?: boolean;
  streaming?: boolean;
  runs?: AssistantRunResult[];
}

export interface AssistantStep {
  id: string;
  label: string;
  state: 'running' | 'ok' | 'error';
}

export interface AssistantThread {
  id: string;
  title: string;
  updatedAt: number;
  messages: AssistantChatMessage[];
  pending?: AssistantResult | null;
  pendingDocumentId?: string | null;
}

interface AssistantState {
  messages: AssistantChatMessage[];
  threads: AssistantThread[];
  activeThreadId: string | null;
  status: 'idle' | 'running' | 'paused' | 'awaiting_approval';
  runId: string | null;
  pending: AssistantResult | null;
  /** A mid-turn effect approval (e.g. a test run) that is blocking the stream. */
  toolApproval: AssistantApproval | null;
  /** The IR id the proposal was computed against. Guards cross-workflow apply. */
  pendingDocumentId: string | null;
  error: string | null;
  progressLabel: string | null;
  steps: AssistantStep[];
  autoApply: boolean;
  setAutoApply: (value: boolean) => void;
  hydrate: (workflowId: string | null) => void;
  newThread: () => void;
  selectThread: (id: string) => void;
  send: (instruction: string, mode?: 'edit' | 'ask', model?: { provider?: string; model?: string }) => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  cancel: () => void;
  applyPending: () => boolean;
  decidePending: (approve: boolean, remember: boolean) => Promise<void>;
  decideToolApproval: (approve: boolean, remember: boolean) => Promise<void>;
  answerClarification: (answer: string) => Promise<void>;
  discardPending: () => void;
  reset: () => void;
}

const AUTO_APPLY_KEY = 'be_graph_assistant_autoapply_v1';
let counter = 0;
let activeController: AbortController | null = null;

function nextId(prefix = 'm'): string {
  counter += 1;
  return `${prefix}_${Date.now().toString(36)}_${counter}`;
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
  threads: [],
  activeThreadId: null,
  status: 'idle',
  runId: null,
  pending: null,
  toolApproval: null,
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
    activeController?.abort();
    activeController = null;
    if (!storageKey(workflowId)) {
      set({ messages: [], threads: [], activeThreadId: null, pending: null, toolApproval: null, pendingDocumentId: null, error: null, steps: [], progressLabel: null, status: 'idle', runId: null });
      return;
    }
    const stored = loadStored(workflowId);
    const active = stored.threads.find((thread) => thread.id === stored.activeThreadId) ?? null;
    set({
      threads: stored.threads,
      activeThreadId: stored.activeThreadId,
      messages: active?.messages ?? [],
      pending: active?.pending ?? null,
      toolApproval: null,
      pendingDocumentId: active?.pendingDocumentId ?? null,
      error: null,
      steps: [],
      progressLabel: null,
      status: 'idle',
      runId: null,
    });
  },

  newThread: () => {
    activeController?.abort();
    activeController = null;
    const workflowId = useGraphEditor.getState().workflowId;
    const stored = loadStored(workflowId);
    const id = newThreadId();
    const threads = [
      { id, title: 'New conversation', updatedAt: Date.now(), messages: [], pending: null, pendingDocumentId: null },
      ...stored.threads,
    ].slice(0, MAX_THREADS);
    saveStored(workflowId, { threads, activeThreadId: id });
    set({
      threads,
      activeThreadId: id,
      messages: [],
      pending: null,
      toolApproval: null,
      pendingDocumentId: null,
      error: null,
      status: 'idle',
      runId: null,
      steps: [],
      progressLabel: null,
    });
  },

  selectThread: (id) => {
    activeController?.abort();
    activeController = null;
    const workflowId = useGraphEditor.getState().workflowId;
    const stored = loadStored(workflowId);
    const thread = stored.threads.find((item) => item.id === id);
    if (!thread) return;
    saveStored(workflowId, { threads: stored.threads, activeThreadId: id });
    set({
      threads: stored.threads,
      activeThreadId: id,
      messages: thread.messages,
      pending: thread.pending ?? null,
      toolApproval: null,
      pendingDocumentId: thread.pendingDocumentId ?? null,
      error: null,
      status: 'idle',
      runId: null,
      steps: [],
      progressLabel: null,
    });
  },

  send: async (instruction, mode = 'edit', model) => {
    const text = instruction.trim();
    if (!text || get().status !== 'idle') return;
    const editor = useGraphEditor.getState();
    if (!editor.ir) {
      set({ error: 'Open a workflow before asking the assistant to change it.' });
      return;
    }

    const history: AssistantTurn[] = get()
      .messages.filter((message) => !message.pending && !message.error)
      .slice(-8)
      .map((message) => ({ role: message.role, content: message.content }));

    if (!get().activeThreadId) {
      const thread: AssistantThread = {
        id: newThreadId(),
        title: 'New conversation',
        updatedAt: Date.now(),
        messages: [],
        pending: null,
        pendingDocumentId: null,
      };
      const threads = [thread, ...get().threads].slice(0, MAX_THREADS);
      saveStored(editor.workflowId, { threads, activeThreadId: thread.id });
      set({ threads, activeThreadId: thread.id });
    }

    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    const requireApproval = !get().autoApply;

    set((state) => ({
      status: 'running',
      runId: null,
      error: null,
      pending: null,
      toolApproval: null,
      pendingDocumentId: null,
      progressLabel: 'Reading the workflow',
      steps: [],
      messages: [...state.messages, { id: nextId(), role: 'user', content: text }],
    }));

    // Persist the user turn immediately: a reload mid-run should not lose the
    // question, even though the answer is not ready yet.
    const initialStored = persist(editor.workflowId, get().messages, null, null);
    if (initialStored) set({ threads: initialStored.threads, activeThreadId: initialStored.activeThreadId });

    try {
      const result = await assistGraphStream(
        {
          instruction: text,
          ir: editor.ir,
          mode,
          selection: editor.selection,
          history,
          lastRun: lastRunContext(),
          requireApproval,
          model,
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            if (event.type === 'run') {
              set({ runId: event.runId, status: 'running' });
            } else if (event.type === 'text_delta') {
              set((state) => {
                const messages = [...state.messages];
                const last = messages[messages.length - 1];
                if (last && last.role === 'assistant' && last.streaming) {
                  messages[messages.length - 1] = { ...last, content: last.content + event.text };
                } else {
                  messages.push({ id: nextId(), role: 'assistant', content: event.text, streaming: true });
                }
                return { messages };
              });
            } else if (event.type === 'status') {
              if (event.stage === 'paused') set({ status: 'paused', progressLabel: event.label });
              else if (event.stage === 'running' && get().status === 'paused') set({ status: 'running', progressLabel: event.label });
              else set({ progressLabel: event.label });
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
            } else if (event.type === 'approval_requested') {
              set({ toolApproval: event.approval, status: 'awaiting_approval', progressLabel: 'Waiting for approval' });
            } else if (event.type === 'approval_resolved') {
              set({ toolApproval: null, status: 'running', progressLabel: 'Approval recorded' });
            } else if (event.type === 'cancelled') {
              set({ status: 'idle', progressLabel: null });
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
        && result.warnings.length === 0
        && !result.approval;
      set((state) => {
        const messages = [...state.messages];
        const last = messages[messages.length - 1];
        const streamed = last && last.role === 'assistant' && last.streaming ? last.content : '';
        const content = reply && reply !== 'Done.' ? reply : streamed || reply;
        const next = {
          id: last && last.role === 'assistant' && last.streaming ? last.id : nextId(),
          role: 'assistant' as const,
          content,
          pending: hasEdits && !autoApply,
          streaming: false,
          runs: result.runs ?? [],
        };
        if (last && last.role === 'assistant' && last.streaming) {
          messages[messages.length - 1] = { ...last, ...next };
        } else {
          messages.push(next);
        }
        return {
          status: 'idle',
          runId: null,
          progressLabel: null,
          steps: [],
          toolApproval: null,
          pending: hasEdits || result.clarification ? result : null,
          pendingDocumentId: hasEdits ? editor.ir?.id ?? null : null,
          messages,
        };
      });
      if (autoApply) get().applyPending();
      if (result.errors.length > 0 && !autoApply) {
        set({ error: result.errors[0]?.message ?? 'The proposal is not valid yet.' });
      }
      const stored = persist(useGraphEditor.getState().workflowId, get().messages, get().pending, get().pendingDocumentId);
      if (stored) set({ threads: stored.threads, activeThreadId: stored.activeThreadId });
    } catch (err) {
      const aborted = err instanceof DOMException
        ? err.name === 'AbortError'
        : err instanceof Error && err.name === 'AbortError';
      if (aborted) {
        set((state) => ({
          status: 'idle',
          runId: null,
          progressLabel: null,
          pending: null,
          toolApproval: null,
          pendingDocumentId: null,
          steps: [],
          messages: [
            ...state.messages.map((message) => (message.streaming ? { ...message, streaming: false } : message)),
            { id: nextId(), role: 'assistant', content: 'Stopped.' },
          ],
        }));
      } else {
        const message = err instanceof Error ? err.message : 'The assistant failed';
        set((state) => ({
          status: 'idle',
          runId: null,
          progressLabel: null,
          pending: null,
          toolApproval: null,
          pendingDocumentId: null,
          steps: [],
          error: message,
          messages: [
            ...state.messages.map((item) => (item.streaming ? { ...item, streaming: false } : item)),
            { id: nextId(), role: 'assistant', content: message, error: true },
          ],
        }));
      }
      const stored = persist(useGraphEditor.getState().workflowId, get().messages, get().pending, get().pendingDocumentId);
      if (stored) set({ threads: stored.threads, activeThreadId: stored.activeThreadId });
    } finally {
      if (activeController === controller) activeController = null;
    }
  },

  cancel: () => {
    const { runId } = get();
    if (runId) void cancelAssistRun(runId).catch(() => {});
    activeController?.abort();
  },

  pause: async () => {
    const { runId, status } = get();
    if (status !== 'running' || !runId) return;
    set({ status: 'paused', progressLabel: 'Paused' });
    try {
      await pauseAssistRun(runId);
    } catch (err) {
      set({ status: 'running', error: err instanceof Error ? err.message : 'The assistant could not pause.' });
    }
  },

  resume: async () => {
    const { runId, status } = get();
    if (status !== 'paused' || !runId) return;
    set({ status: 'running', progressLabel: 'Resumed' });
    try {
      await resumeAssistRun(runId);
    } catch (err) {
      set({ status: 'paused', error: err instanceof Error ? err.message : 'The assistant could not resume.' });
    }
  },

  decidePending: async (approve, remember) => {
    const { pending } = get();
    if (!pending) return;
    const approval = pending.approval;
    if (approval) {
      if (approval.status === 'denied' || approval.status === 'expired') {
        set({ error: 'This change was already denied. Ask for a different change.' });
        return;
      }
      try {
        const decided = await decideAssistantApproval(approval.id, approve, remember);
        const status = decided.approval?.status;
        if (approve && status && status !== 'approved') {
          set({ error: 'The runtime did not approve this change. Ask again.' });
          return;
        }
      } catch (err) {
        set({ error: err instanceof Error ? err.message : 'The approval could not be recorded.' });
        return;
      }
    }
    if (remember) get().setAutoApply(true);
    if (approve) get().applyPending();
    else get().discardPending();
  },

  decideToolApproval: async (approve, remember) => {
    const { toolApproval } = get();
    if (!toolApproval) return;
    try {
      const decided = await decideAssistantApproval(toolApproval.id, approve, remember);
      const status = decided.approval?.status;
      if (approve && status && status !== 'approved') {
        set({ error: 'The runtime did not approve this tool call.' });
        return;
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'The approval could not be recorded.' });
      return;
    }
    if (remember) get().setAutoApply(true);
    set({ toolApproval: null, status: 'running' });
  },

  answerClarification: async (answer) => {
    const { pending } = get();
    const clarification = pending?.clarification;
    if (!clarification) return;
    const value = answer.trim();
    try {
      if (clarification.id) await answerAssistantClarification(clarification.id, value);
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'The answer could not be recorded.' });
      return;
    }
    get().discardPending();
    if (value) await get().send(value, 'edit');
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
    const stored = persist(useGraphEditor.getState().workflowId, get().messages, get().pending, get().pendingDocumentId);
    if (stored) set({ threads: stored.threads, activeThreadId: stored.activeThreadId });
    return true;
  },

  discardPending: () => {
    set((state) => ({
      pending: null,
      pendingDocumentId: null,
      error: null,
      messages: state.messages.map((message) => (message.pending ? { ...message, pending: false } : message)),
    }));
    const stored = persist(useGraphEditor.getState().workflowId, get().messages, get().pending, get().pendingDocumentId);
    if (stored) set({ threads: stored.threads, activeThreadId: stored.activeThreadId });
  },

  reset: () => {
    activeController?.abort();
    activeController = null;
    set({
      messages: [],
      threads: [],
      activeThreadId: null,
      pending: null,
      pendingDocumentId: null,
      error: null,
      status: 'idle',
      runId: null,
      steps: [],
      progressLabel: null,
      toolApproval: null,
    });
  },
}));

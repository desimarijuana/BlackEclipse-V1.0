// ── Graph assistant persistence ─────────────────────────────────────────────
// Durable per-workflow conversation threads. Kept apart from the zustand store so
// the store stays about state transitions and this module owns the storage
// shape, migration from the old session-only transcript, and compaction.

import type { AssistantResult } from './assistant-client';
import type { AssistantChatMessage, AssistantThread } from './assistant-store';

export const STORAGE_PREFIX = 'be_graph_assistant_threads_v2:';
const LEGACY_PREFIX = 'be_graph_assistant_v1:';
export const MAX_THREADS = 30;
const MAX_MESSAGES = 60;

export interface StoredAssistantState {
  threads: AssistantThread[];
  activeThreadId: string | null;
}

let counter = 0;

export function newThreadId(): string {
  counter += 1;
  return `t_${Date.now().toString(36)}_${counter}`;
}

export function storageKey(workflowId: string | null | undefined): string | null {
  return workflowId ? `${STORAGE_PREFIX}${workflowId}` : null;
}

function threadTitle(messages: AssistantChatMessage[], fallback = 'New conversation'): string {
  const first = messages.find((message) => message.role === 'user' && message.content.trim());
  return (first?.content ?? fallback).trim().slice(0, 72) || fallback;
}

function cleanMessages(messages: AssistantChatMessage[]): AssistantChatMessage[] {
  return messages
    .filter((message) => message && (message.role === 'user' || message.role === 'assistant') && typeof message.content === 'string')
    .slice(-MAX_MESSAGES)
    .map(({ id, role, content, applied, error, runs }) => ({ id, role, content, applied, error, runs }));
}

function compactPending(pending: AssistantResult | null | undefined): AssistantResult | null {
  if (!pending) return null;
  // The IR is the editor's own document; the proposal only needs the validated
  // operations and the document id it was computed against.
  return { ...pending, ir: undefined };
}

function parseThreads(raw: string | null): StoredAssistantState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredAssistantState>;
    if (!Array.isArray(parsed.threads)) return null;
    const threads = parsed.threads
      .filter((thread) => thread && typeof thread.id === 'string' && Array.isArray(thread.messages))
      .map((thread) => ({
        id: thread.id,
        title: typeof thread.title === 'string' ? thread.title : threadTitle(thread.messages),
        updatedAt: typeof thread.updatedAt === 'number' ? thread.updatedAt : Date.now(),
        messages: cleanMessages(thread.messages as AssistantChatMessage[]),
        pending: (thread.pending as AssistantResult | null | undefined) ?? null,
        pendingDocumentId: typeof thread.pendingDocumentId === 'string' ? thread.pendingDocumentId : null,
      }))
      .slice(0, MAX_THREADS);
    const activeThreadId = typeof parsed.activeThreadId === 'string'
      && threads.some((thread) => thread.id === parsed.activeThreadId)
      ? parsed.activeThreadId
      : threads[0]?.id ?? null;
    return { threads, activeThreadId };
  } catch {
    return null;
  }
}

export function loadStored(workflowId: string | null | undefined): StoredAssistantState {
  const key = storageKey(workflowId);
  if (!key || typeof window === 'undefined') return { threads: [], activeThreadId: null };
  try {
    const stored = parseThreads(window.localStorage.getItem(key));
    if (stored) return stored;
    // Migrate the old session-only single transcript into one durable thread.
    const legacyKey = workflowId ? `${LEGACY_PREFIX}${workflowId}` : null;
    const legacy = legacyKey ? window.sessionStorage.getItem(legacyKey) : null;
    if (legacy) {
      const parsed = JSON.parse(legacy) as AssistantChatMessage[];
      if (Array.isArray(parsed) && parsed.length > 0) {
        const messages = cleanMessages(parsed);
        const id = newThreadId();
        const migrated = {
          threads: [{ id, title: threadTitle(messages), updatedAt: Date.now(), messages, pending: null, pendingDocumentId: null }],
          activeThreadId: id,
        };
        saveStored(workflowId, migrated);
        window.sessionStorage.removeItem(legacyKey as string);
        return migrated;
      }
    }
  } catch {
    /* storage can be unavailable; the in-memory thread still works */
  }
  return { threads: [], activeThreadId: null };
}

export function saveStored(workflowId: string | null | undefined, state: StoredAssistantState): void {
  const key = storageKey(workflowId);
  if (!key || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(state));
  } catch {
    /* quota/private mode — the in-memory thread still works */
  }
}

export function persist(
  workflowId: string | null | undefined,
  messages: AssistantChatMessage[],
  pending?: AssistantResult | null,
  pendingDocumentId?: string | null,
): StoredAssistantState | null {
  if (!storageKey(workflowId)) return null;
  const stored = loadStored(workflowId);
  const id = stored.activeThreadId ?? newThreadId();
  const clean = cleanMessages(messages);
  const thread: AssistantThread = {
    id,
    title: threadTitle(clean),
    updatedAt: Date.now(),
    messages: clean,
    pending: compactPending(pending),
    pendingDocumentId: pendingDocumentId ?? null,
  };
  const threads = [thread, ...stored.threads.filter((item) => item.id !== id)]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_THREADS);
  const next = { threads, activeThreadId: id };
  saveStored(workflowId, next);
  return next;
}

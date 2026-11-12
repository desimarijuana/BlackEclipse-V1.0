// ── Agent Workspace — restore from a chat conversation ───────────────────────
// When a user opens a past chat, point the workspace at that conversation's most
// recent run so its panels (Context, Output, Changes) reflect the chat being
// viewed instead of the last live run. The run is rebuilt from the persisted
// trace + run record (`history.ts`); the runtime's session→run list is the
// fallback for older chats whose messages predate `runId`.

import type { Message } from '@/types/chat';
import { getChatSession } from '@/lib/harness/clients/eclipse-memory-browser';
import { loadRunSnapshot } from './history';
import { useWorkspaceStore } from './store';

/** The harness run id of a conversation's most recent turn, if any. */
export function latestRunId(messages: Message[] | undefined): string | undefined {
  if (!messages) return undefined;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const id = messages[i]?.runId;
    if (id) return id;
  }
  return undefined;
}

/**
 * Point the workspace store at a conversation's most recent run, or clear it
 * when the conversation has no runs. Never clobbers a live run that started
 * while the history load was in flight (opening a chat then sending immediately).
 */
export async function restoreWorkspaceForChat(
  messages: Message[] | undefined,
  chatId: string | null,
): Promise<void> {
  const store = useWorkspaceStore.getState();
  let runId = latestRunId(messages);
  if (!runId && chatId) {
    try {
      const { runs } = await getChatSession(chatId);
      runId = runs.length > 0 ? runs[runs.length - 1] : undefined;
    } catch {
      /* runtime unavailable — fall through to clear */
    }
  }
  if (!runId) {
    store.clear();
    return;
  }
  try {
    const snapshot = await loadRunSnapshot(runId);
    const current = useWorkspaceStore.getState();
    const live = current.state.execution.status === 'running' || current.state.execution.status === 'planning';
    if (current.runId && current.runId !== runId && live) return;
    store.loadRun(runId, snapshot);
  } catch {
    store.clear();
  }
}

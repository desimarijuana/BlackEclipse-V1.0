// ── Which conversation owns the live Agent Workspace ────────────────────────
//
// The workspace is a single projection with one run bound at a time. With
// parallel conversations, every stream used to call `bindRun`, resetting the
// projection for whichever run emitted last. This tiny registry lets the
// manager say "these run ids belong to that chat" and lets the workspace ingest
// only the focused conversation's run. No imports, so it cannot create a cycle
// between the run manager and the workspace store.

let focusedChatId: string | null = null;
const runChat = new Map<string, string>();

export function setFocusedChat(chatId: string | null | undefined): void {
  // A blank id (new-chat landing) keeps the last focused conversation rather
  // than letting every background run project into the workspace at once.
  if (chatId && chatId.length > 0) focusedChatId = chatId;
}

export function bindRunChat(runId: string, chatId: string): void {
  if (!runId || !chatId) return;
  runChat.set(runId, chatId);
}

export function unbindRunChat(runId: string): void {
  if (runId) runChat.delete(runId);
}

/** Whether a frame belongs to the conversation the workspace is showing. */
export function shouldIngestRun(runId: string | undefined): boolean {
  if (!runId || !focusedChatId) return true;
  const chatId = runChat.get(runId);
  // An untagged run (an older runtime/frame) is allowed rather than dropped.
  return !chatId || chatId === focusedChatId;
}

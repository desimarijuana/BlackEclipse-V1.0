// ── Forking a conversation ───────────────────────────────────────────────────
//
// A fork is a REAL new conversation, not a UI-only branch: it gets its own id,
// transcript and session folder so continuing it can never mutate the source.
//
// Pure (no DOM, no fs) so the clone rules are unit-testable. The session-file
// copy lives on the server (`cloneSessionContext`); this module only builds the
// conversation the shell selects and persists.

import type { Message } from '@/types/chat';
import type { Conversation, ConversationFork } from './chat-organization';

export interface ForkOptions {
  /**
   * Cut the fork at this message (inclusive). Omit to fork the whole
   * conversation. When the id is absent the whole conversation is copied.
   */
  messageId?: string;
  /** Override for tests; defaults to `Date.now()` + random suffix. */
  newChatId?: () => string;
  /** Override for tests; defaults to a per-fork message-id prefix. */
  newMessageId?: (index: number) => string;
  /** Override for tests; defaults to `Date.now()`. */
  now?: number;
}

/** A collision-safe conversation id accepted by the session store's validator. */
export function newChatId(now = Date.now(), rand = Math.random()): string {
  return `chat_${now}_${rand.toString(36).slice(2, 8)}`;
}

/** "Research NVDA" → "Research NVDA (fork)". */
export function forkTitle(title: string): string {
  const base = title.trim() || 'Untitled Session';
  return `${base} (fork)`;
}

/**
 * Clone the turns that belong to the fork, giving every message a NEW id.
 * Independent ids matter: the same message id must not be shared across two
 * transcripts (feedback, canvas targets and quote jump links are per-chat).
 *
 * Live-only fields are cleared — a fork is not waiting on an approval or a
 * clarification that belonged to the source run. Quotes are remapped to the
 * copied message ids so their jump-to-source still works inside the fork.
 */
export function cloneMessages(
  messages: Message[],
  options: { newMessageId?: (index: number) => string } = {},
): Message[] {
  const makeId = options.newMessageId
    ?? ((index: number) => `m_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}_${index}`);
  const idMap = new Map<string, string>();
  const cloned = messages.map((message, index) => {
    const id = makeId(index);
    idMap.set(message.id, id);
    const next = { ...message, id };
    // A fork is not waiting on a decision that belonged to the source run.
    delete next.pendingApproval;
    delete next.pendingClarification;
    return next;
  });
  return cloned.map((message) => {
    if (!message.quote) return message;
    const mapped = idMap.get(message.quote.messageId);
    if (!mapped || mapped === message.quote.messageId) return message;
    return { ...message, quote: { ...message.quote, messageId: mapped } };
  });
}

/**
 * Build the forked conversation. The fork lives beside the source (same folder,
 * colour, tags) but is never pinned, archived or trashed. Provenance is
 * snapshotted so it survives deleting the source.
 */
export function forkConversation(source: Conversation, options: ForkOptions = {}): Conversation {
  const now = options.now ?? Date.now();
  let end = source.messages.length;
  if (options.messageId) {
    const index = source.messages.findIndex((message) => message.id === options.messageId);
    // An id that no longer exists must not silently fork an empty/whole chat.
    end = index === -1 ? source.messages.length : index + 1;
  }
  const messages = cloneMessages(source.messages.slice(0, end), {
    newMessageId: options.newMessageId,
  });
  const forkedFrom: ConversationFork = {
    conversationId: source.id,
    title: source.title,
    at: now,
    ...(options.messageId ? { messageId: options.messageId } : {}),
  };
  return {
    id: (options.newChatId ?? (() => newChatId(now)))(),
    title: forkTitle(source.title),
    messages,
    timestamp: now,
    createdAt: now,
    forkedFrom,
    folderId: source.folderId ?? null,
    color: source.color ?? null,
    pinned: false,
    tags: [...(source.tags ?? [])],
  };
}

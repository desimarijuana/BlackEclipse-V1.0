// Client helpers for server-side conversation transcripts. Thin wrappers over
// /api/chat/transcript — shaped like the localStorage Conversation rows so the
// ChatBot tab can persist and hydrate without a second model.

import { normalizeConversation, type Conversation } from "./chat-organization";

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((body as { error?: string }).error || `Request failed (${res.status})`);
  }
  return body as T;
}

/**
 * Every conversation persisted on the server, normalized and newest-first.
 *
 * `?summary=1` returns metadata only (no message bodies): the full history is
 * tens of MB on a long-lived install, and fetching it on every app boot made
 * the single Node thread serialize + gzip the whole transcript before the rest
 * of the page could load. Bodies come from `getServerConversation` when a chat
 * is opened.
 */
export async function listServerConversations(): Promise<Conversation[]> {
  const res = await fetch("/api/chat/transcript?summary=1", { cache: "no-store" });
  const body = await json<{ conversations: unknown[] }>(res);
  const raw = Array.isArray(body.conversations) ? body.conversations : [];
  return raw
    .map(normalizeConversation)
    .filter((c): c is Conversation => c !== null)
    .sort((a, b) => b.timestamp - a.timestamp);
}

/** One conversation WITH its message bodies (lazy hydration on open). */
export async function getServerConversation(chatId: string): Promise<Conversation | null> {
  const res = await fetch(
    `/api/chat/transcript?chatId=${encodeURIComponent(chatId)}`,
    { cache: "no-store" },
  );
  const body = await json<{ transcript: unknown }>(res);
  return normalizeConversation(body.transcript);
}

/** Upsert one conversation on the server. */
export async function saveServerConversation(conv: Conversation): Promise<void> {
  const res = await fetch("/api/chat/transcript", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chatId: conv.id, transcript: conv }),
  });
  await json<{ success: true }>(res);
}

/** Delete one conversation's server copy. */
export async function deleteServerConversation(chatId: string): Promise<void> {
  const res = await fetch(`/api/chat/transcript?chatId=${encodeURIComponent(chatId)}`, {
    method: "DELETE",
  });
  await json<{ success: true }>(res);
}

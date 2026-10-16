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

/** Every conversation persisted on the server, normalized and newest-first. */
export async function listServerConversations(): Promise<Conversation[]> {
  const res = await fetch("/api/chat/transcript", { cache: "no-store" });
  const body = await json<{ conversations: unknown[] }>(res);
  const raw = Array.isArray(body.conversations) ? body.conversations : [];
  return raw
    .map(normalizeConversation)
    .filter((c): c is Conversation => c !== null)
    .sort((a, b) => b.timestamp - a.timestamp);
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

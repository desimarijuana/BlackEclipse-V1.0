// Client helpers for a conversation's session workspace. Thin wrappers over
// /api/chat/session — no logic beyond request shaping and honest errors.

import type { Checkpoint, CheckpointSnapshot, FileProvenance, SessionFile, SessionFileKind, SessionInfo } from "./session-types";

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((body as { error?: string }).error || `Request failed (${res.status})`);
  }
  return body as T;
}

export async function fetchSession(chatId: string): Promise<SessionInfo> {
  const res = await fetch(`/api/chat/session?chatId=${encodeURIComponent(chatId)}`, {
    cache: "no-store",
  });
  const body = await json<{ session: SessionInfo }>(res);
  return body.session;
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function uploadSessionFile(
  chatId: string,
  kind: SessionFileKind,
  name: string,
  bytes: Uint8Array,
  meta?: FileProvenance,
): Promise<SessionFile> {
  const res = await fetch("/api/chat/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chatId, kind, name, contentBase64: toBase64(bytes), ...(meta ? { meta } : {}) }),
  });
  const body = await json<{ file: SessionFile }>(res);
  return body.file;
}

export async function deleteSessionFile(
  chatId: string,
  kind: SessionFileKind,
  name: string
): Promise<void> {
  const params = new URLSearchParams({ chatId, kind, name });
  const res = await fetch(`/api/chat/session?${params.toString()}`, { method: "DELETE" });
  await json<{ success: true }>(res);
}

/** Copy a conversation's context documents into a new (forked) conversation. */
export async function cloneSessionContext(fromChatId: string, toChatId: string): Promise<number> {
  const res = await fetch("/api/chat/session/clone", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fromChatId, toChatId }),
  });
  const body = await json<{ copied: number }>(res);
  return typeof body.copied === "number" ? body.copied : 0;
}

export function sessionFileUrl(chatId: string, kind: SessionFileKind, name: string): string {
  const params = new URLSearchParams({ chatId, kind, name });
  return `/api/chat/session/file?${params.toString()}`;
}

// ── Checkpoints ──────────────────────────────────────────────────────────────

export async function listCheckpoints(chatId: string): Promise<Checkpoint[]> {
  const res = await fetch(`/api/chat/checkpoints?chatId=${encodeURIComponent(chatId)}`, { cache: "no-store" });
  const body = await json<{ checkpoints: Checkpoint[] }>(res);
  return body.checkpoints;
}

export async function createCheckpoint(
  chatId: string,
  label: string,
  messages: Array<{ id: string; role: string; content: string }>
): Promise<Checkpoint> {
  const res = await fetch("/api/chat/checkpoints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chatId, label, messages }),
  });
  const body = await json<{ checkpoint: Checkpoint }>(res);
  return body.checkpoint;
}

export async function readCheckpoint(chatId: string, id: string): Promise<CheckpointSnapshot> {
  const params = new URLSearchParams({ chatId, id });
  const res = await fetch(`/api/chat/checkpoints?${params.toString()}`, { cache: "no-store" });
  const body = await json<{ snapshot: CheckpointSnapshot }>(res);
  return body.snapshot;
}

export async function deleteCheckpoint(chatId: string, id: string): Promise<void> {
  const params = new URLSearchParams({ chatId, id });
  const res = await fetch(`/api/chat/checkpoints?${params.toString()}`, { method: "DELETE" });
  await json<{ success: true }>(res);
}

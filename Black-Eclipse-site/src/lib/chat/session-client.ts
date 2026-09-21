// Client helpers for a conversation's session workspace. Thin wrappers over
// /api/chat/session — no logic beyond request shaping and honest errors.

import type { SessionFile, SessionFileKind, SessionInfo } from "./session-types";

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
  bytes: Uint8Array
): Promise<SessionFile> {
  const res = await fetch("/api/chat/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chatId, kind, name, contentBase64: toBase64(bytes) }),
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

export function sessionFileUrl(chatId: string, kind: SessionFileKind, name: string): string {
  const params = new URLSearchParams({ chatId, kind, name });
  return `/api/chat/session/file?${params.toString()}`;
}

// ─── Channel Gateway BROWSER client ──────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/channels/**`), which proxy to the
// Python runtime. This module MUST stay client-safe: no Node process or
// filesystem APIs, and no server-only runtime bootstrap (that lives in the
// server-only `channels-client.ts`). Fetch only.

import type {
  ChannelBindingView,
  ChannelConfigView,
  ChannelKind,
  ChannelLinkCode,
  ChannelMessageView,
  ChannelsHealth,
  ControlScope,
} from "./channels-client";

// Type-only re-exports — erased at compile time, so no server code ships.
export type {
  ChannelBindingView,
  ChannelConfigView,
  ChannelKind,
  ChannelLinkCode,
  ChannelMessageView,
  ChannelsHealth,
  ControlScope,
};

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function channelsHealth(): Promise<ChannelsHealth> {
  return api<ChannelsHealth>("/api/channels/health");
}

export async function listChannels(): Promise<ChannelConfigView[]> {
  const body = await api<{ channels: ChannelConfigView[] }>("/api/channels");
  return body.channels ?? [];
}

export async function configureChannel(
  kind: ChannelKind,
  enabled: boolean,
  config: Record<string, unknown>,
): Promise<ChannelConfigView> {
  const body = await api<{ channel: ChannelConfigView }>(`/api/channels/${encodeURIComponent(kind)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled, config }),
  });
  return body.channel;
}

export async function deleteChannel(kind: ChannelKind): Promise<boolean> {
  const body = await api<{ deleted: boolean }>(`/api/channels/${encodeURIComponent(kind)}`, { method: "DELETE" });
  return Boolean(body.deleted);
}

export async function createLinkCode(kind: ChannelKind, scope: ControlScope): Promise<ChannelLinkCode> {
  const body = await api<{ linkCode: ChannelLinkCode }>("/api/channels/link-code", {
    method: "POST",
    body: JSON.stringify({ kind, scope }),
  });
  return body.linkCode;
}

export async function listBindings(kind?: ChannelKind): Promise<ChannelBindingView[]> {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  const body = await api<{ bindings: ChannelBindingView[] }>(`/api/channels/bindings${q}`);
  return body.bindings ?? [];
}

export async function setBindingScope(bindingId: string, scope: ControlScope): Promise<void> {
  await api(`/api/channels/bindings/${encodeURIComponent(bindingId)}/scope`, {
    method: "POST",
    body: JSON.stringify({ scope }),
  });
}

export async function revokeBinding(bindingId: string): Promise<boolean> {
  const body = await api<{ revoked: boolean }>(`/api/channels/bindings/${encodeURIComponent(bindingId)}`, {
    method: "DELETE",
  });
  return Boolean(body.revoked);
}

export async function sendChannelMessage(
  kind: ChannelKind,
  chat: string,
  text: string,
): Promise<{ ok: boolean; reason?: string }> {
  return api<{ ok: boolean; reason?: string }>("/api/channels/send", {
    method: "POST",
    body: JSON.stringify({ kind, chat, text }),
  });
}

export async function listChannelMessages(opts: { kind?: ChannelKind; limit?: number } = {}): Promise<ChannelMessageView[]> {
  const params = new URLSearchParams();
  if (opts.kind) params.set("kind", opts.kind);
  params.set("limit", String(opts.limit ?? 50));
  const body = await api<{ messages: ChannelMessageView[] }>(`/api/channels/messages?${params}`);
  return body.messages ?? [];
}

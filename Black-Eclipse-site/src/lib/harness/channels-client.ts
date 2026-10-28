// ─── Channel Gateway front door ──────────────────────────────────────────────
// Thin, typed proxy over the Python runtime's /channels* routes (Settings ›
// Connections). It adds NO channel logic: the runtime owns binding, scope,
// confirmation and provider state. Config values are returned REDACTED by the
// runtime (presence flags only), so a credential never reaches the client.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type ChannelKind =
  | "telegram"
  | "discord"
  | "email"
  | "slack"
  | "whatsapp"
  | "teams"
  | "google_chat"
  | "lark"
  | "webhook";
export type ControlScope = "viewer" | "assistant" | "operator";

export interface ChannelFieldView {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  placeholder: string;
  hint: string;
}

export interface ChannelConfigView {
  channel: ChannelKind;
  label?: string;
  description?: string;
  inboundMode?: "poll" | "push" | "both" | "none";
  fields?: ChannelFieldView[];
  enabled: boolean;
  configured: boolean;
  config: Record<string, unknown>;
  /** Names of credentials stored in the encrypted vault (never their values). */
  secrets?: string[];
  /** Whether credentials are encrypted at rest; false = legacy literal config. */
  secretsEncrypted?: boolean;
  updatedAt: string | null;
}

export interface ChannelBindingView {
  id: string;
  kind: ChannelKind;
  externalId: string;
  externalChat: string;
  displayName: string;
  userId: string | null;
  tenantId: string | null;
  scope: ControlScope;
  status: "active" | "revoked";
  createdAt: string;
  lastSeenAt: string | null;
}

export interface ChannelLinkCode {
  code: string;
  kind: ChannelKind;
  scope: ControlScope;
  expiresAt: string;
}

export interface ChannelMessageView {
  id: string;
  kind: ChannelKind;
  direction: "in" | "out";
  text: string;
  status: string;
  createdAt: string;
}

export interface ChannelsHealth {
  enabled: boolean;
  polling: boolean;
  started: boolean;
  activePollers: string[];
  channels: ChannelConfigView[];
  bindings: number;
  turnsPerHour: number;
  model: { provider: string; model: string };
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const { timeoutMs = 30_000, ...rest } = init;
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(rest.headers ?? {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function channelsHealth(): Promise<ChannelsHealth> {
  return request<ChannelsHealth>("/channels/health", { method: "GET" });
}

export async function listChannels(): Promise<ChannelConfigView[]> {
  const body = await request<{ channels: ChannelConfigView[] }>("/channels", { method: "GET" });
  return body.channels ?? [];
}

export async function configureChannel(
  kind: ChannelKind,
  enabled: boolean,
  config: Record<string, unknown>,
): Promise<ChannelConfigView> {
  const body = await request<{ channel: ChannelConfigView }>(`/channels/${encodeURIComponent(kind)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled, config }),
  });
  return body.channel;
}

export async function deleteChannel(kind: ChannelKind): Promise<boolean> {
  const body = await request<{ deleted: boolean }>(`/channels/${encodeURIComponent(kind)}`, { method: "DELETE" });
  return Boolean(body.deleted);
}

export async function createLinkCode(kind: ChannelKind, scope: ControlScope): Promise<ChannelLinkCode> {
  const body = await request<{ linkCode: ChannelLinkCode }>("/channels/link-code", {
    method: "POST",
    body: JSON.stringify({ kind, scope }),
  });
  return body.linkCode;
}

export async function listBindings(kind?: ChannelKind): Promise<ChannelBindingView[]> {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  const body = await request<{ bindings: ChannelBindingView[] }>(`/channels/bindings${q}`, { method: "GET" });
  return body.bindings ?? [];
}

export async function setBindingScope(bindingId: string, scope: ControlScope): Promise<void> {
  await request(`/channels/bindings/${encodeURIComponent(bindingId)}/scope`, {
    method: "POST",
    body: JSON.stringify({ scope }),
  });
}

export async function revokeBinding(bindingId: string): Promise<boolean> {
  const body = await request<{ revoked: boolean }>(`/channels/bindings/${encodeURIComponent(bindingId)}`, {
    method: "DELETE",
  });
  return Boolean(body.revoked);
}

export async function sendChannelMessage(
  kind: ChannelKind,
  chat: string,
  text: string,
): Promise<{ ok: boolean; reason?: string }> {
  return request<{ ok: boolean; reason?: string }>("/channels/send", {
    method: "POST",
    body: JSON.stringify({ kind, chat, text }),
  });
}

export async function listChannelMessages(
  opts: { kind?: ChannelKind; limit?: number } = {},
): Promise<ChannelMessageView[]> {
  const params = new URLSearchParams();
  if (opts.kind) params.set("kind", opts.kind);
  params.set("limit", String(opts.limit ?? 50));
  const body = await request<{ messages: ChannelMessageView[] }>(`/channels/messages?${params}`, { method: "GET" });
  return body.messages ?? [];
}

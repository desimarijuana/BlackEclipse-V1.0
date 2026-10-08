"use client";

// ── Event System front-door client ───────────────────────────────────────────
// The typed surface over the Event Console API (`/api/events/*`). Mirrors the
// jobs/automation clients: it ensures the Python runtime is healthy, injects the
// operator token, and never exposes a secret. Reads AND mutations are operator
// gated by the Python routes; this is the single place the UI talks to events.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type EventPriority = "low" | "normal" | "high" | "critical" | "bulk";

export interface EclipseEventView {
  id: string;
  type: string;
  version: number;
  timestamp: string;
  source: string;
  correlationId: string | null;
  causationId: string | null;
  traceId: string | null;
  actor: { type: string; id: string } | null;
  sessionId: string | null;
  taskId: string | null;
  workflowId: string | null;
  agentId: string | null;
  priority: EventPriority;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
  depth: number;
  replay: boolean;
  consumers?: ConsumerView[];
}

export interface ConsumerView {
  consumerId?: string;
  eventId?: string;
  status?: string;
  attempts?: number;
  lastAt?: string;
}

export interface EventTypeStat {
  type: string;
  count: number;
  lastAt: string | null;
}

export interface RegistrySpecView {
  type: string;
  version: number;
  namespace: boolean;
  description: string;
  producer: string[];
  consumers: string[];
  priority: string;
  retentionDays: number;
  sensitive: boolean;
}

export interface SubscriptionView {
  consumerId: string;
  patterns: string[];
  delivery: string;
  delivered: number;
  errors: number;
  queueDepth: number;
}

export interface DeclaredSubscriptionView {
  subscriberId: string;
  subscriberType: string;
  patterns: string[];
  predicate: string | null;
  enabled: boolean;
}

export interface DeadLetterView {
  id: string;
  eventId: string;
  consumerId: string;
  eventType: string | null;
  error: string | null;
  errorClass: string | null;
  attempts: number;
  status: string;
  createdAt: string;
}

export interface EventGraphView {
  nodes: Array<Record<string, unknown>>;
  edges: Array<{ from: string; to: string }>;
  root: string | null;
}

export interface ReplayOutcomeView {
  mode: string;
  count: number;
  eventIds: string[];
  matchedSubscribers: string[];
  delivered: number;
  skipped: number;
  dryRun: boolean;
}

export interface EventQuery {
  type?: string;
  namespace?: string;
  correlationId?: string;
  taskId?: string;
  workflowId?: string;
  agentId?: string;
  sessionId?: string;
  priority?: string;
  source?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

function toQuery(query: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
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
    const detail = (body as { detail?: string; error?: string }).detail
      || (body as { error?: string }).error
      || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(typeof detail === "string" ? detail : JSON.stringify(detail)));
  }
  return body as T;
}

export async function listEvents(query: EventQuery = {}): Promise<EclipseEventView[]> {
  const body = await request<{ events: EclipseEventView[] }>(`/events${toQuery({ ...query })}`, { method: "GET" });
  return body.events ?? [];
}

export async function getEvent(id: string): Promise<EclipseEventView> {
  const body = await request<{ event: EclipseEventView }>(`/events/${encodeURIComponent(id)}`, { method: "GET" });
  return body.event;
}

export async function listEventTypes(): Promise<EventTypeStat[]> {
  const body = await request<{ types: EventTypeStat[] }>("/events/types", { method: "GET" });
  return body.types ?? [];
}

export async function eventMetrics(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/events/metrics", { method: "GET" });
}

export async function eventHealth(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/events/health", { method: "GET" });
}

export async function eventRegistry(): Promise<RegistrySpecView[]> {
  const body = await request<{ events: RegistrySpecView[] }>("/events/registry", { method: "GET" });
  return body.events ?? [];
}

export async function listSubscriptions(): Promise<{ live: SubscriptionView[]; declared: DeclaredSubscriptionView[] }> {
  return request<{ live: SubscriptionView[]; declared: DeclaredSubscriptionView[] }>("/events/subscriptions", { method: "GET" });
}

export async function declareSubscription(input: {
  subscriberId: string;
  subscriberType?: string;
  patterns: string[];
  predicate?: string;
  enabled?: boolean;
}): Promise<DeclaredSubscriptionView> {
  const body = await request<{ subscription: DeclaredSubscriptionView }>("/events/subscriptions", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.subscription;
}

export async function deleteSubscription(subscriberId: string): Promise<boolean> {
  const body = await request<{ removed: number }>(`/events/subscriptions/${encodeURIComponent(subscriberId)}`, { method: "DELETE" });
  return (body.removed ?? 0) > 0;
}

export async function listDeadLetters(status?: string): Promise<DeadLetterView[]> {
  const body = await request<{ deadLetters: DeadLetterView[] }>(`/events/dlq${toQuery({ status })}`, { method: "GET" });
  return body.deadLetters ?? [];
}

export async function retryDeadLetter(id: string, confirmDestructive = false): Promise<ReplayOutcomeView> {
  const body = await request<{ replay: ReplayOutcomeView }>(
    `/events/dlq/${encodeURIComponent(id)}/retry${toQuery({ confirmDestructive: confirmDestructive ? "true" : undefined })}`,
    { method: "POST" },
  );
  return body.replay;
}

export async function discardDeadLetter(id: string): Promise<boolean> {
  const body = await request<{ status: string }>(`/events/dlq/${encodeURIComponent(id)}/discard`, { method: "POST" });
  return body.status === "discarded";
}

export async function replayEvents(input: {
  mode: "observe" | "simulation" | "full";
  correlationId?: string;
  taskId?: string;
  workflowId?: string;
  traceId?: string;
  eventId?: string;
  authorized?: boolean;
  confirmDestructive?: boolean;
  limit?: number;
}): Promise<ReplayOutcomeView> {
  const body = await request<{ replay: ReplayOutcomeView }>("/events/replay", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.replay;
}

export async function eventGraph(correlationId?: string, traceId?: string): Promise<EventGraphView> {
  return request<EventGraphView>(`/events/graph${toQuery({ correlationId, traceId })}`, { method: "GET" });
}

export async function listEventRules(): Promise<Array<Record<string, unknown>>> {
  const body = await request<{ rules: Array<Record<string, unknown>> }>("/events/rules", { method: "GET" });
  return body.rules ?? [];
}

export async function createEventRule(input: {
  name: string;
  eventType: string;
  action: string;
  condition?: string;
  agentId?: string;
  workflowId?: string;
  objective?: string;
  activated?: boolean;
}): Promise<Record<string, unknown>> {
  const body = await request<{ rule: Record<string, unknown> }>("/events/rules", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.rule;
}

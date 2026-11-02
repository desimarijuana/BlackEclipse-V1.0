// ── Webhook client ───────────────────────────────────────────────────────────
// Browser-side wrappers over the webhook routes. Like schedules, a webhook is
// user configuration in JDDS, not runtime state. The secret is returned only by
// create/rotate (shown once); it is never present on a list response.

export type WebhookMode = 'safe' | 'armed';
export type WebhookResponseMode = 'immediate' | 'wait';
export type WebhookVerificationMode = 'hmac' | 'token' | 'both';

export interface WorkflowWebhook {
  id: string;
  workflowId: string;
  nodeId: string | null;
  name: string;
  slug: string;
  endpoint: string;
  enabled: boolean;
  mode: WebhookMode;
  allowedMethods: string[];
  responseMode: WebhookResponseMode;
  responseTimeoutMs: number;
  verificationMode: WebhookVerificationMode;
  version: number | null;
  secretHint: string;
  lastReceivedAt: string | null;
  lastRunId: string | null;
  lastStatus: string | null;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Fired after any webhook mutation so the canvas can refresh node summaries. */
export const WEBHOOKS_CHANGED_EVENT = 'eclipse:webhooks-changed';

function notify(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(WEBHOOKS_CHANGED_EVENT));
}

export class WebhookApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'WebhookApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new WebhookApiError(
      (data as { error?: string }).error ?? `Request failed (${res.status})`,
      res.status,
    );
  }
  return data as T;
}

export async function listWebhooks(workflowId: string): Promise<WorkflowWebhook[]> {
  const data = await request<{ webhooks: WorkflowWebhook[] }>(`/api/workflows/${workflowId}/webhooks`);
  return data.webhooks ?? [];
}

export async function createWebhook(
  workflowId: string,
  input: { nodeId?: string | null; name?: string },
): Promise<{ webhook: WorkflowWebhook; secret: string }> {
  const data = await request<{ webhook: WorkflowWebhook; secret: string }>(
    `/api/workflows/${workflowId}/webhooks`,
    { method: 'POST', body: JSON.stringify(input) },
  );
  notify();
  return data;
}

export async function updateWebhook(
  id: string,
  patch: {
    nodeId?: string | null;
    name?: string;
    enabled?: boolean;
    mode?: WebhookMode;
    allowNetwork?: boolean;
    allowedMethods?: string[];
    responseMode?: WebhookResponseMode;
    responseTimeoutMs?: number;
    verificationMode?: WebhookVerificationMode;
  },
): Promise<WorkflowWebhook> {
  const data = await request<{ webhook: WorkflowWebhook }>(`/api/workflow-webhooks/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
  notify();
  return data.webhook;
}

export async function rotateWebhookSecret(id: string): Promise<{ webhook: WorkflowWebhook; secret: string }> {
  const data = await request<{ webhook: WorkflowWebhook; secret: string }>(
    `/api/workflow-webhooks/${id}/rotate`,
    { method: 'POST' },
  );
  notify();
  return data;
}

export async function deleteWebhook(id: string): Promise<void> {
  await request(`/api/workflow-webhooks/${id}`, { method: 'DELETE' });
  notify();
}

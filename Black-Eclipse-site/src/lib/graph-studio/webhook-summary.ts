// ── Webhook summary (client) ─────────────────────────────────────────────────
// The node card's read-only view of a WorkflowWebhook. The Webhook tab remains
// the editor.

export interface WebhookNodeSummary {
  id: string;
  enabled: boolean;
  mode: 'safe' | 'armed';
  version: number | null;
  endpoint: string;
  lastStatus: string | null;
  lastReceivedAt: string | null;
  lastError: string | null;
}

/** A short display form of the endpoint path (`/api/webhooks/…`). */
export function webhookPathLabel(endpoint: string): string {
  const text = endpoint || '';
  return text.length <= 30 ? text : `…${text.slice(-29)}`;
}

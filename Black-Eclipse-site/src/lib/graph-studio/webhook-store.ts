// ── Workflow webhooks — persistence, arm state, delivery receipts ────────────
// Server-only. A webhook is user configuration (JDDS), like a schedule:
//   * the node stays zero-config; this row owns endpoint/secret/mode;
//   * the secret is encrypted with the connector-secret store and shown once;
//   * `safe` runs the normal read-only TEST envelope;
//   * `armed` pins a workflow version + content hash + grants, and refuses a
//     delivery if the graph changed (no widening by request).
//
// The Python runtime never reads this table; the public route verifies and then
// calls `startPersistedRun`, which re-derives authority from the persisted IR.

import { prisma } from '@/lib/db';
import { decryptSecret, encryptSecret } from '@/lib/connectors/secrets';
import { contentHash } from './hash';
import { summarizeRunNeeds } from './run-authorization';
import { getWorkflow } from './server-store';
import {
  generateWebhookSecret,
  generateWebhookSlug,
  secretHint,
} from './webhook-crypto';

export type WebhookMode = 'safe' | 'armed';
export type WebhookResponseMode = 'immediate' | 'wait';
export type WebhookVerificationMode = 'hmac' | 'token' | 'both';

export interface WebhookRecord {
  id: string;
  workflowId: string;
  nodeId: string | null;
  name: string;
  slug: string;
  /** Relative endpoint the operator copies. Never contains the secret. */
  endpoint: string;
  enabled: boolean;
  mode: WebhookMode;
  allowedMethods: string[];
  responseMode: WebhookResponseMode;
  responseTimeoutMs: number;
  verificationMode: WebhookVerificationMode;
  version: number | null;
  /** Arm digest/grants (content hash + allowNetwork), or null in safe mode. */
  grantsJson: string | null;
  secretHint: string;
  lastReceivedAt: string | null;
  lastRunId: string | null;
  lastStatus: string | null;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

type Row = {
  id: string;
  workflowId: string;
  nodeId: string | null;
  name: string;
  slug: string;
  secretCipher: string;
  secretHint: string;
  enabled: boolean;
  mode: string;
  allowedMethods: string;
  responseMode: string;
  responseTimeoutMs: number;
  verificationMode: string;
  version: number | null;
  grantsJson: string | null;
  lastReceivedAt: Date | null;
  lastRunId: string | null;
  lastStatus: string | null;
  lastError: string | null;
  createdAt: Date;
  updatedAt: Date;
};

const METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

function parseMethods(raw: string): string[] {
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return ['POST'];
    const methods = value.map((item) => String(item).toUpperCase()).filter((item) => METHODS.has(item));
    return methods.length > 0 ? [...new Set(methods)] : ['POST'];
  } catch {
    return ['POST'];
  }
}

function asMode(value: string): WebhookMode {
  return value === 'armed' ? 'armed' : 'safe';
}

function asResponseMode(value: string): WebhookResponseMode {
  return value === 'wait' ? 'wait' : 'immediate';
}

function asVerificationMode(value: string): WebhookVerificationMode {
  return value === 'token' || value === 'both' ? value : 'hmac';
}

function toRecord(row: Row): WebhookRecord {
  return {
    id: row.id,
    workflowId: row.workflowId,
    nodeId: row.nodeId,
    name: row.name,
    slug: row.slug,
    endpoint: `/api/webhooks/${row.slug}`,
    enabled: row.enabled,
    mode: asMode(row.mode),
    allowedMethods: parseMethods(row.allowedMethods),
    responseMode: asResponseMode(row.responseMode),
    responseTimeoutMs: row.responseTimeoutMs,
    verificationMode: asVerificationMode(row.verificationMode),
    version: row.version,
    grantsJson: row.grantsJson,
    secretHint: row.secretHint,
    lastReceivedAt: row.lastReceivedAt?.toISOString() ?? null,
    lastRunId: row.lastRunId,
    lastStatus: row.lastStatus,
    lastError: row.lastError,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

function internal(row: Row): Row {
  return row;
}

export async function listWebhooks(workflowId: string): Promise<WebhookRecord[]> {
  const rows = await prisma.workflowWebhook.findMany({
    where: { workflowId },
    orderBy: { createdAt: 'asc' },
    take: 100,
  });
  return rows.map((row) => toRecord(row as Row));
}

export async function getWebhook(id: string): Promise<WebhookRecord | null> {
  const row = await prisma.workflowWebhook.findUnique({ where: { id } });
  return row ? toRecord(row as Row) : null;
}

/** Internal lookup for the public route: needs the cipher, never returned to a client. */
export async function getWebhookForDelivery(
  slug: string,
): Promise<{ record: WebhookRecord; row: Row } | null> {
  const row = await prisma.workflowWebhook.findUnique({ where: { slug } });
  if (!row) return null;
  return { record: toRecord(row as Row), row: internal(row as Row) };
}

export function readWebhookSecret(row: Row): string {
  return decryptSecret(row.secretCipher);
}

async function uniqueSlug(): Promise<string> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const slug = generateWebhookSlug();
    const existing = await prisma.workflowWebhook.findUnique({ where: { slug }, select: { id: true } });
    if (!existing) return slug;
  }
  throw new Error('Could not allocate a unique webhook URL');
}

export async function createWebhook(input: {
  workflowId: string;
  nodeId?: string | null;
  name?: string;
}): Promise<{ webhook: WebhookRecord; secret: string }> {
  const secret = generateWebhookSecret();
  const row = await prisma.workflowWebhook.create({
    data: {
      workflowId: input.workflowId,
      nodeId: input.nodeId?.trim() || null,
      name: input.name?.trim() || 'Webhook',
      slug: await uniqueSlug(),
      secretCipher: encryptSecret(secret),
      secretHint: secretHint(secret),
      allowedMethods: JSON.stringify(['POST']),
    },
  });
  return { webhook: toRecord(row as Row), secret };
}

export async function rotateWebhookSecret(id: string): Promise<{ webhook: WebhookRecord; secret: string } | null> {
  const existing = await prisma.workflowWebhook.findUnique({ where: { id } });
  if (!existing) return null;
  const secret = generateWebhookSecret();
  const row = await prisma.workflowWebhook.update({
    where: { id },
    data: { secretCipher: encryptSecret(secret), secretHint: secretHint(secret) },
  });
  return { webhook: toRecord(row as Row), secret };
}

function normalizeMethods(values: unknown): string[] {
  if (!Array.isArray(values)) return ['POST'];
  const methods = values
    .map((value) => String(value).toUpperCase())
    .filter((value) => METHODS.has(value));
  return methods.length > 0 ? [...new Set(methods)] : ['POST'];
}

/**
 * Arm the webhook against the CURRENT saved version.
 *
 * Only read/compute/network graphs can be armed. Writes and trading are refused
 * because an unattended caller must not obtain those effects from a webhook.
 */
export async function armWebhook(
  id: string,
  input: { allowNetwork?: boolean } = {},
): Promise<WebhookRecord> {
  const row = await prisma.workflowWebhook.findUnique({ where: { id } });
  if (!row) throw new Error('Webhook not found');

  const workflow = await getWorkflow(row.workflowId);
  if (!workflow) throw new Error('Workflow not found');

  const hasTrigger = workflow.ir.nodes.some(
    (node) => node.type === 'trigger.webhook' && (!row.nodeId || node.id === row.nodeId),
  );
  if (!hasTrigger) throw new Error('This webhook is not linked to a trigger.webhook node in the workflow.');

  const summary = summarizeRunNeeds(workflow.ir);
  if (summary.unknownNodes.length > 0) {
    throw new Error(`Unknown node type(s): ${summary.unknownNodes.join(', ')}`);
  }
  if (summary.writeNodes.length > 0 || summary.tradingNodes.length > 0 || summary.modelNodes.length > 0) {
    throw new Error('An armed webhook supports read/compute/network only; remove write, trading and agent/model nodes to arm it.');
  }
  if (summary.requiresNetwork && !input.allowNetwork) {
    throw new Error(`This workflow needs network access (${summary.networkNodes.join(', ')}); confirm it to arm the webhook.`);
  }

  const grants = {
    contentHash: contentHash(workflow.ir),
    allowNetwork: summary.requiresNetwork,
    requiredCapabilities: summary.requiredCapabilities,
  };
  const updated = await prisma.workflowWebhook.update({
    where: { id },
    data: {
      mode: 'armed',
      version: workflow.version,
      grantsJson: JSON.stringify(grants),
    },
  });
  return toRecord(updated as Row);
}

export type ArmedCheck =
  | { ok: true; version: number | null; authorization?: { operator: true; allowNetwork: boolean } }
  | { ok: false; error: string };

/** Re-validate the pinned version + digest before every delivery. */
export async function verifyArmed(record: WebhookRecord): Promise<ArmedCheck> {
  if (record.mode !== 'armed') {
    // Safe mode still runs the CURRENT version, so refuse if its trigger node
    // was deleted: an endpoint must not outlive the graph it belongs to.
    const current = await getWorkflow(record.workflowId);
    if (!current) return { ok: false, error: 'the workflow no longer exists' };
    const linked = current.ir.nodes.some(
      (node) => node.type === 'trigger.webhook' && (!record.nodeId || node.id === record.nodeId),
    );
    if (!linked) return { ok: false, error: 'the trigger.webhook node is no longer in the workflow' };
    return { ok: true, version: null };
  }
  if (!record.version || !record.grantsJson) return { ok: false, error: 'webhook is not armed' };

  let grants: { contentHash?: string; allowNetwork?: boolean };
  try {
    grants = JSON.parse(record.grantsJson) as { contentHash?: string; allowNetwork?: boolean };
  } catch {
    return { ok: false, error: 'arm record is unreadable; re-arm the webhook' };
  }

  const workflow = await getWorkflow(record.workflowId, record.version);
  if (!workflow) return { ok: false, error: 'the pinned workflow version no longer exists' };
  if (grants.contentHash && contentHash(workflow.ir) !== grants.contentHash) {
    return { ok: false, error: 'the pinned workflow version changed; re-arm the webhook' };
  }
  const hasTrigger = workflow.ir.nodes.some(
    (node) => node.type === 'trigger.webhook' && (!record.nodeId || node.id === record.nodeId),
  );
  if (!hasTrigger) return { ok: false, error: 'the trigger.webhook node is no longer in the pinned version' };
  const summary = summarizeRunNeeds(workflow.ir);
  if (summary.writeNodes.length > 0 || summary.tradingNodes.length > 0 || summary.modelNodes.length > 0) {
    return { ok: false, error: 'the pinned version now contains write/trading/model nodes; re-arm refused' };
  }
  if (summary.requiresNetwork && !grants.allowNetwork) {
    return { ok: false, error: 'the pinned version needs network, which was not granted when armed' };
  }
  return {
    ok: true,
    version: record.version,
    authorization: { operator: true, allowNetwork: Boolean(grants.allowNetwork) },
  };
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
): Promise<WebhookRecord | null> {
  const existing = await prisma.workflowWebhook.findUnique({ where: { id } });
  if (!existing) return null;

  if (patch.mode === 'armed') {
    return armWebhook(id, { allowNetwork: patch.allowNetwork });
  }

  const row = await prisma.workflowWebhook.update({
    where: { id },
    data: {
      nodeId: patch.nodeId === undefined ? existing.nodeId : patch.nodeId,
      name: patch.name?.trim() || existing.name,
      enabled: patch.enabled ?? existing.enabled,
      ...(patch.mode === 'safe'
        ? { mode: 'safe', version: null, grantsJson: null }
        : {}),
      ...(patch.allowedMethods ? { allowedMethods: JSON.stringify(normalizeMethods(patch.allowedMethods)) } : {}),
      ...(patch.responseMode ? { responseMode: asResponseMode(patch.responseMode) } : {}),
      ...(patch.responseTimeoutMs !== undefined
        ? { responseTimeoutMs: Math.max(1_000, Math.min(30_000, Math.round(patch.responseTimeoutMs))) }
        : {}),
      ...(patch.verificationMode ? { verificationMode: asVerificationMode(patch.verificationMode) } : {}),
    },
  });
  return toRecord(row as Row);
}

export async function deleteWebhook(id: string): Promise<boolean> {
  try {
    await prisma.workflowWebhook.delete({ where: { id } });
    return true;
  } catch {
    return false;
  }
}

/** Insert a receipt. A duplicate delivery returns the prior run instead. */
export async function claimDelivery(
  webhookId: string,
  deliveryId: string,
  ttlMs = 10 * 60 * 1000,
): Promise<{ duplicate: false } | { duplicate: true; runId: string | null }> {
  const now = new Date();
  await prisma.workflowWebhookReceipt.deleteMany({ where: { expiresAt: { lt: now } } }).catch(() => {});
  try {
    await prisma.workflowWebhookReceipt.create({
      data: { webhookId, deliveryId, expiresAt: new Date(now.getTime() + ttlMs) },
    });
    return { duplicate: false };
  } catch (err) {
    if ((err as { code?: string }).code === 'P2002') {
      const row = await prisma.workflowWebhookReceipt.findUnique({
        where: { webhookId_deliveryId: { webhookId, deliveryId } },
        select: { runId: true },
      });
      return { duplicate: true, runId: row?.runId ?? null };
    }
    throw err;
  }
}

export async function setDeliveryRun(webhookId: string, deliveryId: string, runId: string): Promise<void> {
  await prisma.workflowWebhookReceipt.updateMany({
    where: { webhookId, deliveryId },
    data: { runId },
  });
}

export async function recordDelivery(
  id: string,
  outcome: { runId?: string | null; status?: string | null; error?: string | null },
): Promise<void> {
  await prisma.workflowWebhook.update({
    where: { id },
    data: {
      lastReceivedAt: new Date(),
      lastRunId: outcome.runId ?? null,
      lastStatus: outcome.status ?? null,
      lastError: outcome.error ? outcome.error.slice(0, 500) : null,
    },
  }).catch(() => {});
}

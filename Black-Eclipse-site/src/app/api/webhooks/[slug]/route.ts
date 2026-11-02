// ── Public inbound webhook ───────────────────────────────────────────────────
// `POST|GET /api/webhooks/[slug]`. This is deliberately NOT operator-gated: the
// caller is a third party and cannot present a session cookie. Authenticity is
// proven by an HMAC over the RAW body + timestamp (or a token header), exactly
// like the channel gateway. The slug identifies the endpoint; it is NOT a
// secret. The middleware exempts this prefix from the session gate.
//
// A delivery can start either:
//   * a safe run (the normal read-only TEST envelope), or
//   * an armed run against a pinned workflow version whose grants the operator
//     confirmed. verifyArmed() refuses if the graph/hash changed.
// A delivery never carries authority of its own.

import { NextResponse } from 'next/server';
import { HARNESS_PY_URL } from '@/lib/harness/python-runtime';
import { runtimeCallbackToken } from '@/lib/harness/runtime-auth';
import { clientKey, rateLimit } from '@/lib/api-guard';
import { startPersistedRun } from '@/lib/graph-studio/run-server';
import { MAX_RUN_INPUT_BYTES, validateRunInput } from '@/lib/graph-studio/run-input';
import {
  recordDelivery,
  claimDelivery,
  getWebhookForDelivery,
  readWebhookSecret,
  setDeliveryRun,
  verifyArmed,
} from '@/lib/graph-studio/webhook-store';
import {
  DELIVERY_HEADER,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
  TOKEN_HEADER,
  verifyWebhookSignature,
  verifyWebhookToken,
} from '@/lib/graph-studio/webhook-crypto';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ slug: string }> };

const SKIP_HEADERS = new Set([
  'authorization', 'cookie', 'set-cookie', 'host', 'content-length',
  'connection', 'transfer-encoding', 'x-eclipse-token', 'x-eclipse-signature',
  'x-api-key',
]);

function safeHeaders(request: Request): Record<string, string> {
  const out: Record<string, string> = {};
  let count = 0;
  for (const [name, value] of request.headers.entries()) {
    const key = name.toLowerCase();
    if (SKIP_HEADERS.has(key) || value.length > 2_000) continue;
    out[key] = value;
    count += 1;
    if (count >= 30) break;
  }
  return out;
}

function queryObject(request: Request): Record<string, string> {
  const url = new URL(request.url);
  const out: Record<string, string> = {};
  url.searchParams.forEach((value, key) => {
    if (!(key in out)) out[key] = value;
  });
  return out;
}

function terminalRun(run: unknown): boolean {
  const status = (run as { status?: unknown } | null)?.status;
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}

async function waitForRun(runId: string, timeoutMs: number): Promise<Record<string, unknown> | null> {
  const token = runtimeCallbackToken();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${HARNESS_PY_URL}/graphs/runs/${encodeURIComponent(runId)}`, {
        headers: token ? { 'X-Harness-Operator': token } : {},
        cache: 'no-store',
        signal: AbortSignal.timeout(5_000),
      });
      if (res.ok) {
        const data = (await res.json().catch(() => ({}))) as { run?: Record<string, unknown> };
        const run = data.run;
        if (run && terminalRun(run)) return run;
      }
    } catch {
      // Keep polling until the deadline; a transient runtime hiccup is not a 500.
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return null;
}

async function handle(request: Request, ctx: Ctx): Promise<Response> {
  const { slug } = await ctx.params;

  // Per-endpoint rate limit before any database or HMAC work.
  const limited = rateLimit(`webhook:${slug}:${clientKey(request)}`, { limit: 120, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json({ error: 'Too many requests' }, {
      status: 429,
      headers: { 'Retry-After': String(limited.retryAfterSec) },
    });
  }

  const found = await getWebhookForDelivery(slug);
  if (!found || !found.record.enabled) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }
  const { record, row } = found;
  const method = request.method.toUpperCase();
  if (!record.allowedMethods.includes(method)) {
    return NextResponse.json({ error: 'Method not allowed' }, { status: 405 });
  }

  const declaredLength = Number(request.headers.get('content-length') ?? '0');
  if (Number.isFinite(declaredLength) && declaredLength > MAX_RUN_INPUT_BYTES) {
    return NextResponse.json({ error: 'Payload too large' }, { status: 413 });
  }
  // Read the RAW bytes: the signature is over exactly what the sender sent.
  const raw = await request.text().catch(() => '');
  if (new TextEncoder().encode(raw).length > MAX_RUN_INPUT_BYTES) {
    return NextResponse.json({ error: 'Payload too large' }, { status: 413 });
  }

  let secret: string;
  try {
    secret = readWebhookSecret(row);
  } catch {
    console.error(`[api/webhooks] could not decrypt the secret for ${record.id}`);
    return NextResponse.json({ error: 'Webhook unavailable' }, { status: 503 });
  }

  const signature = request.headers.get(SIGNATURE_HEADER);
  const timestamp = request.headers.get(TIMESTAMP_HEADER);
  const token = request.headers.get(TOKEN_HEADER);
  let verified = false;
  let proofError: string | null = null;

  if (record.verificationMode === 'hmac' || record.verificationMode === 'both') {
    proofError = verifyWebhookSignature({ secret, signature, timestamp, body: raw });
    verified = proofError === null;
  }
  if (!verified && (record.verificationMode === 'token' || record.verificationMode === 'both')) {
    proofError = verifyWebhookToken(secret, token);
    verified = proofError === null;
  }
  if (!verified) {
    // Deliberately terse: the endpoint must not help an attacker distinguish
    // "wrong secret" from "unknown endpoint".
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const url = new URL(request.url);
  const challenge = url.searchParams.get('challenge') ?? url.searchParams.get('hub.challenge');
  if (method === 'GET' && challenge) {
    return NextResponse.json({ challenge });
  }

  const explicitDelivery = request.headers.get(DELIVERY_HEADER)?.trim() || '';
  if (explicitDelivery) {
    const claim = await claimDelivery(record.id, explicitDelivery);
    if (claim.duplicate) {
      return NextResponse.json(
        { duplicate: true, runId: claim.runId, accepted: Boolean(claim.runId) },
        { status: 200 },
      );
    }
  }

  const armed = await verifyArmed(record);
  if (!armed.ok) {
    await recordDelivery(record.id, { status: 'refused', error: armed.error });
    return NextResponse.json({ error: armed.error }, { status: 409 });
  }

  let runInput: unknown;
  if (raw.trim()) {
    try {
      runInput = JSON.parse(raw);
    } catch {
      runInput = { text: raw };
    }
  }
  const input = validateRunInput(runInput);
  if (!input.ok) {
    await recordDelivery(record.id, { status: 'refused', error: input.error });
    return NextResponse.json({ error: input.error }, { status: 400 });
  }

  const triggerContext = {
    body: input.value,
    headers: safeHeaders(request),
    query: queryObject(request),
    method,
    receivedAt: new Date().toISOString(),
    webhookId: record.id,
    deliveryId: explicitDelivery,
    signatureVerified: true,
  };

  const result = await startPersistedRun({
    workflowId: record.workflowId,
    version: armed.version ?? undefined,
    runInput: input.value,
    triggerContext,
    // Safe mode omits `authorization` entirely: startPersistedRun defaults to a
    // test run. Armed mode passes only the pinned, operator-confirmed grant.
    authorization: armed.authorization,
    // Do NOT forward the inbound request: an external caller's identity headers
    // must never become the run owner.
  });

  if (!result.ok) {
    await recordDelivery(record.id, { status: 'failed', error: result.error });
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  const runId = (result.run as { id?: string } | undefined)?.id ?? '';
  if (explicitDelivery) await setDeliveryRun(record.id, explicitDelivery, runId);
  await recordDelivery(record.id, { runId, status: 'started' });

  if (record.responseMode === 'wait' && runId) {
    const run = await waitForRun(runId, record.responseTimeoutMs);
    if (run) {
      const status = String(run.status);
      await recordDelivery(record.id, { runId, status });
      return NextResponse.json({
        ok: status === 'succeeded',
        runId,
        status,
        output: run.output ?? null,
      });
    }
  }

  return NextResponse.json({ accepted: true, runId }, { status: 202 });
}

export async function GET(request: Request, ctx: Ctx) {
  return handle(request, ctx);
}

export async function POST(request: Request, ctx: Ctx) {
  return handle(request, ctx);
}

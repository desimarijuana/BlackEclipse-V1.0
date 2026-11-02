// ── /api/workflow-webhooks/[wid] — update settings / arm / delete ────────────

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { deleteWebhook, updateWebhook } from '@/lib/graph-studio/webhook-store';
import type {
  WebhookMode,
  WebhookResponseMode,
  WebhookVerificationMode,
} from '@/lib/graph-studio/webhook-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ wid: string }> };

export async function PATCH(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-webhook-update');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { wid } = await ctx.params;
  try {
    const body = (await request.json().catch(() => ({}))) as {
      nodeId?: string | null;
      name?: string;
      enabled?: boolean;
      mode?: WebhookMode;
      allowNetwork?: boolean;
      allowedMethods?: string[];
      responseMode?: WebhookResponseMode;
      responseTimeoutMs?: number;
      verificationMode?: WebhookVerificationMode;
    };
    const webhook = await updateWebhook(wid, {
      nodeId: body.nodeId,
      name: body.name,
      enabled: body.enabled,
      mode: body.mode,
      allowNetwork: Boolean(body.allowNetwork),
      allowedMethods: body.allowedMethods,
      responseMode: body.responseMode,
      responseTimeoutMs: body.responseTimeoutMs,
      verificationMode: body.verificationMode,
    });
    if (!webhook) return NextResponse.json({ error: 'Webhook not found' }, { status: 404 });
    return NextResponse.json({ webhook });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to update webhook' },
      { status: 400 },
    );
  }
}

export async function DELETE(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-webhook-delete');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { wid } = await ctx.params;
  const ok = await deleteWebhook(wid);
  if (!ok) return NextResponse.json({ error: 'Webhook not found' }, { status: 404 });
  return NextResponse.json({ success: true });
}

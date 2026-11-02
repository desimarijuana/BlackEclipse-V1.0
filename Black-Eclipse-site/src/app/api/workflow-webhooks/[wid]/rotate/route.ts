// ── /api/workflow-webhooks/[wid]/rotate — replace the signing secret ─────────
// The new secret is returned once; the old one stops verifying immediately.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { rotateWebhookSecret } from '@/lib/graph-studio/webhook-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ wid: string }> };

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-webhook-rotate');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { wid } = await ctx.params;
  const rotated = await rotateWebhookSecret(wid);
  if (!rotated) return NextResponse.json({ error: 'Webhook not found' }, { status: 404 });
  return NextResponse.json(rotated);
}

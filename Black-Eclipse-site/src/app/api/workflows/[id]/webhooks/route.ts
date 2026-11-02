// ── /api/workflows/[id]/webhooks — list + create inbound endpoints ──────────
// A webhook is user configuration (JDDS), linked to a trigger.webhook node. The
// secret is returned exactly once on create/rotate; list never includes it.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { createWebhook, listWebhooks } from '@/lib/graph-studio/webhook-store';
import { getWorkflow } from '@/lib/graph-studio/server-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_request: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json({ webhooks: await listWebhooks(id) });
  } catch (err) {
    console.error('[api/workflows/:id/webhooks] GET error:', err);
    return NextResponse.json({ error: 'Failed to list webhooks' }, { status: 500 });
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-webhook-create');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  try {
    const body = (await request.json().catch(() => ({}))) as {
      nodeId?: string | null;
      name?: string;
    };
    const workflow = await getWorkflow(id);
    if (!workflow) return NextResponse.json({ error: 'Workflow not found' }, { status: 404 });
    const nodeId = typeof body.nodeId === 'string' && body.nodeId.trim() ? body.nodeId.trim() : null;
    if (nodeId) {
      // A node added since the last save is allowed: the link is harmless and
      // the arm step refuses until the node exists in the pinned version.
      const node = workflow.ir.nodes.find((item) => item.id === nodeId);
      if (node && node.type !== 'trigger.webhook') {
        return NextResponse.json({ error: 'nodeId must identify a trigger.webhook node' }, { status: 400 });
      }
    }
    const created = await createWebhook({
      workflowId: id,
      nodeId,
      name: body.name,
    });
    // `secret` is the ONLY time the plaintext is returned.
    return NextResponse.json(created, { status: 201 });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to create webhook' },
      { status: 400 },
    );
  }
}

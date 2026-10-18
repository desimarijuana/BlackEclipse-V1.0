// ── /api/workflows — list + create Graph Studio workflow documents ──────────
// Backed by the JDDS Prisma store (`lib/graph-studio/server-store`). The client
// IR is re-validated server-side before a row is written.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { createWorkflow, listWorkflows } from '@/lib/graph-studio/server-store';
import { readWorkflowIR } from '@/lib/graph-studio/migrations';
import { createWorkflowIR } from '@/lib/graph-studio/ir';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const workflows = await listWorkflows();
    return NextResponse.json({ workflows });
  } catch (err) {
    console.error('[api/workflows] GET error:', err);
    return NextResponse.json({ error: 'Failed to list workflows' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, 'workflows-create');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as {
      name?: string;
      description?: string;
      tags?: string[];
      ir?: unknown;
    };
    if (!body.name || typeof body.name !== 'string') {
      return NextResponse.json({ error: 'name is required' }, { status: 400 });
    }
    // Accept a supplied IR (validated) or start from a fresh empty document.
    const ir = body.ir ? readWorkflowIR(body.ir) : createWorkflowIR({ name: body.name, description: body.description ?? '' });
    const workflow = await createWorkflow({
      name: body.name,
      description: body.description ?? '',
      tags: body.tags ?? [],
      ir,
    });
    return NextResponse.json({ workflow }, { status: 201 });
  } catch (err) {
    console.error('[api/workflows] POST error:', err);
    return NextResponse.json({ error: err instanceof Error ? err.message : 'Failed to create workflow' }, { status: 400 });
  }
}

// ── /api/workflows/[id] — read / save (append version) / delete ──────────────
// GET    ?version=N  → a specific (or the current) version's IR.
// PATCH              → save the supplied IR as the NEXT version (append-only).
// DELETE             → remove the workflow and (cascaded) its versions.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { deleteWorkflow, getWorkflow, saveWorkflow } from '@/lib/graph-studio/server-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ id: string }> };

export async function GET(request: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const { searchParams } = new URL(request.url);
  const rawVersion = searchParams.get('version');
  const version = rawVersion ? Number.parseInt(rawVersion, 10) : undefined;
  try {
    const workflow = await getWorkflow(id, Number.isFinite(version) ? version : undefined);
    if (!workflow) return NextResponse.json({ error: 'Workflow not found' }, { status: 404 });
    return NextResponse.json({ workflow });
  } catch (err) {
    console.error('[api/workflows/:id] GET error:', err);
    return NextResponse.json({ error: err instanceof Error ? err.message : 'Failed to load workflow' }, { status: 500 });
  }
}

export async function PATCH(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflows-save');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  try {
    const body = (await request.json().catch(() => ({}))) as { ir?: unknown; note?: string };
    if (!body.ir) return NextResponse.json({ error: 'ir is required' }, { status: 400 });
    const workflow = await saveWorkflow(id, body.ir, body.note);
    return NextResponse.json({ workflow });
  } catch (err) {
    console.error('[api/workflows/:id] PATCH error:', err);
    return NextResponse.json({ error: err instanceof Error ? err.message : 'Failed to save workflow' }, { status: 400 });
  }
}

export async function DELETE(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflows-delete');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  const ok = await deleteWorkflow(id);
  if (!ok) return NextResponse.json({ error: 'Workflow not found' }, { status: 404 });
  return NextResponse.json({ success: true });
}

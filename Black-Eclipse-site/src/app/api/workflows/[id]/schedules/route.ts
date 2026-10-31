// ── /api/workflows/[id]/schedules — list + create unattended schedules ───────

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { createSchedule, listSchedules } from '@/lib/graph-studio/schedule-store';
import { getWorkflow } from '@/lib/graph-studio/server-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_request: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json({ schedules: await listSchedules(id) });
  } catch (err) {
    console.error('[api/workflows/:id/schedules] GET error:', err);
    return NextResponse.json({ error: 'Failed to list schedules' }, { status: 500 });
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-schedule-create');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  try {
    const body = (await request.json().catch(() => ({}))) as {
      nodeId?: string | null;
      name?: string;
      cron?: string;
      timezone?: string;
      catchUp?: 'skip' | 'coalesce';
      version?: number | null;
      enabled?: boolean;
    };
    if (!body.name || !body.cron) {
      return NextResponse.json({ error: 'name and cron are required' }, { status: 400 });
    }
    const workflow = await getWorkflow(id);
    if (!workflow) return NextResponse.json({ error: 'Workflow not found' }, { status: 404 });
    const schedule = await createSchedule({
      workflowId: id,
      nodeId: typeof body.nodeId === 'string' && body.nodeId.trim() ? body.nodeId.trim() : null,
      name: body.name,
      cron: body.cron,
      timezone: body.timezone,
      catchUp: body.catchUp,
      version: body.version ?? null,
      enabled: body.enabled,
    });
    return NextResponse.json({ schedule }, { status: 201 });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to create schedule' },
      { status: 400 },
    );
  }
}

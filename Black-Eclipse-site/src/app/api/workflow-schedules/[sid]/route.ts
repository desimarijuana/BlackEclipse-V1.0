// ── /api/workflow-schedules/[sid] — update (enable/pause/edit) or delete ─────

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { deleteSchedule, updateSchedule } from '@/lib/graph-studio/schedule-store';
import type { ScheduleRecord } from '@/lib/graph-studio/schedule-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ sid: string }> };

export async function PATCH(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-schedule-update');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { sid } = await ctx.params;
  try {
    const body = (await request.json().catch(() => ({}))) as Partial<ScheduleRecord>;
    const schedule = await updateSchedule(sid, {
      nodeId: typeof body.nodeId === 'string' && body.nodeId.trim() ? body.nodeId.trim() : undefined,
      name: body.name,
      cron: body.cron,
      timezone: body.timezone,
      enabled: body.enabled,
      catchUp: body.catchUp,
      version: body.version,
    });
    if (!schedule) return NextResponse.json({ error: 'Schedule not found' }, { status: 404 });
    return NextResponse.json({ schedule });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to update schedule' },
      { status: 400 },
    );
  }
}

export async function DELETE(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'workflow-schedule-delete');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { sid } = await ctx.params;
  const ok = await deleteSchedule(sid);
  if (!ok) return NextResponse.json({ error: 'Schedule not found' }, { status: 404 });
  return NextResponse.json({ success: true });
}

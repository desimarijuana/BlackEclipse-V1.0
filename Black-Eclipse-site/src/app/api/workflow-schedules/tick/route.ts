// ── /api/workflow-schedules/tick — fire every due schedule now ───────────────
// The boot timer calls `runDueSchedules` directly; this route exists so an
// operator (or an external cron) can drive the tick explicitly, and so the
// behaviour is testable over HTTP.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { runDueSchedules } from '@/lib/graph-studio/schedule-tick';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const blocked = guardMutation(request, 'workflow-schedule-tick');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const outcomes = await runDueSchedules();
    return NextResponse.json({ outcomes });
  } catch (err) {
    console.error('[api/workflow-schedules/tick] error:', err);
    return NextResponse.json({ error: 'Tick failed' }, { status: 500 });
  }
}

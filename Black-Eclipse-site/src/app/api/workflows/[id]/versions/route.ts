// ── /api/workflows/[id]/versions — immutable version history ─────────────────

import { NextResponse } from 'next/server';
import { listVersions } from '@/lib/graph-studio/server-store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_request: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const versions = await listVersions(id);
    return NextResponse.json({ versions });
  } catch (err) {
    console.error('[api/workflows/:id/versions] GET error:', err);
    return NextResponse.json({ error: 'Failed to list versions' }, { status: 500 });
  }
}

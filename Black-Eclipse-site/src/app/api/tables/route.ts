// ── /api/tables — list and create user data tables ──────────────────────────
// Spreadsheet-style tables owned by the operator. Separate from connector-fed
// datasets (/api/datasets) and from the canonical market tables.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { createDataTable, listDataTables } from '@/lib/tables/store';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json({ tables: await listDataTables() });
  } catch (err) {
    console.error('[api/tables] GET error:', err);
    return NextResponse.json({ error: 'Failed to load tables' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, 'tables-create');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as {
      name?: unknown;
      description?: unknown;
      columns?: unknown;
    };
    const table = await createDataTable({
      name: body.name,
      description: body.description,
      columns: body.columns,
    });
    return NextResponse.json({ table }, { status: 201 });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to create table' },
      { status: 400 },
    );
  }
}

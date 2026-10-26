// ── /api/tables/[id] — read, edit and delete a user data table ───────────────
// POST uses an explicit `action` so one route owns the small set of spreadsheet
// mutations (metadata, columns, rows) without a route per cell.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import {
  addDataTableRow, deleteDataTable, deleteDataTableRow, getDataTable,
  updateDataTableColumns, updateDataTableMeta, updateDataTableRow,
} from '@/lib/tables/store';

export const dynamic = 'force-dynamic';

type Ctx = { params: Promise<{ id: string }> };

function errorResponse(err: unknown, fallback: string) {
  const message = err instanceof Error ? err.message : fallback;
  const status = /not found/i.test(message) ? 404 : 400;
  return NextResponse.json({ error: message }, { status });
}

export async function GET(_request: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const table = await getDataTable(id);
    if (!table) return NextResponse.json({ error: 'Table not found' }, { status: 404 });
    return NextResponse.json({ table });
  } catch (err) {
    console.error('[api/tables/:id] GET error:', err);
    return NextResponse.json({ error: 'Failed to load table' }, { status: 500 });
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'tables-update');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  try {
    const body = (await request.json().catch(() => ({}))) as {
      action?: unknown;
      name?: unknown;
      description?: unknown;
      columns?: unknown;
      rowId?: unknown;
      values?: unknown;
    };
    const action = typeof body.action === 'string' ? body.action : '';

    if (action === 'update_meta') {
      return NextResponse.json({ table: await updateDataTableMeta(id, { name: body.name, description: body.description }) });
    }
    if (action === 'update_columns') {
      return NextResponse.json({ table: await updateDataTableColumns(id, body.columns) });
    }

    const current = await getDataTable(id);
    if (!current) return NextResponse.json({ error: 'Table not found' }, { status: 404 });
    const columns = current.table.columns;

    if (action === 'add_row') {
      return NextResponse.json({ table: await addDataTableRow(id, body.values, columns) });
    }
    if (action === 'update_row') {
      if (typeof body.rowId !== 'string') return NextResponse.json({ error: 'rowId is required' }, { status: 400 });
      return NextResponse.json({ table: await updateDataTableRow(id, body.rowId, body.values, columns) });
    }
    if (action === 'delete_row') {
      if (typeof body.rowId !== 'string') return NextResponse.json({ error: 'rowId is required' }, { status: 400 });
      return NextResponse.json({ table: await deleteDataTableRow(id, body.rowId) });
    }
    return NextResponse.json({ error: `Unknown action "${action}"` }, { status: 400 });
  } catch (err) {
    return errorResponse(err, 'Failed to update table');
  }
}

export async function DELETE(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, 'tables-delete');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  try {
    await deleteDataTable(id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return errorResponse(err, 'Failed to delete table');
  }
}

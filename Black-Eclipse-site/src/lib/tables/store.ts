// ── User data tables — server store ──────────────────────────────────────────
// The ONE place DataTable / DataTableRow rows are read and written. Columns and
// cell values are JSON strings (Prisma + SQLite has no Json column in this
// project). These tables are operator-authored scratch data: they are NOT the
// canonical market tables and they are NOT connector-fed CustomDatasets.

import { prisma } from '@/lib/db';
import {
  TABLE_COLUMN_TYPES, isTableColumnType,
  type DataTableDetail, type DataTableRowRecord, type DataTableSummary,
  type TableColumn, type TableColumnType,
} from './types';

const MAX_NAME = 120;
const MAX_COLUMNS = 60;
const MAX_CELL_JSON_BYTES = 1_000_000;

interface RawTableRow {
  id: string;
  values: string;
  position: number;
  createdAt: Date;
  updatedAt: Date;
}

interface RawTable {
  id: string;
  name: string;
  description: string | null;
  columns: string;
  createdAt: Date;
  updatedAt: Date;
}

function parseJson<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function columnId(used: Set<string> = new Set()): string {
  for (;;) {
    const id = `col_${Math.random().toString(36).slice(2, 10)}`;
    if (!used.has(id)) {
      used.add(id);
      return id;
    }
  }
}

export function parseColumns(raw: string): TableColumn[] {
  const parsed = parseJson<unknown>(raw, []);
  if (!Array.isArray(parsed)) return [];
  const used = new Set<string>();
  const columns: TableColumn[] = [];
  for (const item of parsed) {
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const name = typeof record.name === 'string' ? record.name.trim() : '';
    if (!name) continue;
    let id = typeof record.id === 'string' && record.id ? record.id : columnId(used);
    if (used.has(id)) id = columnId(used);
    used.add(id);
    const type = isTableColumnType(record.type) ? record.type : 'string';
    columns.push({ id, name: name.slice(0, MAX_NAME), type });
    if (columns.length >= MAX_COLUMNS) break;
  }
  return columns;
}

function normaliseColumns(input: unknown): TableColumn[] {
  if (!Array.isArray(input)) throw new Error('columns must be an array');
  const used = new Set<string>();
  const columns: TableColumn[] = [];
  for (const item of input) {
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const name = typeof record.name === 'string' ? record.name.trim() : '';
    if (!name) continue;
    let id = typeof record.id === 'string' && record.id ? record.id : columnId(used);
    if (used.has(id)) id = columnId(used);
    used.add(id);
    const type: TableColumnType = isTableColumnType(record.type) ? record.type : 'string';
    columns.push({ id, name: name.slice(0, MAX_NAME), type });
    if (columns.length > MAX_COLUMNS) throw new Error(`A table can have at most ${MAX_COLUMNS} columns`);
  }
  if (columns.length === 0) throw new Error('A table needs at least one column');
  return columns;
}

function normaliseValues(input: unknown, columns: TableColumn[]): Record<string, unknown> {
  if (input === undefined || input === null) return {};
  if (typeof input !== 'object' || Array.isArray(input)) throw new Error('values must be an object');
  const allowed = new Set(columns.map((column) => column.id));
  const values: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
    if (!allowed.has(key)) continue;
    if (value === undefined) continue;
    values[key] = value;
  }
  const size = JSON.stringify(values).length;
  if (size > MAX_CELL_JSON_BYTES) throw new Error('Row exceeds the 1 MB row limit');
  return values;
}

function parseValues(raw: string): Record<string, unknown> {
  const parsed = parseJson<unknown>(raw, {});
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
  return parsed as Record<string, unknown>;
}

function toRow(row: RawTableRow): DataTableRowRecord {
  return {
    id: row.id,
    values: parseValues(row.values),
    position: row.position,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

function toDetail(table: RawTable, rows: RawTableRow[]): DataTableDetail {
  return {
    table: {
      id: table.id,
      name: table.name,
      description: table.description ?? '',
      columns: parseColumns(table.columns),
      createdAt: table.createdAt.toISOString(),
      updatedAt: table.updatedAt.toISOString(),
    },
    rows: rows.map(toRow),
  };
}

async function touchTable(id: string): Promise<void> {
  await prisma.dataTable.update({ where: { id }, data: { updatedAt: new Date() } });
}

export async function listDataTables(): Promise<DataTableSummary[]> {
  const rows = await prisma.dataTable.findMany({
    include: { _count: { select: { rows: true } } },
    orderBy: { updatedAt: 'desc' },
  });
  return rows.map((row) => ({
    id: row.id,
    name: row.name,
    description: row.description ?? '',
    columnCount: parseColumns(row.columns).length,
    rowCount: row._count.rows,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  }));
}

export async function createDataTable(input: {
  name: unknown;
  description?: unknown;
  columns: unknown;
}): Promise<DataTableDetail> {
  const name = typeof input.name === 'string' ? input.name.trim() : '';
  if (!name) throw new Error('Table name is required');
  const columns = normaliseColumns(input.columns);
  const table = await prisma.dataTable.create({
    data: {
      name: name.slice(0, MAX_NAME),
      description: typeof input.description === 'string' ? input.description.trim().slice(0, 500) : null,
      columns: JSON.stringify(columns),
    },
  });
  return toDetail(table, []);
}

export async function getDataTable(id: string): Promise<DataTableDetail | null> {
  const table = await prisma.dataTable.findUnique({ where: { id } });
  if (!table) return null;
  const rows = await prisma.dataTableRow.findMany({
    where: { tableId: id },
    orderBy: [{ position: 'asc' }, { createdAt: 'asc' }],
  });
  return toDetail(table, rows);
}

export async function updateDataTableMeta(
  id: string,
  input: { name?: unknown; description?: unknown },
): Promise<DataTableDetail> {
  const existing = await prisma.dataTable.findUnique({ where: { id } });
  if (!existing) throw new Error('Table not found');
  const name = typeof input.name === 'string' && input.name.trim() ? input.name.trim().slice(0, MAX_NAME) : existing.name;
  const description = typeof input.description === 'string'
    ? input.description.trim().slice(0, 500)
    : existing.description;
  const table = await prisma.dataTable.update({
    where: { id },
    data: { name, description, updatedAt: new Date() },
  });
  const rows = await prisma.dataTableRow.findMany({
    where: { tableId: id },
    orderBy: [{ position: 'asc' }, { createdAt: 'asc' }],
  });
  return toDetail(table, rows);
}

export async function updateDataTableColumns(id: string, input: unknown): Promise<DataTableDetail> {
  const columns = normaliseColumns(input);
  const existing = await prisma.dataTable.findUnique({ where: { id } });
  if (!existing) throw new Error('Table not found');
  await prisma.dataTable.update({
    where: { id },
    data: { columns: JSON.stringify(columns), updatedAt: new Date() },
  });
  return (await getDataTable(id))!;
}

export async function addDataTableRow(
  id: string,
  input: unknown,
  columns: TableColumn[],
): Promise<DataTableDetail> {
  const existing = await prisma.dataTable.findUnique({ where: { id } });
  if (!existing) throw new Error('Table not found');
  const values = normaliseValues(input, columns);
  const max = await prisma.dataTableRow.aggregate({ where: { tableId: id }, _max: { position: true } });
  await prisma.dataTableRow.create({
    data: {
      tableId: id,
      values: JSON.stringify(values),
      position: (max._max.position ?? -1) + 1,
    },
  });
  await touchTable(id);
  return (await getDataTable(id))!;
}

export async function updateDataTableRow(
  id: string,
  rowId: string,
  input: unknown,
  columns: TableColumn[],
): Promise<DataTableDetail> {
  const values = normaliseValues(input, columns);
  const result = await prisma.dataTableRow.updateMany({
    where: { id: rowId, tableId: id },
    data: { values: JSON.stringify(values), updatedAt: new Date() },
  });
  if (result.count === 0) throw new Error('Row not found');
  await touchTable(id);
  return (await getDataTable(id))!;
}

export async function deleteDataTableRow(id: string, rowId: string): Promise<DataTableDetail> {
  const result = await prisma.dataTableRow.deleteMany({ where: { id: rowId, tableId: id } });
  if (result.count === 0) throw new Error('Row not found');
  await touchTable(id);
  return (await getDataTable(id))!;
}

export async function deleteDataTable(id: string): Promise<void> {
  await prisma.dataTable.delete({ where: { id } });
}

export { TABLE_COLUMN_TYPES };

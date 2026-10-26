// ── User data tables — browser client ────────────────────────────────────────
// Thin wrappers over /api/tables; no table logic lives here.

import type {
  CreateTableInput, DataTableDetail, DataTableRowRecord, DataTableSummary, TableColumn,
} from './types';

export class TableApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'TableApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new TableApiError((data as { error?: string }).error ?? `Request failed (${res.status})`, res.status);
  }
  return data as T;
}

export async function listDataTables(): Promise<DataTableSummary[]> {
  const data = await request<{ tables: DataTableSummary[] }>('/api/tables');
  return data.tables ?? [];
}

export async function createDataTable(input: CreateTableInput): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>('/api/tables', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return data.table;
}

export async function getDataTable(id: string): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>(`/api/tables/${encodeURIComponent(id)}`);
  return data.table;
}

export async function updateDataTableMeta(
  id: string,
  input: { name?: string; description?: string },
): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>(`/api/tables/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ action: 'update_meta', ...input }),
  });
  return data.table;
}

export async function updateDataTableColumns(id: string, columns: TableColumn[]): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>(`/api/tables/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ action: 'update_columns', columns }),
  });
  return data.table;
}

export async function addDataTableRow(id: string, values: Record<string, unknown> = {}): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>(`/api/tables/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ action: 'add_row', values }),
  });
  return data.table;
}

export async function updateDataTableRow(
  id: string,
  rowId: string,
  values: Record<string, unknown>,
): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>(`/api/tables/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ action: 'update_row', rowId, values }),
  });
  return data.table;
}

export async function deleteDataTableRow(id: string, rowId: string): Promise<DataTableDetail> {
  const data = await request<{ table: DataTableDetail }>(`/api/tables/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ action: 'delete_row', rowId }),
  });
  return data.table;
}

export async function deleteDataTable(id: string): Promise<void> {
  await request(`/api/tables/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export type { DataTableRowRecord };

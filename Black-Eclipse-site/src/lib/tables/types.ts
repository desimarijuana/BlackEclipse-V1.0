// ── User data tables — shared types ──────────────────────────────────────────
// These are spreadsheet-style user tables (n8n Data Tables equivalent), separate
// from connector-fed CustomDatasets and from the canonical market tables.

export const TABLE_COLUMN_TYPES = ['string', 'number', 'boolean', 'date', 'json'] as const;

export type TableColumnType = (typeof TABLE_COLUMN_TYPES)[number];

export interface TableColumn {
  id: string;
  name: string;
  type: TableColumnType;
}

export interface DataTableSummary {
  id: string;
  name: string;
  description: string;
  columnCount: number;
  rowCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface DataTableRowRecord {
  id: string;
  values: Record<string, unknown>;
  position: number;
  createdAt: string;
  updatedAt: string;
}

export interface DataTableDetail {
  table: {
    id: string;
    name: string;
    description: string;
    columns: TableColumn[];
    createdAt: string;
    updatedAt: string;
  };
  rows: DataTableRowRecord[];
}

export interface CreateTableInput {
  name: string;
  description?: string;
  columns: Array<{ name: string; type: TableColumnType }>;
}

export function isTableColumnType(value: unknown): value is TableColumnType {
  return typeof value === 'string' && (TABLE_COLUMN_TYPES as readonly string[]).includes(value);
}

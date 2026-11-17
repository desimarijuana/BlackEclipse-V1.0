'use client';

import { useEffect, useMemo, useState } from 'react';
import { confirmDialog } from '@/lib/ui/confirm-dialog';
import { Button } from '@/components/ui/button';
import {
  ArrowLeft, Check, ChevronDown, Loader2, Plus, Search, Trash2, X,
} from '@/lib/icons';
import {
  addDataTableRow, deleteDataTable, deleteDataTableRow, getDataTable, updateDataTableColumns,
  updateDataTableMeta, updateDataTableRow, TableApiError,
} from '@/lib/tables/client';
import {
  TABLE_COLUMN_TYPES,
  type DataTableDetail, type DataTableRowRecord, type TableColumn, type TableColumnType,
} from '@/lib/tables/types';

function cellValue(value: unknown, type: TableColumnType): string {
  if (value === null || value === undefined) return '';
  if (type === 'date' && typeof value === 'string') return value.slice(0, 10);
  if (type === 'json') {
    if (typeof value === 'string') return value;
    try { return JSON.stringify(value); } catch { return ''; }
  }
  return String(value);
}

function parseCell(input: string, type: TableColumnType): unknown {
  if (type === 'number') return input === '' ? null : Number(input);
  if (type === 'boolean') return input === 'true';
  return input;
}

export function TableGrid({
  initial,
  onBack,
  onDeleted,
}: {
  initial: DataTableDetail;
  onBack: () => void;
  onDeleted: () => void;
}) {
  const [name, setName] = useState(initial.table.name);
  const [description, setDescription] = useState(initial.table.description);
  const [columns, setColumns] = useState<TableColumn[]>(initial.table.columns);
  const [rows, setRows] = useState<DataTableRowRecord[]>(initial.rows);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [addingColumn, setAddingColumn] = useState(false);
  const [newColumnName, setNewColumnName] = useState('');
  const [newColumnType, setNewColumnType] = useState<TableColumnType>('string');

  useEffect(() => {
    setName(initial.table.name);
    setDescription(initial.table.description);
    setColumns(initial.table.columns);
    setRows(initial.rows);
  }, [initial]);

  const reload = async () => {
    try {
      const fresh = await getDataTable(initial.table.id);
      setName(fresh.table.name);
      setDescription(fresh.table.description);
      setColumns(fresh.table.columns);
      setRows(fresh.rows);
    } catch {
      /* the visible state stays as it was; the error banner explains the failed write */
    }
  };

  const visibleRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      columns.some((column) => cellValue(row.values[column.id], column.type).toLowerCase().includes(q)),
    );
  }, [rows, columns, query]);

  const setCell = (rowId: string, columnId: string, value: unknown) => {
    setRows((prev) => prev.map((row) => (
      row.id === rowId ? { ...row, values: { ...row.values, [columnId]: value } } : row
    )));
  };

  const commitRow = async (row: DataTableRowRecord) => {
    try {
      await updateDataTableRow(initial.table.id, row.id, row.values);
      setError(null);
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : 'Could not save this cell');
    }
  };

  const commitMeta = async () => {
    try {
      await updateDataTableMeta(initial.table.id, { name: name.trim() || initial.table.name, description });
      setError(null);
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : 'Could not save table details');
    }
  };

  const commitColumns = async (next: TableColumn[]) => {
    setColumns(next);
    try {
      const detail = await updateDataTableColumns(initial.table.id, next);
      setColumns(detail.table.columns);
      setRows(detail.rows);
      setError(null);
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : 'Could not save columns');
      void reload();
    }
  };

  const renameColumn = (index: number, nextName: string) => {
    setColumns((prev) => prev.map((column, i) => (i === index ? { ...column, name: nextName } : column)));
  };

  const addColumn = async () => {
    const clean = newColumnName.trim();
    if (!clean) return;
    const next = [...columns, { id: `col_${Math.random().toString(36).slice(2, 10)}`, name: clean, type: newColumnType }];
    setNewColumnName('');
    setNewColumnType('string');
    setAddingColumn(false);
    await commitColumns(next);
  };

  const removeColumn = async (column: TableColumn) => {
    if (columns.length === 1) return;
    if (!(await confirmDialog({ title: `Delete the “${column.name}” column?`, description: 'Its cells will no longer be shown.', tone: 'danger' }))) return;
    await commitColumns(columns.filter((item) => item.id !== column.id));
  };

  const addRow = async () => {
    setBusy(true);
    try {
      const detail = await addDataTableRow(initial.table.id, {});
      setRows(detail.rows);
      setError(null);
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : 'Could not add a row');
    } finally {
      setBusy(false);
    }
  };

  const removeRow = async (rowId: string) => {
    try {
      const detail = await deleteDataTableRow(initial.table.id, rowId);
      setRows(detail.rows);
      setError(null);
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : 'Could not delete the row');
    }
  };

  const removeTable = async () => {
    if (!(await confirmDialog({ title: `Delete the whole “${name}” table and all of its rows?`, tone: 'danger' }))) return;
    try {
      await deleteDataTable(initial.table.id);
      onDeleted();
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : 'Could not delete the table');
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full px-4 py-6 md:px-6 lg:px-8">
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft size={13} /> All tables
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <div className="relative">
              <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Find a row…"
                className="w-44 rounded-md border border-white/10 bg-background/60 py-1 pl-7 pr-2 text-[11px] outline-none focus:border-sky-400/50"
              />
            </div>
            <Button type="button" variant="destructive" size="sm" onClick={() => void removeTable()}>
              <Trash2 size={11} /> Delete table
            </Button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => void commitMeta()}
            className="min-w-0 max-w-[420px] flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-[22px] font-semibold tracking-tight text-foreground outline-none hover:border-white/10 focus:border-sky-400/50"
          />
          <div className="flex items-center gap-2 text-[10.5px] text-muted-foreground">
            <span>{columns.length} columns</span>
            <span>{rows.length} rows</span>
          </div>
        </div>
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          onBlur={() => void commitMeta()}
          placeholder="Add a description…"
          className="mt-0.5 w-full max-w-2xl rounded-md border border-transparent bg-transparent px-1 py-0.5 text-[11px] text-muted-foreground outline-none hover:border-white/10 focus:border-sky-400/50"
        />

        {error && <p className="mt-3 rounded-md border border-rose-500/25 bg-rose-500/10 px-2.5 py-1.5 text-[10.5px] text-rose-200">{error}</p>}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" disabled={busy} onClick={() => void addRow()}>
            <Plus size={12} /> Add row
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setAddingColumn((value) => !value)}>
            <Plus size={12} /> Add column <ChevronDown size={10} />
          </Button>
          {busy && <Loader2 size={13} className="animate-spin text-muted-foreground" />}
        </div>

        {addingColumn && (
          <div className="glass-card mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-white/10 px-2 py-1.5">
            <input
              autoFocus
              value={newColumnName}
              onChange={(event) => setNewColumnName(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void addColumn(); }}
              placeholder="Column name"
              className="min-w-0 flex-1 rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-sky-400/50"
            />
            <select
              value={newColumnType}
              onChange={(event) => setNewColumnType(event.target.value as TableColumnType)}
              className="rounded-md border border-white/10 bg-background/60 px-1.5 py-1 text-[10.5px] text-muted-foreground outline-none"
            >
              {TABLE_COLUMN_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
            <Button type="button" size="xs" onClick={() => void addColumn()}>
              <Check size={11} />
            </Button>
            <Button type="button" variant="ghost" size="icon-xs" onClick={() => setAddingColumn(false)}>
              <X size={11} />
            </Button>
          </div>
        )}

        <div className="glass-card mt-3 overflow-hidden rounded-xl border border-white/10">
          <div className="max-h-[calc(100dvh-18rem)] overflow-auto">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm">
                <tr className="border-b border-white/10">
                  <th className="w-10 px-2 py-2 text-center text-[7.5px] font-semibold uppercase tracking-wider text-muted-foreground">#</th>
                  {columns.map((column, index) => (
                    <th key={column.id} className="group/head min-w-[150px] border-l border-white/5 px-1 py-1.5">
                      <div className="flex items-center gap-0.5">
                        <input
                          value={column.name}
                          onChange={(event) => renameColumn(index, event.target.value)}
                          onBlur={() => void commitColumns(columns)}
                          className="min-w-0 flex-1 rounded bg-transparent px-1 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground outline-none hover:bg-white/5 focus:bg-white/5 focus:text-foreground"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          title="Delete column"
                          disabled={columns.length === 1}
                          onClick={() => void removeColumn(column)}
                          className="h-5 w-5 text-muted-foreground opacity-0 group-hover/head:opacity-100 hover:text-rose-400"
                        >
                          <X size={10} />
                        </Button>
                      </div>
                      <div className="px-1 text-[8px] text-muted-foreground/60">{column.type}</div>
                    </th>
                  ))}
                  <th className="w-9 px-1 py-2" />
                </tr>
              </thead>
              <tbody>
                {visibleRows.length === 0 && (
                  <tr>
                    <td colSpan={columns.length + 2} className="px-3 py-12 text-center text-[11.5px] text-muted-foreground">
                      {rows.length === 0 ? 'No rows yet — click “Add row” to start entering data.' : 'No rows match that search.'}
                    </td>
                  </tr>
                )}
                {visibleRows.map((row, rowIndex) => (
                  <tr key={row.id} className="group/row border-b border-white/5 last:border-0 hover:bg-white/[0.03]">
                    <td className="px-2 py-0 text-center text-[9px] text-muted-foreground/70">{rowIndex + 1}</td>
                    {columns.map((column) => (
                      <td key={column.id} className="border-l border-white/5 p-0">
                        {column.type === 'boolean' ? (
                          <div className="flex h-8 items-center justify-center">
                            <input
                              type="checkbox"
                              checked={Boolean(row.values[column.id])}
                              onChange={(event) => {
                                const next = { ...row, values: { ...row.values, [column.id]: event.target.checked } };
                                setCell(row.id, column.id, event.target.checked);
                                void commitRow(next);
                              }}
                              className="h-3.5 w-3.5 accent-sky-500"
                            />
                          </div>
                        ) : (
                          <input
                            type={column.type === 'number' ? 'number' : column.type === 'date' ? 'date' : 'text'}
                            value={cellValue(row.values[column.id], column.type)}
                            onChange={(event) => setCell(row.id, column.id, parseCell(event.target.value, column.type))}
                            onBlur={() => void commitRow(row)}
                            onKeyDown={(event) => { if (event.key === 'Enter') (event.target as HTMLInputElement).blur(); }}
                            className="h-8 w-full min-w-[150px] bg-transparent px-2 text-[11px] text-foreground outline-none focus:bg-sky-500/5 focus:ring-1 focus:ring-inset focus:ring-sky-400/40"
                          />
                        )}
                      </td>
                    ))}
                    <td className="px-0">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        title="Delete row"
                        onClick={() => void removeRow(row.id)}
                        className="mx-auto h-6 w-6 text-muted-foreground opacity-0 group-hover/row:opacity-100 hover:text-rose-400"
                      >
                        <Trash2 size={11} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">
          Cells save when you leave the field, or immediately for checkboxes and dates. This table is stored in Eclipse&apos;s local data vault.
        </p>
      </div>
    </div>
  );
}

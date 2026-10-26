'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Database, Plus, Trash2, X } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { createDataTable, TableApiError } from '@/lib/tables/client';
import { TABLE_COLUMN_TYPES, type DataTableDetail, type TableColumnType } from '@/lib/tables/types';

interface ColumnDraft {
  name: string;
  type: TableColumnType;
}

const NEW_COLUMN: ColumnDraft = { name: '', type: 'string' };

export function CreateTableDialog({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (table: DataTableDetail) => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [columns, setColumns] = useState<ColumnDraft[]>([{ name: 'Name', type: 'string' }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setColumn = (index: number, patch: Partial<ColumnDraft>) => {
    setColumns((prev) => prev.map((column, i) => (i === index ? { ...column, ...patch } : column)));
  };

  const submit = async () => {
    const cleanName = name.trim();
    const cleanColumns = columns.map((column) => ({ ...column, name: column.name.trim() })).filter((column) => column.name);
    if (!cleanName) {
      setError('Give the table a name.');
      return;
    }
    if (cleanColumns.length === 0) {
      setError('Add at least one column.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const table = await createDataTable({ name: cleanName, description: description.trim(), columns: cleanColumns });
      onCreated(table);
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : err instanceof Error ? err.message : 'Failed to create table');
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[125] flex items-center justify-center px-4">
      <button type="button" aria-label="Cancel" onClick={onCancel} className="absolute inset-0 cursor-default bg-black/50" />
      <div className="glass-card-strong relative flex max-h-[86vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/10 shadow-2xl">
        <div className="flex items-start gap-2.5 border-b border-white/10 px-4 py-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sky-500/15 text-sky-300">
            <Database size={17} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-semibold text-foreground">New table</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Create a spreadsheet-style table for your own data.</p>
          </div>
          <Button type="button" variant="ghost" size="icon-xs" onClick={onCancel} className="shrink-0">
            <X size={13} />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <label className="block">
            <span className="mb-1 block text-[10.5px] text-muted-foreground">Table name</span>
            <input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Trade log"
              className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1.5 text-[12px] outline-none focus:border-sky-400/50"
            />
          </label>
          <label className="mt-2.5 block">
            <span className="mb-1 block text-[10.5px] text-muted-foreground">Description (optional)</span>
            <input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What will this table hold?"
              className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1.5 text-[12px] outline-none focus:border-sky-400/50"
            />
          </label>

          <div className="mt-4">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Columns</span>
              <span className="text-[10px] text-muted-foreground">{columns.length}/60</span>
            </div>
            <div className="space-y-1.5">
              {columns.map((column, index) => (
                <div key={index} className="flex items-center gap-1.5">
                  <input
                    value={column.name}
                    onChange={(event) => setColumn(index, { name: event.target.value })}
                    placeholder={`Column ${index + 1}`}
                    className="min-w-0 flex-1 rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-sky-400/50"
                  />
                  <select
                    value={column.type}
                    onChange={(event) => setColumn(index, { type: event.target.value as TableColumnType })}
                    className="w-[104px] shrink-0 rounded-md border border-white/10 bg-background/60 px-1.5 py-1 text-[11px] text-muted-foreground outline-none focus:border-sky-400/50"
                  >
                    {TABLE_COLUMN_TYPES.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    title="Remove column"
                    disabled={columns.length === 1}
                    onClick={() => setColumns((prev) => prev.filter((_, i) => i !== index))}
                    className="shrink-0 hover:text-rose-400"
                  >
                    <Trash2 size={12} />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              type="button"
              variant="outline"
              size="xs"
              disabled={columns.length >= 60}
              onClick={() => setColumns((prev) => [...prev, { ...NEW_COLUMN, name: `Column ${prev.length + 1}` }])}
              className="mt-2"
            >
              <Plus size={11} /> Add column
            </Button>
          </div>

          {error && <p className="mt-3 rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-2.5">
          <Button type="button" variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" size="sm" disabled={busy} onClick={() => void submit()}>
            {busy ? 'Creating…' : 'Create table'}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

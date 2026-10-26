'use client';

// ── Tables — spreadsheet-style user data ─────────────────────────────────────
// A first-class, n8n-Data-Tables-style surface: create a table, define columns,
// add rows and edit cells. Stored in Eclipse's local data vault. Connector-fed
// datasets remain a separate read-only surface under Settings → Data Sources.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronRight, Clock, Database, Loader2, Plus, RefreshCw, Search, Settings2, Trash2,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  deleteDataTable, getDataTable, listDataTables, TableApiError,
} from '@/lib/tables/client';
import type { DataTableDetail, DataTableSummary } from '@/lib/tables/types';
import { CreateTableDialog } from './create-table-dialog';
import { TableGrid } from './table-grid';

function relativeDate(value: string): string {
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return '';
  const delta = Date.now() - then;
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

export function TablesScreen({ onOpenDataSources }: { onOpenDataSources?: () => void }) {
  const [tables, setTables] = useState<DataTableSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<DataTableDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTables(await listDataTables());
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : err instanceof Error ? err.message : 'Failed to load tables');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openTable = async (id: string) => {
    setLoadingDetail(true);
    setError(null);
    try {
      setSelected(await getDataTable(id));
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : err instanceof Error ? err.message : 'Failed to open table');
    } finally {
      setLoadingDetail(false);
    }
  };

  const remove = async (table: DataTableSummary) => {
    if (!window.confirm(`Delete “${table.name}” and all ${table.rowCount} row(s)?`)) return;
    try {
      await deleteDataTable(table.id);
      if (selected?.table.id === table.id) setSelected(null);
      await load();
    } catch (err) {
      setError(err instanceof TableApiError ? err.message : err instanceof Error ? err.message : 'Failed to delete table');
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return tables;
    return tables.filter(
      (table) => table.name.toLowerCase().includes(q) || table.description.toLowerCase().includes(q),
    );
  }, [tables, query]);

  if (selected) {
    return (
      <TableGrid
        initial={selected}
        onBack={() => {
          setSelected(null);
          void load();
        }}
        onDeleted={() => {
          setSelected(null);
          void load();
        }}
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full px-4 py-6 md:px-6 lg:px-8">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-sky-400">
              <Database size={14} /> Data
            </div>
            <h1 className="mt-1 text-[24px] font-semibold tracking-tight text-foreground">Tables</h1>
            <p className="mt-1 max-w-2xl text-[12px] text-muted-foreground">
              Spreadsheet-style tables you can fill with your own data. Stored locally and available to workflows.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => void load()}
              title="Refresh tables"
            >
              <RefreshCw size={13} />
            </Button>
            {onOpenDataSources && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onOpenDataSources}
                title="Connector-fed datasets live in Settings → Data Sources"
              >
                <Settings2 size={13} /> Data sources
              </Button>
            )}
            <Button type="button" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus size={13} /> New table
            </Button>
          </div>
        </header>

        {error && <p className="mt-3 rounded-md bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-200">{error}</p>}

        <div className="mt-5 flex items-center gap-2">
          <div className="relative w-full max-w-sm">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search tables…"
              className="w-full rounded-lg border border-white/10 bg-background/60 py-1.5 pl-8 pr-2 text-[12px] outline-none focus:border-sky-400/50"
            />
          </div>
          <span className="ml-auto text-[10.5px] text-muted-foreground">{filtered.length} table{filtered.length === 1 ? '' : 's'}</span>
        </div>

        {loadingDetail && (
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Opening table…
          </p>
        )}

        {loading && tables.length === 0 && (
          <div className="mt-10 flex items-center justify-center gap-2 text-[12px] text-muted-foreground">
            <Loader2 size={14} className="animate-spin" /> Loading tables…
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="glass-card mt-4 flex flex-col items-center gap-2 rounded-xl border border-dashed border-white/15 px-6 py-14 text-center">
            <Database size={26} className="text-sky-400/80" />
            <p className="text-[13px] font-medium text-foreground">
              {tables.length === 0 ? 'No tables yet' : 'No tables match that search'}
            </p>
            <p className="max-w-md text-[11.5px] text-muted-foreground">
              {tables.length === 0
                ? 'Create a table, define its columns, then add rows like a spreadsheet.'
                : 'Try a different name or description.'}
            </p>
            {tables.length === 0 && (
              <Button type="button" size="sm" onClick={() => setCreateOpen(true)} className="mt-1">
                <Plus size={13} /> New table
              </Button>
            )}
          </div>
        )}

        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {filtered.map((table) => (
            <article
              key={table.id}
              className={cn(
                'glass-card group relative flex min-h-[128px] flex-col rounded-xl border border-white/10 p-3 transition-colors hover:border-sky-400/30',
              )}
            >
              <button type="button" onClick={() => void openTable(table.id)} className="min-w-0 flex-1 text-left">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 text-sky-300">
                    <Database size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-foreground">{table.name}</span>
                    <span className="mt-0.5 line-clamp-2 block text-[10.5px] leading-snug text-muted-foreground">
                      {table.description || 'No description.'}
                    </span>
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[9.5px] text-muted-foreground">
                  <span className="rounded-full border border-white/10 px-1.5 py-0.5">{table.columnCount} columns</span>
                  <span className="rounded-full border border-white/10 px-1.5 py-0.5">{table.rowCount} rows</span>
                  <span className="flex items-center gap-1"><Clock size={9} /> {relativeDate(table.updatedAt)}</span>
                </div>
              </button>
              <div className="mt-2 flex items-center justify-between border-t border-white/5 pt-1.5">
                <span className="flex items-center gap-1 text-[10px] font-medium text-sky-300">
                  Open table <ChevronRight size={10} />
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  title="Delete table"
                  onClick={() => void remove(table)}
                  className="text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-rose-400"
                >
                  <Trash2 size={11} />
                </Button>
              </div>
            </article>
          ))}
        </div>
      </div>

      {createOpen && (
        <CreateTableDialog
          onCancel={() => setCreateOpen(false)}
          onCreated={(table) => {
            setCreateOpen(false);
            setSelected(table);
            void load();
          }}
        />
      )}
    </div>
  );
}

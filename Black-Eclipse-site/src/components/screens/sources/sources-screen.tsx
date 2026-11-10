'use client';

// ── Sources — the large-corpus browser ───────────────────────────────────────
// Open a folder or drive in place (nothing is copied), watch the catalog scan,
// search by routing (metadata / full-text / bounded scan / semantic) and read
// bounded windows. A card never contains the whole file, whatever its size.

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  AlertCircle, Database, FileText, FolderPlus, Server as HardDrive,
  Image as ImageIcon, Layers, Loader2, Play, RefreshCw, Search, Table2,
  Terminal, Trash2, X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  addRoot, humanBytes, indexSources, listRoots, openSource, readWindow,
  removeRoot, runSourceSql, searchSources, sourceStats, startScan,
  type SourceHit, type SourceOpenResult, type SourceRoot,
  type SourceSearchResult, type SourceStats, type SqlResult,
} from '@/lib/sources/client';

type Mode = 'auto' | 'metadata' | 'text' | 'raw' | 'similar';

const MODES: Array<{ id: Mode; label: string; hint: string }> = [
  { id: 'auto', label: 'Auto', hint: 'Route to the cheapest engine' },
  { id: 'metadata', label: 'Metadata', hint: 'Names, size, dates — no content read' },
  { id: 'text', label: 'Text', hint: 'Full-text index, with a scan fallback' },
  { id: 'raw', label: 'Raw', hint: 'Bounded parallel scan (regex allowed)' },
  { id: 'similar', label: 'Similar', hint: 'Semantic vectors, when configured' },
];

const CLASS_ICON: Record<string, typeof FileText> = {
  text: FileText,
  code: Terminal,
  table: Table2,
  document: FileText,
  image: ImageIcon,
  archive: Layers,
  database: Database,
  binary: HardDrive,
};

function ClassIcon({ klass, className }: { klass: string; className?: string }) {
  const Icon = CLASS_ICON[klass] ?? FileText;
  return <Icon className={className} />;
}

export function SourcesScreen({ active = true }: { active?: boolean }) {
  const [stats, setStats] = useState<SourceStats | null>(null);
  const [roots, setRoots] = useState<SourceRoot[]>([]);
  const [rootPath, setRootPath] = useState('');
  const [rootLabel, setRootLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<Mode>('auto');
  const [rootFilter, setRootFilter] = useState<string>('');
  const [classFilter, setClassFilter] = useState<string>('');
  const [result, setResult] = useState<SourceSearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  const [selected, setSelected] = useState<SourceOpenResult | null>(null);
  const [windowText, setWindowText] = useState('');
  const [windowOffset, setWindowOffset] = useState(0);
  const [windowDone, setWindowDone] = useState(false);

  const [sql, setSql] = useState('SELECT * FROM t LIMIT 50');
  const [sqlResult, setSqlResult] = useState<SqlResult | null>(null);
  const [runningSql, setRunningSql] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextStats, nextRoots] = await Promise.all([sourceStats(), listRoots()]);
      setStats(nextStats);
      setRoots(nextRoots.roots);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load sources');
    }
  }, []);

  useEffect(() => {
    if (active) void refresh();
  }, [active, refresh]);

  const scanning = roots.some((root) => root.status === 'SCANNING');

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (!active || !scanning) return;
    pollRef.current = setInterval(() => {
      void refresh();
    }, 1500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [active, scanning, refresh]);

  const onAddRoot = async () => {
    const path = rootPath.trim();
    if (!path) return;
    setBusy(true);
    setError(null);
    try {
      await addRoot(path, rootLabel.trim() || undefined);
      setRootPath('');
      setRootLabel('');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add that folder');
    } finally {
      setBusy(false);
    }
  };

  const onScan = async (root: SourceRoot) => {
    setError(null);
    try {
      await startScan(root.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the scan');
    }
  };

  const onRemove = async (root: SourceRoot) => {
    if (!window.confirm(`Remove "${root.label}" from the catalog? The folder itself is not touched.`)) return;
    try {
      await removeRoot(root.id);
      setResult(null);
      setSelected(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove the root');
    }
  };

  const onSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setSelected(null);
    try {
      const next = await searchSources({
        query: query.trim(),
        mode,
        rootIds: rootFilter ? [rootFilter] : undefined,
        klass: classFilter || undefined,
        limit: 60,
      });
      setResult(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const onOpen = async (hit: SourceHit) => {
    setError(null);
    try {
      const opened = await openSource({ rootId: hit.root_id, relpath: hit.relpath });
      setSelected(opened);
      const start = hit.offset ?? 0;
      setWindowOffset(start);
      setWindowDone(false);
      setSqlResult(null);
      if (opened.card.klass === 'text' || opened.card.klass === 'code') {
        const window = await readWindow({
          rootId: hit.root_id, relpath: hit.relpath, offset: start, length: 32 * 1024,
        });
        setWindowText(window.text ?? '');
        setWindowDone(window.eof);
      } else {
        setWindowText('');
        setWindowDone(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open that file');
    }
  };

  const onMore = async () => {
    if (!selected) return;
    try {
      const next = await readWindow({
        rootId: selected.root.id,
        relpath: selected.file.relpath,
        offset: windowOffset + 32 * 1024,
        length: 32 * 1024,
      });
      setWindowOffset(windowOffset + 32 * 1024);
      setWindowText((prev) => prev + (next.text ?? ''));
      setWindowDone(next.eof);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read further');
    }
  };

  const onIndex = async () => {
    setIndexing(true);
    setError(null);
    setNotice(null);
    try {
      const outcome = await indexSources({
        rootIds: rootFilter ? [rootFilter] : undefined,
        limitFiles: 100,
        budgetS: 30,
        semantic: false,
      });
      setNotice(
        `Indexed ${outcome.indexed} file(s), ${outcome.chunks} chunk(s) in ${outcome.elapsedMs} ms.`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Indexing failed');
    } finally {
      setIndexing(false);
    }
  };

  const onSql = async () => {
    if (!selected || !sql.trim()) return;
    setRunningSql(true);
    setError(null);
    try {
      const outcome = await runSourceSql({
        rootId: selected.root.id,
        relpath: selected.file.relpath,
        sql: sql.trim(),
        maxRows: 100,
      });
      setSqlResult(outcome);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SQL failed');
    } finally {
      setRunningSql(false);
    }
  };

  const tableSelected = selected?.card.klass === 'table';

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 px-4 py-6 md:px-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Sources</h1>
            <p className="text-sm text-muted-foreground">
              Open folders and drives in place. Nothing is copied; queries route to metadata,
              the text index, DuckDB, or a bounded scan.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="glass-button inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
        {stats && (
          <div className="flex flex-wrap gap-2 text-xs">
            <Stat label="Files" value={stats.files.toLocaleString()} />
            <Stat label="Size" value={humanBytes(stats.bytes)} />
            <Stat label="Indexed" value={`${stats.indexedFiles.toLocaleString()} files`} />
            <Stat label="Chunks" value={stats.chunks.toLocaleString()} />
            <Stat
              label="Semantic"
              value={stats.semantic.available ? 'available' : 'off'}
              muted={!stats.semantic.available}
            />
          </div>
        )}
      </header>

      {error && <Banner tone="error" icon={<AlertCircle className="h-4 w-4" />}>{error}</Banner>}
      {notice && <Banner tone="info" icon={<CheckDot />}>{notice}</Banner>}

      <section className="glass-card rounded-2xl p-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <FolderPlus className="h-4 w-4" /> Add a source root
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Point at a folder or drive. A 4 TB file or a million-file folder is catalogued by
          reference — the bytes never move.
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            value={rootPath}
            onChange={(event) => setRootPath(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') void onAddRoot(); }}
            placeholder="D:\data  or  /mnt/archive"
            className="min-w-0 flex-1 rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-foreground/30"
          />
          <input
            value={rootLabel}
            onChange={(event) => setRootLabel(event.target.value)}
            placeholder="Label (optional)"
            className="w-full rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-sm outline-none placeholder:text-muted-foreground/60 sm:w-40"
          />
          <button
            type="button"
            onClick={() => void onAddRoot()}
            disabled={busy || !rootPath.trim()}
            className="glass-button inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderPlus className="h-4 w-4" />}
            Add
          </button>
        </div>
      </section>

      <section className="space-y-2">
        {roots.length === 0 && (
          <div className="glass-card rounded-2xl p-6 text-sm text-muted-foreground">
            No roots yet. Add a folder above to start. The catalog is stored in
            <code className="mx-1 rounded bg-background/60 px-1.5 py-0.5 text-xs">.black-eclipse/sources</code>
            — never inside your data.
          </div>
        )}
        {roots.map((root) => (
          <div key={root.id} className="glass-card flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
            <HardDrive className="h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{root.label}</div>
              <div className="truncate text-xs text-muted-foreground">{root.path}</div>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <div>{root.file_count.toLocaleString()} files · {humanBytes(root.total_bytes)}</div>
              <div className={cn(root.status === 'ERROR' && 'text-red-400', root.status === 'SCANNING' && 'text-sky-400')}>
                {root.status === 'SCANNING' ? 'scanning…' : root.status.toLowerCase()}
                {root.error ? ` · ${root.error}` : ''}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => void onScan(root)}
                disabled={root.status === 'SCANNING'}
                className="glass-button inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs disabled:opacity-40"
              >
                {root.status === 'SCANNING' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Scan
              </button>
              <button
                type="button"
                onClick={() => void onRemove(root)}
                className="inline-flex items-center rounded-lg px-2 py-1.5 text-xs text-muted-foreground hover:text-red-400"
                title="Remove from catalog (the folder is untouched)"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </section>

      <section className="glass-card space-y-3 rounded-2xl p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void onSearch(); }}
              placeholder="Search names, content, a pattern — or ask for *.parquet"
              className="w-full rounded-xl border border-border/60 bg-background/60 py-2 pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-foreground/30"
            />
          </div>
          <button
            type="button"
            onClick={() => void onSearch()}
            disabled={searching || !query.trim()}
            className="glass-button inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm disabled:opacity-50"
          >
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Search
          </button>
          <button
            type="button"
            onClick={() => void onIndex()}
            disabled={indexing || roots.length === 0}
            className="glass-button inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm disabled:opacity-50"
            title="Build a bounded text index so the next search is instant"
          >
            {indexing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Layers className="h-4 w-4" />}
            Index
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {MODES.map((entry) => (
            <button
              key={entry.id}
              type="button"
              title={entry.hint}
              onClick={() => setMode(entry.id)}
              className={cn(
                'rounded-lg px-2.5 py-1 text-xs transition-colors',
                mode === entry.id
                  ? 'bg-foreground/10 text-foreground'
                  : 'text-muted-foreground hover:bg-foreground/5',
              )}
            >
              {entry.label}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-border/60" />
          <select
            value={rootFilter}
            onChange={(event) => setRootFilter(event.target.value)}
            className="rounded-lg border border-border/50 bg-background/60 px-2 py-1 text-xs"
          >
            <option value="">All roots</option>
            {roots.map((root) => (
              <option key={root.id} value={root.id}>{root.label}</option>
            ))}
          </select>
          <select
            value={classFilter}
            onChange={(event) => setClassFilter(event.target.value)}
            className="rounded-lg border border-border/50 bg-background/60 px-2 py-1 text-xs"
          >
            <option value="">All types</option>
            {['text', 'code', 'table', 'document', 'image', 'audio', 'video', 'archive', 'database', 'binary'].map((klass) => (
              <option key={klass} value={klass}>{klass}</option>
            ))}
          </select>
        </div>
        {result && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>
              {result.hits.length} hit(s) via {result.plan.engines.join(' + ') || 'none'} · {result.elapsedMs} ms
            </span>
            <span>{result.scannedFiles.toLocaleString()} file(s), {humanBytes(result.scannedBytes)} scanned</span>
            {result.truncated && <span className="text-amber-400">partial: budget or result cap reached</span>}
            {result.warnings.map((warning) => (
              <span key={warning} className="text-amber-400">{warning}</span>
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section className="space-y-1.5">
          {result?.hits.map((hit) => (
            <button
              key={`${hit.root_id}:${hit.relpath}:${hit.offset ?? 0}`}
              type="button"
              onClick={() => void onOpen(hit)}
              className={cn(
                'glass-card-subtle w-full rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-foreground/5',
                selected?.file.relpath === hit.relpath && 'ring-1 ring-foreground/20',
              )}
            >
              <div className="flex items-center gap-2">
                <ClassIcon klass={hit.klass} className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm">{hit.relpath}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{hit.engine}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{humanBytes(hit.size)}</span>
              </div>
              {hit.snippet && (
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{hit.snippet}</p>
              )}
              {(hit.line || hit.page) && (
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {hit.line ? `line ${hit.line}` : `page ${hit.page}`}
                </p>
              )}
            </button>
          ))}
          {result && result.hits.length === 0 && (
            <div className="glass-card rounded-xl p-4 text-sm text-muted-foreground">
              No matches. Try <button className="underline" type="button" onClick={() => setMode('raw')}>Raw</button> for
              unindexed content, or widen the filters.
            </div>
          )}
          {!result && (
            <div className="glass-card rounded-xl p-4 text-sm text-muted-foreground">
              Search across every registered root. Auto routes to metadata when the query is a
              filename/extension, to the text index when it is content, and to a bounded scan when
              nothing is indexed yet.
            </div>
          )}
        </section>

        <section className="space-y-3">
          {!selected && (
            <div className="glass-card rounded-2xl p-4 text-sm text-muted-foreground">
              Select a result to open its card. The card is bounded: format, size, schema/pages,
              a preview and the index state — never the whole file.
            </div>
          )}
          {selected && (
            <div className="glass-card space-y-3 rounded-2xl p-4">
              <div className="flex items-start gap-2">
                <ClassIcon klass={selected.card.klass} className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{selected.file.relpath}</div>
                  <div className="text-xs text-muted-foreground">
                    {selected.card.klass} · {humanBytes(selected.card.size)} ·{' '}
                    {selected.card.index_state.toLowerCase()}
                    {selected.card.pages ? ` · ${selected.card.pages} pages` : ''}
                    {selected.card.rows_hint != null ? ` · ${selected.card.rows_hint.toLocaleString()} rows` : ''}
                    {selected.card.width && selected.card.height ? ` · ${selected.card.width}×${selected.card.height}` : ''}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="rounded-lg p-1 text-muted-foreground hover:bg-foreground/5"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {selected.card.columns.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {selected.card.columns.slice(0, 30).map((column) => (
                    <span
                      key={column.name}
                      className="rounded-md bg-foreground/5 px-1.5 py-0.5 text-[11px] text-muted-foreground"
                    >
                      {column.name}{column.type ? `: ${column.type}` : ''}
                    </span>
                  ))}
                </div>
              )}

              {selected.card.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 text-[11px] text-amber-300">
                  {selected.card.warnings.join(' · ')}
                </div>
              )}

              {selected.card.head && (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-background/60 p-3 font-mono text-[11px] leading-relaxed text-foreground/90">
                  {selected.card.head.slice(0, 6_000)}
                </pre>
              )}

              {(selected.card.klass === 'text' || selected.card.klass === 'code') && (
                <div className="space-y-2">
                  {windowText && (
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-background/60 p-3 font-mono text-[11px] leading-relaxed">
                      {windowText}
                    </pre>
                  )}
                  {!windowDone && (
                    <button
                      type="button"
                      onClick={() => void onMore()}
                      className="glass-button rounded-lg px-3 py-1.5 text-xs"
                    >
                      Read the next 32 KB
                    </button>
                  )}
                </div>
              )}

              {tableSelected && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-xs font-medium">
                    <Table2 className="h-3.5 w-3.5" /> Query this table
                    <span className="font-normal text-muted-foreground">— bound as view `t`</span>
                  </div>
                  <textarea
                    value={sql}
                    onChange={(event) => setSql(event.target.value)}
                    rows={3}
                    spellCheck={false}
                    className="w-full rounded-xl border border-border/60 bg-background/60 p-2.5 font-mono text-[11px] outline-none focus:border-foreground/30"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void onSql()}
                      disabled={runningSql}
                      className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
                    >
                      {runningSql ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                      Run
                    </button>
                    {sqlResult && (
                      <span className={cn('text-[11px]', sqlResult.ok ? 'text-muted-foreground' : 'text-red-400')}>
                        {sqlResult.ok
                          ? `${sqlResult.row_count} row(s) in ${sqlResult.elapsed_ms} ms`
                          : sqlResult.error}
                      </span>
                    )}
                  </div>
                  {sqlResult?.ok && (
                    <div className="max-h-64 overflow-auto rounded-xl bg-background/60">
                      <table className="w-full text-left text-[11px]">
                        <thead className="sticky top-0 bg-background/80 text-muted-foreground">
                          <tr>
                            {sqlResult.columns.map((column) => (
                              <th key={column} className="px-2 py-1.5 font-medium">{column}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {sqlResult.rows.slice(0, 50).map((row, index) => (
                            <tr key={index} className="border-t border-border/30">
                              {row.map((value, cell) => (
                                <td key={cell} className="px-2 py-1">{value === null ? '—' : String(value)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <span className={cn('glass-card-subtle rounded-lg px-2.5 py-1', muted && 'text-muted-foreground')}>
      <span className="text-muted-foreground">{label}</span> <span className="font-medium">{value}</span>
    </span>
  );
}

function Banner({ tone, icon, children }: { tone: 'error' | 'info'; icon: ReactNode; children: ReactNode }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-xl border px-3 py-2 text-sm',
        tone === 'error'
          ? 'border-red-500/30 bg-red-500/10 text-red-300'
          : 'border-sky-500/30 bg-sky-500/10 text-sky-200',
      )}
    >
      <span className="mt-0.5">{icon}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

function CheckDot() {
  return <span className="mt-0.5 block h-2 w-2 rounded-full bg-sky-400" />;
}

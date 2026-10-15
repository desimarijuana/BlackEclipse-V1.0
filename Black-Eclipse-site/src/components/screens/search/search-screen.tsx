'use client';

// ── Search Intelligence admin / debug screen ─────────────────────────────────
// Operator surface over the unified retrieval layer: run a semantic/keyword/
// hybrid search, inspect citations and per-component scores, view a debug trace
// of the pipeline, and monitor the index/embedding health. Talks only to the
// front-door proxy (`/api/harness/search/*`), which talks to the same service
// the agent tools use — so the screen and the agent can never disagree.

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { Search as SearchIcon, RefreshCw, Database, AlertTriangle } from '@/lib/icons';
import {
  bulkIndexSearch,
  debugSearch,
  deleteSearchDocument,
  fetchSearchEvents,
  fetchSearchStats,
  listSearchDocuments,
  reindexSearchDocument,
  runSearch,
} from '@/lib/harness/search-client';
import type {
  SearchAdminStats,
  SearchDocumentRow,
  SearchEventRow,
  SearchHit,
  SearchQueryBody,
} from '@/lib/harness/search-types';

const MODES = ['hybrid', 'semantic', 'keyword'] as const;

function ScoreChip({ label, value }: { label: string; value: number | null }) {
  if (value === null || value === undefined) return null;
  return (
    <span className="glass-card-subtle rounded-md px-1.5 py-0.5 text-[10px] tabular-nums text-foreground/70">
      {label} {value.toFixed(3)}
    </span>
  );
}

function HitCard({ hit, rank }: { hit: SearchHit; rank: number }) {
  const locator = [hit.provenance.section, hit.provenance.page != null ? `p.${hit.provenance.page}` : null]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className="glass-card rounded-lg p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-foreground/50">#{rank}</span>
        <span className="font-medium">{hit.citation.label}</span>
        {locator && <span className="text-foreground/50">{locator}</span>}
        <span className="ml-auto flex gap-1">
          <ScoreChip label="score" value={hit.score} />
          <ScoreChip label="vec" value={hit.vectorScore} />
          <ScoreChip label="kw" value={hit.keywordScore} />
          <ScoreChip label="rerank" value={hit.rerankScore} />
        </span>
      </div>
      <p className="text-sm text-foreground/85">{hit.content.length > 480 ? `${hit.content.slice(0, 480)}…` : hit.content}</p>
      <div className="mt-1.5 flex flex-wrap gap-2 text-[10px] text-foreground/45">
        <span className="font-mono">{hit.provenance.documentId}</span>
        <span className="font-mono">{hit.citation.chunkId}</span>
        {hit.timestamps.publishedAt && <span>published {hit.timestamps.publishedAt}</span>}
        <span>{hit.provenance.trust}</span>
      </div>
    </div>
  );
}

export function SearchScreen() {
  const [stats, setStats] = useState<SearchAdminStats | null>(null);
  const [documents, setDocuments] = useState<SearchDocumentRow[]>([]);
  const [events, setEvents] = useState<SearchEventRow[]>([]);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<(typeof MODES)[number]>('hybrid');
  const [topK, setTopK] = useState(10);
  const [namespace, setNamespace] = useState('');
  const [asOf, setAsOf] = useState('');
  const [rerank, setRerank] = useState(true);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, d, e] = await Promise.all([
        fetchSearchStats(),
        listSearchDocuments({ limit: 25 }),
        fetchSearchEvents(25),
      ]);
      setStats(s);
      setDocuments(d.documents ?? []);
      setEvents(e.events ?? []);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const buildBody = useCallback((): SearchQueryBody => {
    const body: SearchQueryBody = { query, mode, top_k: topK, rerank };
    if (namespace.trim()) body.namespace = namespace.trim();
    if (asOf.trim()) body.as_of = asOf.trim();
    return body;
  }, [query, mode, topK, rerank, namespace, asOf]);

  const onSearch = useCallback(async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError(null);
    setTrace(null);
    try {
      const res = await runSearch(buildBody());
      setHits(res.result?.hits ?? []);
      setWarnings(res.result?.warnings ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }, [query, busy, buildBody]);

  const onDebug = useCallback(async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await debugSearch(buildBody());
      setTrace(res.trace ?? null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }, [query, busy, buildBody]);

  const onIndex = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await bulkIndexSearch();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const onReindex = useCallback(async (documentId: string) => {
    setBusy(true);
    try {
      await reindexSearchDocument(documentId, true);
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const onDelete = useCallback(async (documentId: string) => {
    setBusy(true);
    try {
      await deleteSearchDocument(documentId);
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const embedding = stats?.embedding;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <SearchIcon className="h-5 w-5 text-primary" />
        <h1 className="text-lg font-semibold">Search Intelligence</h1>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {embedding && (
            <span
              className={cn(
                'glass-card-subtle max-w-full truncate rounded-md px-2 py-1 text-xs',
                embedding.available ? 'text-emerald-400' : 'text-amber-400',
              )}
            >
              {embedding.available
                ? `Embeddings: ${embedding.provider}/${embedding.model} (${embedding.dimensions}d)`
                : `Keyword-only: ${embedding.reason}`}
            </span>
          )}
          <button className="glass-button rounded-md px-2 py-1 text-xs" onClick={() => void refresh()} disabled={busy}>
            <RefreshCw className="mr-1 inline h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card flex items-center gap-2 rounded-lg p-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4" /> {error}
        </div>
      )}

      {/* Query */}
      <div className="glass-card space-y-3 rounded-xl p-4">
        <div className="flex flex-wrap gap-2">
          <input
            className="glass-card-subtle min-w-[16rem] flex-1 rounded-md px-3 py-2 text-sm outline-none"
            placeholder="Search documents, research, memory, skills…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void onSearch();
            }}
          />
          <select
            className="glass-card-subtle rounded-md px-2 py-2 text-sm"
            value={mode}
            onChange={(e) => setMode(e.target.value as (typeof MODES)[number])}
          >
            {MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <input
            className="glass-card-subtle w-20 rounded-md px-2 py-2 text-sm"
            type="number"
            min={1}
            max={100}
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value) || 10)}
          />
          <input
            className="glass-card-subtle w-40 rounded-md px-2 py-2 text-sm"
            placeholder="namespace (optional)"
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
          />
          <input
            className="glass-card-subtle w-44 rounded-md px-2 py-2 text-sm"
            placeholder="as-of (ISO, optional)"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
          <button className="glass-button rounded-md px-3 py-2 text-sm" onClick={() => void onSearch()} disabled={busy}>
            Search
          </button>
          <button className="glass-button rounded-md px-3 py-2 text-sm" onClick={() => void onDebug()} disabled={busy}>
            Debug
          </button>
        </div>
        <label className="flex items-center gap-2 text-xs text-foreground/70">
          <input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} /> rerank
        </label>
      </div>

      {warnings.length > 0 && (
        <div className="glass-card-subtle rounded-lg p-3 text-xs text-amber-400">
          {warnings.map((w) => (
            <div key={w}>{w}</div>
          ))}
        </div>
      )}

      {hits && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-foreground/70">{hits.length} result(s)</h2>
          {hits.map((hit, i) => (
            <HitCard key={hit.id} hit={hit} rank={i + 1} />
          ))}
        </div>
      )}

      {trace && (
        <div className="glass-card rounded-xl p-4">
          <h2 className="mb-2 text-sm font-medium">Debug trace</h2>
          <pre className="max-h-80 overflow-auto text-[11px] text-foreground/70">{JSON.stringify(trace, null, 2)}</pre>
        </div>
      )}

      {/* Admin stats */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ['Documents', stats?.index.documents],
          ['Chunks', stats?.index.chunks],
          ['Vectors', stats?.index.vectors],
          ['Avg latency', stats ? `${stats.search.avgLatencyMs} ms` : undefined],
          ['Searches', stats?.search.recentQueries],
          ['Cache entries', stats?.embedding.cache.entries],
          ['Embedding failures', stats?.search.embeddingFailures],
          ['Vector models', stats?.index.vectorModels.length],
          ['ANN index', stats ? (stats.index.annBackend ? 'sqlite-vec' : 'brute-force') : undefined],
        ].map(([label, value]) => (
          <div key={String(label)} className="glass-card-subtle rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wide text-foreground/45">{label}</div>
            <div className="text-lg font-semibold tabular-nums">{value ?? '—'}</div>
          </div>
        ))}
      </div>

      <div className="glass-card rounded-xl p-4">
        <div className="mb-2 flex items-center gap-2">
          <Database className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-medium">Indexed documents</h2>
          <button className="glass-button ml-auto rounded-md px-2 py-1 text-xs" onClick={() => void onIndex()} disabled={busy}>
            Index all sources
          </button>
        </div>
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-foreground/45">
              <tr>
                <th className="py-1 pr-2">Title</th>
                <th className="py-1 pr-2">Namespace</th>
                <th className="py-1 pr-2">State</th>
                <th className="py-1 pr-2">Chunks</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.documentId} className="border-t border-white/5">
                  <td className="py-1 pr-2 font-mono">{d.title || d.documentId}</td>
                  <td className="py-1 pr-2">{d.namespace}</td>
                  <td className="py-1 pr-2">{d.state}</td>
                  <td className="py-1 pr-2 tabular-nums">{d.chunkCount}</td>
                  <td className="py-1 text-right">
                    <button className="glass-button rounded px-1.5 py-0.5" onClick={() => void onReindex(d.documentId)} disabled={busy}>
                      reindex
                    </button>
                    <button className="glass-button ml-1 rounded px-1.5 py-0.5" onClick={() => void onDelete(d.documentId)} disabled={busy}>
                      delete
                    </button>
                  </td>
                </tr>
              ))}
              {documents.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-3 text-center text-foreground/45">
                    No documents indexed. Use “Index all sources” to build the index from memory, evidence, documents and skills.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass-card rounded-xl p-4">
        <h2 className="mb-2 text-sm font-medium">Recent search events</h2>
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-foreground/45">
              <tr>
                <th className="py-1 pr-2">Kind</th>
                <th className="py-1 pr-2">Mode</th>
                <th className="py-1 pr-2">Latency</th>
                <th className="py-1 pr-2">Results</th>
                <th className="py-1">When</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-white/5">
                  <td className="py-1 pr-2 font-mono">{e.kind}</td>
                  <td className="py-1 pr-2">{e.mode ?? '—'}</td>
                  <td className="py-1 pr-2 tabular-nums">{e.latencyMs != null ? `${e.latencyMs.toFixed(0)} ms` : '—'}</td>
                  <td className="py-1 pr-2 tabular-nums">{e.results ?? '—'}</td>
                  <td className="py-1 text-foreground/50">{e.createdAt}</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-3 text-center text-foreground/45">
                    No searches recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

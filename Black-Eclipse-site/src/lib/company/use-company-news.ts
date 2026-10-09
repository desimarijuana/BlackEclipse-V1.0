'use client';

// ── Company news hook (Workstream E, Section G) ──────────────────────────────
// Reads the JDDS-backed /api/news feed for a ticker. The server already
// deduplicates syndicated coverage (clusters) and never fetches feeds live, so
// this is fast and consistent. Publication time comes from the item timestamp;
// we never invent an event date.

import { useCallback, useEffect, useState } from 'react';

export interface CompanyNewsItem {
  id: string;
  headline: string;
  summary: string | null;
  source: string;
  url: string | null;
  ticker: string | null;
  sentiment: string;
  category: string | null;
  publishedAt: string;
  sourceCount: number;
  clusterSources: string[];
}

export interface CompanyNewsState {
  items: CompanyNewsItem[];
  loading: boolean;
  error: string | null;
  lastIngestAt: string | null;
}

interface RawNews {
  id?: string;
  headline?: string;
  summary?: string | null;
  source?: string;
  url?: string | null;
  ticker?: string | null;
  sentiment?: string;
  category?: string | null;
  timestamp?: string;
  sourceCount?: number;
  clusterSources?: string[];
}

export function useCompanyNews(symbol: string, limit = 12) {
  const [state, setState] = useState<CompanyNewsState>({ items: [], loading: true, error: null, lastIngestAt: null });

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!symbol) {
      setState({ items: [], loading: false, error: null, lastIngestAt: null });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await fetch(`/api/news?ticker=${encodeURIComponent(symbol)}&limit=${limit}&cluster=1`, { signal });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'News unavailable');
      const items: CompanyNewsItem[] = (Array.isArray(data.news) ? data.news : []).map((n: RawNews) => ({
        id: String(n.id ?? Math.random()),
        headline: n.headline ?? '',
        summary: n.summary ?? null,
        source: n.source ?? 'Unknown',
        url: n.url ?? null,
        ticker: n.ticker ?? null,
        sentiment: n.sentiment ?? 'neutral',
        category: n.category ?? null,
        publishedAt: n.timestamp ?? new Date().toISOString(),
        sourceCount: n.sourceCount ?? 1,
        clusterSources: Array.isArray(n.clusterSources) ? n.clusterSources : [],
      }));
      setState({ items, loading: false, error: null, lastIngestAt: data.lastIngestAt ?? null });
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') return;
      setState({ items: [], loading: false, error: e instanceof Error ? e.message : 'News unavailable', lastIngestAt: null });
    }
  }, [symbol, limit]);

  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [load]);

  return { ...state, refresh: () => void load() };
}

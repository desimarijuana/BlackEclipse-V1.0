'use client';

// ── Company AI research hook (Workstream E, Sections B + K) ──────────────────
// Drives the EXISTING web-research engine through the front-door proxy. It
// starts a company-brief research run, polls status, then loads the run's
// evidence, sources, claims, citations and conflicts. It renders evidence the
// engine actually retrieved — it never synthesizes a brief client-side. Cached
// per symbol so reopening a stock reuses a recent run instead of re-searching.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  startResearch,
  getResearchStatus,
  getResearchRun,
  isTerminalState,
  type ResearchRunDetail,
  type ResearchStatusView,
} from '@/lib/research/research-client';

export interface CompanyResearchState {
  researchId: string | null;
  /** Engine run state: PLANNING | RUNNING | COMPLETED | PARTIAL | FAILED | CANCELLED. */
  state: string | null;
  running: boolean;
  error: string | null;
  startedAt: string | null;
  status: ResearchStatusView | null;
  detail: ResearchRunDetail | null;
}

const CACHE_KEY = 'eclipse_company_research_v1';
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;

interface CacheEntry { researchId: string; at: number }

function readCache(symbol: string): CacheEntry | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const map = JSON.parse(raw) as Record<string, CacheEntry>;
    const e = map[symbol];
    if (!e || Date.now() - e.at > CACHE_TTL_MS) return null;
    return e;
  } catch {
    return null;
  }
}

function writeCache(symbol: string, researchId: string) {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    const map = raw ? (JSON.parse(raw) as Record<string, CacheEntry>) : {};
    map[symbol] = { researchId, at: Date.now() };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(map));
  } catch { /* quota — best effort */ }
}

export function companyBriefQuestion(name: string, symbol: string, market: string): string {
  return (
    `Company intelligence brief for ${name} (${symbol}, ${market}): ` +
    `what the company does and how it generates revenue; major products, services and business segments; ` +
    `geographic exposure; the current CEO and key executives with appointment dates; recent material developments; ` +
    `the latest reported financial performance; valuation context; major business and financial risks; ` +
    `verifiable upcoming catalysts; the bull and bear case; and important unknowns or missing data.`
  );
}

export function useCompanyResearch(
  symbol: string,
  name: string,
  market: string,
  enabled = true,
) {
  const [state, setState] = useState<CompanyResearchState>({
    researchId: null, state: null, running: false, error: null, startedAt: null, status: null, detail: null,
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runIdRef = useRef(0);
  // name/market are read through refs so a late-arriving asset detail (which can
  // change the display name) never restarts an in-flight research run.
  const nameRef = useRef(name);
  const marketRef = useRef(market);
  nameRef.current = name;
  marketRef.current = market;

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    const detail = await getResearchRun(id);
    setState((s) => ({ ...s, detail, state: detail.run?.state ?? s.state }));
  }, []);

  const poll = useCallback((id: string, myRun: number) => {
    stopPoll();
    pollRef.current = setInterval(async () => {
      if (myRun !== runIdRef.current) { stopPoll(); return; }
      try {
        const status = await getResearchStatus(id);
        setState((s) => ({ ...s, status, state: status.state }));
        if (isTerminalState(status.state)) {
          stopPoll();
          await loadDetail(id);
          setState((s) => ({ ...s, running: false }));
        }
      } catch {
        // A transient poll failure is not fatal; keep polling until terminal/timeout.
      }
    }, 2500);
  }, [stopPoll, loadDetail]);

  const begin = useCallback(async (force: boolean) => {
    if (!symbol || !enabled) return;
    const myRun = ++runIdRef.current;
    stopPoll();
    setState({ researchId: null, state: null, running: true, error: null, startedAt: null, status: null, detail: null });

    // Reuse a cached, recent run unless the user asked to refresh.
    if (!force) {
      const cached = readCache(symbol);
      if (cached) {
        try {
          const status = await getResearchStatus(cached.researchId);
          if (myRun !== runIdRef.current) return;
          setState((s) => ({ ...s, researchId: cached.researchId, status, state: status.state, startedAt: new Date(cached.at).toISOString() }));
          if (isTerminalState(status.state)) {
            await loadDetail(cached.researchId);
            setState((s) => ({ ...s, running: false }));
          } else {
            poll(cached.researchId, myRun);
          }
          return;
        } catch { /* cache stale / run gone — fall through to a new run */ }
      }
    }

    try {
      const { researchId } = await startResearch({
        question: companyBriefQuestion(nameRef.current, symbol, marketRef.current),
        depth: 'standard',
        crossValidationRequired: true,
      });
      if (myRun !== runIdRef.current) return;
      writeCache(symbol, researchId);
      setState((s) => ({ ...s, researchId, running: true, state: 'PLANNING', startedAt: new Date().toISOString() }));
      poll(researchId, myRun);
    } catch (e) {
      if (myRun !== runIdRef.current) return;
      setState((s) => ({ ...s, running: false, error: e instanceof Error ? e.message : 'Research runtime unavailable' }));
    }
  }, [symbol, enabled, stopPoll, loadDetail, poll]);

  useEffect(() => {
    void begin(false);
    return () => { runIdRef.current += 1; stopPoll(); };
  }, [begin, stopPoll]);

  return {
    ...state,
    refresh: () => void begin(true),
  };
}

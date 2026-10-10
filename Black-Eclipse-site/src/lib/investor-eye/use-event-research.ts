'use client';

// ── Investor Eye — event research hook ───────────────────────────────────────
// Drives the EXISTING shared web-research engine (Python) through the
// `/api/research/*` front door — the same engine the Research screen and the
// company dossier use. It starts a run for one event, polls, then loads the
// run's evidence, sources, claims, citations and conflicts. It never
// synthesizes findings client-side; it renders what the engine retrieved.
//
// LAZY by design: an event dossier does NOT auto-start a multi-minute web
// research run on open. The user asks for it, and the run is cached per event
// so reopening reuses a recent result.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  startResearch, getResearchStatus, getResearchRun, isTerminalState,
  type ResearchRunDetail, type ResearchStatusView,
} from '@/lib/research/research-client';

export interface EventResearchState {
  researchId: string | null;
  /** PLANNING | RUNNING | COMPLETED | PARTIAL | FAILED | CANCELLED. */
  state: string | null;
  running: boolean;
  error: string | null;
  startedAt: string | null;
  status: ResearchStatusView | null;
  detail: ResearchRunDetail | null;
}

const CACHE_KEY = 'eclipse_event_research_v1';
const CACHE_TTL_MS = 60 * 60 * 1000;

interface CacheEntry { researchId: string; at: number }

function readCache(key: string): CacheEntry | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const map = JSON.parse(raw) as Record<string, CacheEntry>;
    const e = map[key];
    if (!e || Date.now() - e.at > CACHE_TTL_MS) return null;
    return e;
  } catch {
    return null;
  }
}

function writeCache(key: string, researchId: string) {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    const map = raw ? (JSON.parse(raw) as Record<string, CacheEntry>) : {};
    map[key] = { researchId, at: Date.now() };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(map));
  } catch { /* quota — best effort */ }
}

/** Heuristic: the runtime-unavailable error is a setup gap, not a research bug. */
function isRuntimeGap(message: string | null | undefined): boolean {
  if (!message) return false;
  const m = message.toLowerCase();
  return m.includes('runtime') || m.includes('unavailable') || m.includes('setup:python');
}

export function useEventResearch(dedupKey: string | undefined) {
  const [state, setState] = useState<EventResearchState>({
    researchId: null, state: null, running: false, error: null, startedAt: null, status: null, detail: null,
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runIdRef = useRef(0);

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
      } catch { /* transient poll failure — keep polling until terminal/timeout */ }
    }, 2500);
  }, [stopPoll, loadDetail]);

  const begin = useCallback(async (question: string, force: boolean) => {
    if (!dedupKey || !question) return;
    const myRun = ++runIdRef.current;
    stopPoll();
    setState({ researchId: null, state: null, running: true, error: null, startedAt: null, status: null, detail: null });

    // Reuse a cached, recent run unless the user asked to refresh.
    if (!force) {
      const cached = readCache(dedupKey);
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
        } catch { /* stale / gone — fall through to a new run */ }
      }
    }

    try {
      const { researchId } = await startResearch({
        question,
        depth: 'standard',
        crossValidationRequired: true,
      });
      if (myRun !== runIdRef.current) return;
      writeCache(dedupKey, researchId);
      setState((s) => ({ ...s, researchId, running: true, state: 'PLANNING', startedAt: new Date().toISOString() }));
      poll(researchId, myRun);
    } catch (e) {
      if (myRun !== runIdRef.current) return;
      setState((s) => ({ ...s, running: false, error: e instanceof Error ? e.message : 'Research runtime unavailable' }));
    }
  }, [dedupKey, stopPoll, loadDetail, poll]);

  // A run belongs to one event: drop it when the selection changes.
  useEffect(() => {
    runIdRef.current += 1;
    stopPoll();
    setState({ researchId: null, state: null, running: false, error: null, startedAt: null, status: null, detail: null });
    return () => { stopPoll(); };
  }, [dedupKey, stopPoll]);

  return {
    ...state,
    runtimeGap: isRuntimeGap(state.error),
    run: (question: string) => void begin(question, true),
    reuse: (question: string) => void begin(question, false),
  };
}

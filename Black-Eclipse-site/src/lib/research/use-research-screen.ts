'use client';

// ── Research screen data hook ────────────────────────────────────────────────
// One reactive source of truth for the dedicated research screen: the run list,
// the selected run's detail, and start/cancel/refresh actions. It polls the
// selected run's status while it is non-terminal so a background run (started
// here or in chat via research_start) shows live progress. It never fabricates
// a run or an answer — a failed load surfaces an honest error.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  cancelResearch,
  getResearchRun,
  getResearchStatus,
  isTerminalState,
  listResearchRuns,
  startResearch,
  type ResearchRunDetail,
  type ResearchRunRow,
  type ResearchStatusView,
  type StartResearchInput,
} from './research-client';

const POLL_MS = 2500;

export interface ResearchScreenState {
  runs: ResearchRunRow[];
  selectedId: string | null;
  detail: ResearchRunDetail | null;
  status: ResearchStatusView | null;
  loadingList: boolean;
  loadingDetail: boolean;
  error: string | null;
  select: (researchId: string) => void;
  refresh: () => void;
  start: (input: StartResearchInput) => Promise<string | null>;
  cancel: (researchId: string) => Promise<void>;
}

export function useResearchScreen(): ResearchScreenState {
  const [runs, setRuns] = useState<ResearchRunRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ResearchRunDetail | null>(null);
  const [status, setStatus] = useState<ResearchStatusView | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selectedId;

  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      const rows = await listResearchRuns(60);
      setRuns(rows);
      setError(null);
      setSelectedId((cur) => cur ?? rows[0]?.researchId ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load research runs');
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList, tick]);

  const loadDetail = useCallback(async (researchId: string) => {
    setLoadingDetail(true);
    try {
      const [d, s] = await Promise.all([
        getResearchRun(researchId),
        getResearchStatus(researchId).catch(() => null),
      ]);
      setDetail(d);
      setStatus(s);
      setError(null);
    } catch (err) {
      setDetail(null);
      setError(err instanceof Error ? err.message : 'Could not load the run');
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setStatus(null);
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  // Poll while the selected run is non-terminal so progress is live.
  useEffect(() => {
    if (!selectedId) return;
    const state = status?.state ?? detail?.run.state;
    if (isTerminalState(state)) return;
    const id = window.setInterval(() => {
      if (selectedRef.current !== selectedId) return;
      void getResearchStatus(selectedId)
        .then((s) => setStatus(s))
        .catch(() => {
          /* keep the last known status; a transient poll failure is not an error */
        });
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [selectedId, status?.state, detail?.run.state]);

  // Refresh the detail once a run reaches a terminal state (to pick up evidence).
  useEffect(() => {
    if (selectedId && isTerminalState(status?.state)) {
      void getResearchRun(selectedId)
        .then((d) => setDetail(d))
        .catch(() => {
          /* detail stays as-is */
        });
    }
  }, [selectedId, status?.state]);

  const start = useCallback(
    async (input: StartResearchInput): Promise<string | null> => {
      try {
        const { researchId } = await startResearch(input);
        setSelectedId(researchId);
        await loadList();
        return researchId;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not start research');
        return null;
      }
    },
    [loadList],
  );

  const cancel = useCallback(
    async (researchId: string) => {
      try {
        await cancelResearch(researchId);
        await loadList();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not cancel the run');
      }
    },
    [loadList],
  );

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  return useMemo(
    () => ({
      runs,
      selectedId,
      detail,
      status,
      loadingList,
      loadingDetail,
      error,
      select: setSelectedId,
      refresh,
      start,
      cancel,
    }),
    [runs, selectedId, detail, status, loadingList, loadingDetail, error, refresh, start, cancel],
  );
}

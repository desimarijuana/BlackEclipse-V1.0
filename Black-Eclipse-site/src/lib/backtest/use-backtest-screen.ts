'use client';

// ── Backtest screen state ────────────────────────────────────────────────────
// Owns the Backtest surface's data: strategies, the last result, and stored
// experiments. Every value comes from the Python Quant Engine via
// `backtestClient`; nothing is simulated. The screen renders exactly what the
// runtime returns (including warnings and the capability matrix).

import { useCallback, useEffect, useState } from 'react';
import {
  backtestClient,
  type BacktestResult,
  type ExperimentSummary,
  type ResearchRequest,
  type ResearchResult,
  type RunBacktestInput,
  type StrategyRecord,
  type StrategySummary,
} from './backtest-client';

export type ResearchKind =
  | 'optimize' | 'walkForward' | 'monteCarlo' | 'sensitivity' | 'robustness';

export interface BacktestScreenState {
  strategies: StrategySummary[];
  experiments: ExperimentSummary[];
  result: BacktestResult | null;
  research: ResearchResult | null;
  selectedId: string | null;
  selected: StrategyRecord | null;
  capabilities: Record<string, string>;
  loading: boolean;
  running: boolean;
  error: string | null;
  notice: string | null;
}

const initial: BacktestScreenState = {
  strategies: [],
  experiments: [],
  result: null,
  research: null,
  selectedId: null,
  selected: null,
  capabilities: {},
  loading: true,
  running: false,
  error: null,
  notice: null,
};

export function useBacktestScreen() {
  const [state, setState] = useState<BacktestScreenState>(initial);

  const refresh = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const [strategies, experiments, caps] = await Promise.all([
        backtestClient.listStrategies(),
        backtestClient.listExperiments(undefined, 25),
        backtestClient.capabilities().catch(() => ({ available: false, capability: {} })),
      ]);
      setState((s) => ({
        ...s,
        strategies,
        experiments,
        capabilities: caps.capability,
        loading: false,
      }));
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : 'load failed' }));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectStrategy = useCallback(async (id: string | null) => {
    if (!id) {
      setState((s) => ({ ...s, selectedId: null, selected: null }));
      return;
    }
    setState((s) => ({ ...s, selectedId: id, error: null }));
    try {
      const selected = await backtestClient.getStrategy(id);
      setState((s) => ({ ...s, selected }));
    } catch (err) {
      setState((s) => ({ ...s, error: err instanceof Error ? err.message : 'load strategy failed' }));
    }
  }, []);

  const run = useCallback(async (input: RunBacktestInput) => {
    setState((s) => ({ ...s, running: true, error: null, notice: null }));
    try {
      const result = await backtestClient.runBacktest(input);
      setState((s) => ({ ...s, running: false, result }));
      void refresh();
      return result;
    } catch (err) {
      setState((s) => ({ ...s, running: false, error: err instanceof Error ? err.message : 'run failed' }));
      return null;
    }
  }, [refresh]);

  const runResearch = useCallback(async (kind: ResearchKind, body: ResearchRequest) => {
    setState((s) => ({ ...s, running: true, error: null, research: null }));
    const call = {
      optimize: backtestClient.optimize,
      walkForward: backtestClient.walkForward,
      monteCarlo: backtestClient.monteCarlo,
      sensitivity: backtestClient.sensitivity,
      robustness: backtestClient.robustness,
    }[kind];
    try {
      const research = await call(body);
      setState((s) => ({ ...s, running: false, research }));
      void refresh();
      return research;
    } catch (err) {
      setState((s) => ({ ...s, running: false, error: err instanceof Error ? err.message : 'research failed' }));
      return null;
    }
  }, [refresh]);

  const openExperiment = useCallback(async (id: string) => {
    setState((s) => ({ ...s, running: true, error: null }));
    try {
      const result = await backtestClient.getArtifact(id);
      setState((s) => ({ ...s, running: false, result }));
    } catch (err) {
      setState((s) => ({ ...s, running: false, error: err instanceof Error ? err.message : 'open failed' }));
    }
  }, []);

  const removeExperiment = useCallback(async (id: string) => {
    try {
      await backtestClient.deleteExperiment(id);
      setState((s) => ({ ...s, experiments: s.experiments.filter((e) => e.id !== id) }));
    } catch (err) {
      setState((s) => ({ ...s, error: err instanceof Error ? err.message : 'delete failed' }));
    }
  }, []);

  const saveStrategy = useCallback(async (strategy: Record<string, unknown>, description?: string) => {
    const { strategy: saved } = await backtestClient.createStrategy(strategy, description);
    await refresh();
    await selectStrategy(saved.id);
    return saved;
  }, [refresh, selectStrategy]);

  const validate = useCallback(async (strategy: Record<string, unknown>) => {
    return backtestClient.validateStrategy(strategy);
  }, []);

  return {
    ...state, refresh, selectStrategy, run, runResearch, openExperiment,
    removeExperiment, saveStrategy, validate,
  };
}

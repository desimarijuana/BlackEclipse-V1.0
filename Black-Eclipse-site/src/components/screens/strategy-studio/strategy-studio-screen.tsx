'use client';

// ── Strategy Studio ─────────────────────────────────────────────────────────
// A guided workspace over the deterministic Python quant engine:
//   Idea → Spec → Test → Prove → Track.
//
// The studio authors NOTHING numeric: the model drafts a spec, the engine
// computes every fill, metric and drawdown, and a missing measurement is shown
// as missing. The workspace persists across reloads and every run is saved.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBacktestScreen } from '@/lib/backtest/use-backtest-screen';
import { copyText } from '@/lib/desktop/clipboard';
import { EdgeReportView } from '@/components/screens/backtest/shared/edge-report-view';
import {
  backtestClient,
  type EdgeReport,
  type ExperimentSummary,
  type PaperRunRecord,
  type StrategyRecord,
} from '@/lib/backtest/backtest-client';
import { STRATEGY_TEMPLATES } from '@/lib/strategy-studio/templates';
import { computePaperWindow, defaultPaperMode, type PaperMode } from '@/lib/strategy-studio/paper-window';
import {
  applyDeepLink,
  browserStorage,
  clearWorkspace,
  defaultWorkspace,
  loadWorkspace,
  saveWorkspace,
  workspaceQuery,
} from '@/lib/strategy-studio/workspace';
import { splitSymbols } from '@/lib/strategy-studio/preflight';
import { StudioHeader } from './studio-header';
import { StudioSidebar } from './studio-sidebar';
import { StudioAlerts } from './studio-alerts';
import { ExperimentHistory } from './experiment-history';
import { PortfolioPanel } from './portfolio-panel';
import { StageRail, computeCompleted, computeStudioStage } from './stage-rail';
import { NAVIGATE_EVENT, consumeStrategyTarget, type NavigateIntent } from '@/lib/navigation/app-nav';
import { CompactSummary } from './compact-summary';
import { EmptyResults, ResultPanels } from './result-panels';
import { ResearchStudio } from './research-studio';
import { SpecCard, type Issue } from './spec-card';
import { type ThesisInputs } from './thesis-panel';
import { PaperPanel, type PaperRun } from './paper-panel';
import { VersionPanel } from './version-panel';
import { PublishButton } from './publish-button';
import { ShareCard } from './share-card';
import { MethodDiscoveryPanel } from './method-discovery-panel';
import { ResearchIntelligencePanel } from './research-intelligence-panel';
import { LiveStrategyPanel } from './live-strategy-panel';
import { SystemHealthPanel } from './system-health-panel';
import { ResearchJournalPanel } from './research-journal-panel';
import { PortfolioStressLab } from './portfolio-stress-lab';
import { ManifestPanel } from '@/components/screens/backtest/shared/manifest-panel';
import { paperHealth } from '@/lib/strategy-studio/paper-health';
import { buildShareCardInput } from '@/lib/strategy-studio/share-card';
import { ShieldCheck } from '@/lib/icons';

const SAMPLE_PROMPT =
  'Buy BTC when the 50-day EMA crosses above the 200-day EMA, exit on the reverse cross, risk 1% per trade with a 2 ATR stop and a 3R target. Long only, daily bars, realistic fees.';

function identityOf(spec: Record<string, unknown> | null): { id: string; name: string } {
  const block = (spec?.strategy ?? {}) as Record<string, unknown>;
  return {
    id: String(block.id ?? spec?.id ?? ''),
    name: String(block.name ?? spec?.name ?? 'Untitled strategy'),
  };
}

async function postQuant<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(`/api/backtest${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = (await response.json().catch(() => ({}))) as {
    error?: unknown;
    detail?: unknown;
  };
  if (!response.ok) {
    const detail = payload.error ?? payload.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : typeof payload.detail === 'object' && payload.detail && 'message' in payload.detail
          ? String((payload.detail as { message?: unknown }).message)
          : `request failed (${response.status})`;
    throw new Error(message);
  }
  return payload as T;
}

export function StrategyStudioScreen() {
  const bt = useBacktestScreen();
  const [prompt, setPrompt] = useState(SAMPLE_PROMPT);
  const [symbol, setSymbol] = useState('BTC-USD');
  const [timeframe, setTimeframe] = useState('1d');
  const [start, setStart] = useState(() => defaultWorkspace().start);
  const [end, setEnd] = useState(() => defaultWorkspace().end);
  const [capital, setCapital] = useState(100_000);
  const [editor, setEditor] = useState('');
  const [issues, setIssues] = useState<Issue[]>([]);
  const [saved, setSaved] = useState<StrategyRecord | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingStrategy, setLoadingStrategy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [edge, setEdge] = useState<EdgeReport | null>(null);
  const [grading, setGrading] = useState(false);
  const [paper, setPaper] = useState<PaperRun | null>(null);
  const [paperApproved, setPaperApproved] = useState(false);
  const [paperBusy, setPaperBusy] = useState(false);
  const [paperMode, setPaperMode] = useState<PaperMode>('forward');
  const [paperModeChosen, setPaperModeChosen] = useState(false);
  const [paperRuns, setPaperRuns] = useState<PaperRunRecord[]>([]);
  const [paperExperiments, setPaperExperiments] = useState<Record<string, ExperimentSummary>>({});
  const [activeExperimentId, setActiveExperimentId] = useState<string | null>(null);
  const [strategyHistory, setStrategyHistory] = useState<ExperimentSummary[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  const boot = useRef<{ strategyId: string | null; experimentId: string | null; replaceEditor: boolean }>({
    strategyId: null,
    experimentId: null,
    replaceEditor: true,
  });

  const result = bt.result;
  const spec = useMemo<Record<string, unknown> | null>(() => {
    if (!editor.trim()) return null;
    try {
      const parsed = JSON.parse(editor);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }, [editor]);
  const identity = identityOf(spec);

  // ── Hydrate the workspace (storage + deep link) once, on mount ────────────
  useEffect(() => {
    const stored = loadWorkspace(browserStorage()) ?? defaultWorkspace();
    const linked = applyDeepLink(stored, typeof window === 'undefined' ? '' : window.location.search);
    setPrompt(linked.prompt || SAMPLE_PROMPT);
    setEditor(linked.editor);
    setSymbol(linked.symbol);
    setTimeframe(linked.timeframe);
    setStart(linked.start);
    setEnd(linked.end);
    setCapital(linked.capital);
    boot.current = {
      strategyId: linked.strategyId,
      experimentId: linked.experimentId,
      // A stored draft is the user's unfinished work: never clobber it.
      replaceEditor: !linked.editor.trim() || linked.wantsStrategy,
    };
    setRestoring(Boolean(linked.strategyId || linked.experimentId));
    setHydrated(true);
  }, []);

  const loadHistory = useCallback(async (strategyId: string | null) => {
    try {
      setStrategyHistory(await backtestClient.listExperiments(strategyId ?? undefined, 25));
    } catch {
      setStrategyHistory([]);
    }
  }, []);

  const loadPaperTrack = useCallback(async (strategyId: string) => {
    try {
      const [runs, experiments] = await Promise.all([
        backtestClient.listPaperRuns(strategyId),
        backtestClient.listExperiments(strategyId, 50),
      ]);
      setPaperRuns(runs);
      setPaperExperiments(Object.fromEntries(experiments.map((item) => [item.id, item])));
    } catch {
      setPaperRuns([]);
      setPaperExperiments({});
    }
  }, []);

  const openStrategy = useCallback(
    async (id: string, options?: { replaceEditor?: boolean; silent?: boolean }) => {
      setLoadingStrategy(true);
      if (!options?.silent) setError(null);
      try {
        const record = await backtestClient.getStrategy(id);
        setSaved(record);
        if (options?.replaceEditor ?? true) {
          setEditor(JSON.stringify(record.spec, null, 2));
          const symbols = (record.spec.universe as { symbols?: string[] } | undefined)?.symbols ?? [];
          if (symbols.length) setSymbol(symbols.join(', '));
          const primary = (record.spec.timeframes as { primary?: string } | undefined)?.primary;
          if (primary) setTimeframe(primary);
          // The shown result belongs to the strategy we are leaving.
          bt.clearResult();
        }
        setIssues([]);
        setEdge(null);
        setPaper(null);
        setNotice(`Opened ${record.name || record.id} · v${record.version ?? record.latestVersion}.`);
        void loadHistory(record.id);
        void loadPaperTrack(record.id);
      } catch (err) {
        setSaved(null);
        setStrategyHistory([]);
        setPaperRuns([]);
        setPaperExperiments({});
        if (options?.silent) {
          setNotice('The last strategy could not be reopened. Your draft is still here.');
        } else {
          setError(err instanceof Error ? err.message : 'could not open the strategy');
        }
      } finally {
        setLoadingStrategy(false);
      }
    },
    [bt, loadHistory, loadPaperTrack],
  );

  useEffect(() => {
    if (!hydrated) return;
    const { strategyId, experimentId, replaceEditor } = boot.current;
    const restore = async () => {
      try {
        if (strategyId) await openStrategy(strategyId, { replaceEditor, silent: true });
        if (experimentId) {
          setActiveExperimentId(experimentId);
          await bt.openExperiment(experimentId);
        }
      } finally {
        setRestoring(false);
      }
    };
    if (strategyId || experimentId) void restore();
    else setRestoring(false);
    // Boot only: afterwards the screens drive their own loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated]);

  // A deep link from another surface ("Open in Strategy Studio"). On first
  // visit the intent is consumed on mount; an already-mounted tab listens.
  useEffect(() => {
    if (!hydrated) return;
    const pending = consumeStrategyTarget();
    if (pending) void openStrategy(pending, { replaceEditor: true, silent: true });
    const onNavigate = (event: Event) => {
      const detail = (event as CustomEvent<NavigateIntent>).detail;
      if (detail?.tab !== 'strategy-studio' || !detail.strategy) return;
      void openStrategy(detail.strategy, { replaceEditor: true, silent: true });
    };
    window.addEventListener(NAVIGATE_EVENT, onNavigate);
    return () => window.removeEventListener(NAVIGATE_EVENT, onNavigate);
  }, [hydrated, openStrategy]);

  // ── Persist the workspace (debounced) ────────────────────────────────────
  useEffect(() => {    if (!hydrated || restoring) return;
    const timer = setTimeout(() => {
      saveWorkspace(
        {
          schema: 1,
          prompt,
          editor,
          strategyId: saved?.id ?? null,
          strategyName: saved?.name ?? null,
          symbol,
          timeframe,
          start,
          end,
          capital,
          experimentId: activeExperimentId,
          updatedAt: new Date().toISOString(),
        },
        browserStorage(),
      );
    }, 500);
    return () => clearTimeout(timer);
  }, [hydrated, restoring, prompt, editor, saved, symbol, timeframe, start, end, capital, activeExperimentId]);

  // ── Keep the address bar shareable ───────────────────────────────────────
  useEffect(() => {
    if (!hydrated || restoring || typeof window === 'undefined') return;
    const query = workspaceQuery({ strategyId: saved?.id ?? null, experimentId: activeExperimentId });
    const next = `${window.location.pathname}?${query}`;
    if (`${window.location.pathname}${window.location.search}` !== next) {
      window.history.replaceState(window.history.state, '', next);
    }
  }, [hydrated, restoring, saved?.id, activeExperimentId]);

  // ── Validate as you type (silent; the button still reports) ──────────────
  useEffect(() => {
    if (!hydrated) return;
    if (!spec) {
      // Invalid or empty JSON: do not keep a previous spec's findings.
      setIssues([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      backtestClient
        .validateStrategy(spec)
        .then((validation) => {
          if (!cancelled) setIssues(validation.issues ?? []);
        })
        .catch(() => {
          /* validation is a convenience here; the button surfaces real errors */
        });
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [spec, hydrated]);

  const copyPath = useCallback(async (path: string) => {
    // A refused copy leaves the path visible, so no error surface is needed.
    if (!(await copyText(path))) return;
    setCopiedPath(path);
    setTimeout(() => setCopiedPath(null), 1500);
  }, []);

  const copyShareLink = useCallback(async () => {
    if (!saved || typeof window === 'undefined') return;
    const query = workspaceQuery({ strategyId: saved.id, experimentId: activeExperimentId });
    const href = `${window.location.origin}${window.location.pathname}?${query}`;
    if (!(await copyText(href))) {
      setError('The link could not be copied to the clipboard.');
      return;
    }
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 1500);
    setNotice('Share link copied. It reopens this strategy and experiment in the studio.');
  }, [activeExperimentId, saved]);

  const draftWithAi = useCallback(async () => {
    setDrafting(true);
    setError(null);
    setNotice(null);
    setIssues([]);
    setEdge(null);
    setPaper(null);
    try {
      const response = await fetch('/api/agent/strategy-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, symbol, timeframe }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        spec?: Record<string, unknown>;
        error?: string;
      };
      if (!response.ok || !payload.spec) {
        throw new Error(payload.error || `draft failed (${response.status})`);
      }
      setEditor(JSON.stringify(payload.spec, null, 2));
      const validation = await bt.validate(payload.spec);
      setIssues(validation.issues ?? []);
      const symbols = ((payload.spec.universe as { symbols?: string[] } | undefined)?.symbols ?? []) as string[];
      if (symbols[0]) setSymbol(symbols[0]);
      setNotice(validation.valid ? 'Draft ready. Review the spec, then save and run.' : 'Draft ready, but it needs fixes.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'draft failed');
    } finally {
      setDrafting(false);
    }
  }, [bt, prompt, symbol, timeframe]);

  const validate = useCallback(async () => {
    if (!spec) {
      setError('The spec editor does not contain a JSON object.');
      return false;
    }
    setError(null);
    try {
      const validation = await bt.validate(spec);
      setIssues(validation.issues ?? []);
      setNotice(validation.valid ? 'Spec is valid.' : 'Fix the errors below.');
      return validation.valid;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'validation failed');
      return false;
    }
  }, [bt, spec]);

  const saveAndRun = useCallback(async () => {
    if (!spec) {
      setError('The spec editor does not contain a JSON object.');
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    setPaper(null);
    setEdge(null);
    try {
      const validation = await bt.validate(spec);
      setIssues(validation.issues ?? []);
      if (!validation.valid) {
        setNotice('Fix the validation errors before running.');
        return;
      }
      // The record's description is the strategy's own description, never its name.
      const description =
        String(((spec.strategy as Record<string, unknown> | undefined)?.description as string | undefined) ?? '').trim() ||
        undefined;
      const record = await bt.saveStrategy(spec, description);
      setSaved(record);
      const symbols = splitSymbols(symbol);
      const run = await bt.run({
        strategyId: record.id,
        symbols: symbols.length ? symbols : undefined,
        start,
        end,
        initialCapital: capital,
        save: true,
        background: true,
      });
      if (run?.experimentId) setActiveExperimentId(run.experimentId);
      void loadHistory(record.id);
      void loadPaperTrack(record.id);
      setNotice(
        run?.experimentId
          ? `Backtest complete. Experiment ${run.experimentId} is saved.`
          : 'Backtest complete. Results are shown below.',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  }, [bt, capital, end, loadHistory, loadPaperTrack, spec, start, symbol]);

  const newStrategy = useCallback(() => {
    setPrompt('');
    setEditor('');
    setSaved(null);
    setIssues([]);
    setEdge(null);
    setPaper(null);
    setPaperApproved(false);
    setActiveExperimentId(null);
    setStrategyHistory([]);
    setPaperRuns([]);
    setPaperExperiments({});
    clearWorkspace(browserStorage());
    bt.clearResult();
    setError(null);
    setNotice('Blank workspace. Describe a thesis, or paste a spec.');
  }, [bt]);

  const applyTemplate = useCallback(
    (id: string) => {
      const template = STRATEGY_TEMPLATES.find((item) => item.id === id);
      if (!template) return;
      const spec = template.spec;
      const strategy = (spec.strategy ?? {}) as { description?: string };
      const symbols = ((spec.universe as { symbols?: string[] } | undefined)?.symbols ?? []);
      const primary = (spec.timeframes as { primary?: string } | undefined)?.primary;
      setEditor(JSON.stringify(spec, null, 2));
      setPrompt(strategy.description ?? template.tagline);
      if (symbols.length) setSymbol(symbols.join(', '));
      if (primary) setTimeframe(primary);
      setSaved(null);
      setIssues([]);
      setEdge(null);
      setPaper(null);
      setPaperApproved(false);
      setActiveExperimentId(null);
      setStrategyHistory([]);
      setPaperRuns([]);
      setPaperExperiments({});
      bt.clearResult();
      setError(null);
      setNotice(`${template.name} loaded. Review it, then save and run. It is an example, not a recommendation.`);
    },
    [bt],
  );

  const openExperiment = useCallback(
    (id: string) => {
      setActiveExperimentId(id);
      setEdge(null);
      setNotice(`Opened experiment ${id}.`);
      void bt.openExperiment(id);
    },
    [bt],
  );

  const removeExperiment = useCallback(
    async (id: string) => {
      await bt.removeExperiment(id);
      if (activeExperimentId === id) setActiveExperimentId(null);
      if (saved) void loadHistory(saved.id);
    },
    [activeExperimentId, bt, loadHistory, saved],
  );

  const gradeEdge = useCallback(async () => {
    const experimentId = result?.experimentId ?? activeExperimentId;
    if (!experimentId) {
      setError('Run the strategy (or open a saved experiment) before grading its edge.');
      return;
    }
    setGrading(true);
    setError(null);
    try {
      const report = await backtestClient.edgeReport({ experimentId });
      setEdge(report);
      if (report.verdict.flags?.length) {
        setNotice(
          `Edge grade ${report.verdict.grade}. ${report.verdict.flags.length} flag(s) — see the report below.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'edge report failed');
    } finally {
      setGrading(false);
    }
  }, [activeExperimentId, result]);

  const paperModeEffective: PaperMode = paperModeChosen ? paperMode : defaultPaperMode(end);
  const paperWindow = computePaperWindow({
    mode: paperModeEffective,
    researchStart: start,
    researchEnd: end,
  });

  const promote = useCallback(async () => {
    if (!saved || !result) return;
    if (!paperApproved) {
      setError('Confirm the paper approval checkbox first.');
      return;
    }
    if (!paperWindow.available) {
      setError(paperWindow.reason ?? 'No paper window is available.');
      return;
    }
    setPaperBusy(true);
    setError(null);
    try {
      const version = String(saved.version ?? saved.latestVersion ?? '1.0.0');
      const approval = await postQuant<{ approval: { id: string } }>(
        `/strategies/${encodeURIComponent(saved.id)}/approvals`,
        { version, actor: 'strategy-studio', note: 'Strategy Studio approval request' },
      );
      // A separate actor records the decision, so the approval trail shows two
      // parties rather than an approval that approves itself.
      await postQuant(`/approvals/${encodeURIComponent(approval.approval.id)}/decide`, {
        approve: true,
        actor: 'operator',
        note: 'Approved for paper shadow run (single-operator workspace)',
      });
      const deployment = await postQuant<{ deployment: { id: string } }>(
        `/strategies/${encodeURIComponent(saved.id)}/deployments`,
        { version, mode: 'paper', note: `Strategy Studio paper deployment (${paperWindow.mode})` },
      );
      const paperRun = await postQuant<{ paperRun: PaperRun }>(
        `/deployments/${encodeURIComponent(deployment.deployment.id)}/paper-runs`,
        {
          symbols: splitSymbols(symbol),
          start: paperWindow.start,
          end: paperWindow.end,
          initialCapital: capital,
          randomSeed: 42,
        },
      );
      setPaper(paperRun.paperRun);
      void loadPaperTrack(saved.id);
      setNotice(
        `Paper ${paperWindow.mode} run recorded over ${paperWindow.start} → ${paperWindow.end}. No live orders were placed.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'paper deployment failed');
    } finally {
      setPaperBusy(false);
    }
  }, [
    capital,
    loadPaperTrack,
    paperApproved,
    paperWindow.available,
    paperWindow.end,
    paperWindow.mode,
    paperWindow.reason,
    paperWindow.start,
    result,
    saved,
    symbol,
  ]);

  const busy = bt.running || drafting || saving || paperBusy || loadingStrategy;
  const progress = bt.progress;
  const disabled = busy || !prompt.trim();

  const thesis: ThesisInputs = { prompt, symbol, timeframe, start, end, capital };
  const updateThesis = useCallback((patch: Partial<ThesisInputs>) => {
    if (patch.prompt !== undefined) setPrompt(patch.prompt);
    if (patch.symbol !== undefined) setSymbol(patch.symbol);
    if (patch.timeframe !== undefined) setTimeframe(patch.timeframe);
    if (patch.start !== undefined) setStart(patch.start);
    if (patch.end !== undefined) setEnd(patch.end);
    if (patch.capital !== undefined) setCapital(patch.capital);
  }, []);

  const stage = computeStudioStage({
    paper: Boolean(paper),
    proved: Boolean(edge || bt.research),
    result: Boolean(result),
    specValid: Boolean(spec) && issues.length === 0,
  });

  const completed = computeCompleted({
    hasPrompt: Boolean(prompt.trim()),
    specValid: Boolean(spec) && issues.length === 0,
    result: Boolean(result),
    proved: Boolean(edge || bt.research),
    paper: Boolean(paper),
  });

  const history = saved ? strategyHistory : bt.experiments;

  // Drift is measured against the latest BACKTEST, never against another paper run.
  const researchBaseline = useMemo(() => {
    const backtests = strategyHistory.filter(
      (item) => item.kind === 'backtest' || item.kind === 'event_driven_backtest',
    );
    return backtests[0]?.metrics ?? result?.metrics ?? null;
  }, [strategyHistory, result]);

  const paperHealthSummary = useMemo(
    () =>
      paperHealth({
        lastRunAt: paperRuns[0]?.createdAt,
        paperMetrics: paperRuns[0]?.metrics ?? null,
        baselineMetrics: researchBaseline,
      }),
    [paperRuns, researchBaseline],
  );

  const shareInput = buildShareCardInput({
    saved,
    spec,
    identity,
    symbolInput: symbol,
    timeframe,
    start,
    end,
    metrics: result?.metrics ?? null,
    grade: edge?.verdict.grade ?? null,
    score: edge?.verdict.score ?? null,
    flags: edge?.verdict.flags ?? null,
    paper: { state: paperHealthSummary.state, headline: paperHealthSummary.headline },
    link: typeof window === 'undefined' ? null : window.location.href,
  });

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4">
      <StudioHeader
        saved={saved}
        loading={bt.loading}
        linkCopied={linkCopied}
        onShare={() => void copyShareLink()}
        onRefresh={() => {
          setError(null);
          setNotice(null);
          void bt.refresh();
          if (saved) {
            void loadHistory(saved.id);
            void loadPaperTrack(saved.id);
          }
        }}
      />

      <StageRail current={stage} completed={completed} />

      <CompactSummary saved={saved} result={result} edge={edge} health={paperHealthSummary} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <StudioSidebar
          templates={STRATEGY_TEMPLATES}
          selectedId={saved?.id ?? null}
          busy={loadingStrategy}
          onOpen={(id) => void openStrategy(id)}
          onNew={newStrategy}
          onTemplate={applyTemplate}
          thesis={thesis}
          onThesisChange={updateThesis}
          onDraft={() => void draftWithAi()}
          drafting={drafting}
          disabled={disabled}
          symbol={symbol}
          timeframe={timeframe}
          saved={saved}
        />

        {/* ── Right: spec, results ── */}
        <div className="flex min-w-0 flex-col gap-4">
          <MethodDiscoveryPanel
            symbol={(splitSymbols(symbol)[0] || symbol || 'BTC-USD').toUpperCase()}
            symbols={splitSymbols(symbol)}
            interval={timeframe}
            onUseSpec={(text) => {
              setEditor(text);
              setNotice('Method spec loaded. Review it, then save and run.');
            }}
            onError={setError}
          />

          <ResearchIntelligencePanel
            symbol={(splitSymbols(symbol)[0] || symbol || 'BTC-USD').toUpperCase()}
            interval={timeframe}
            onError={setError}
          />

          <SystemHealthPanel
            strategyId={saved?.id}
            version={saved ? String(saved.version ?? saved.latestVersion) : undefined}
            onError={setError}
          />

          <LiveStrategyPanel
            strategyId={saved?.id}
            version={saved ? String(saved.version ?? saved.latestVersion) : undefined}
            symbol={(splitSymbols(symbol)[0] || symbol || 'BTC-USD').toUpperCase()}
            onError={setError}
          />

          <SpecCard
            editor={editor}
            onEditor={setEditor}
            spec={spec}
            identityId={identity.id}
            saved={saved}
            issues={issues}
            copiedPath={copiedPath}
            onCopyPath={(path) => void copyPath(path)}
            onValidate={() => void validate()}
            onSaveAndRun={() => void saveAndRun()}
            busy={busy}
            saving={saving}
            running={bt.running}
            progress={progress}
          />

          <StudioAlerts error={error ?? bt.error} notice={notice} />

          {result ? (
            <ResultPanels result={result} grading={grading} onGrade={() => void gradeEdge()} />
          ) : (
            <EmptyResults />
          )}
        </div>
      </div>

      <ExperimentHistory
        experiments={history}
        activeId={activeExperimentId}
        onOpen={openExperiment}
        onDelete={(id) => void removeExperiment(id)}
        onError={setError}
      />

      {saved ? (
        <VersionPanel
          strategy={saved}
          onError={setError}
          onImported={() => void bt.refresh()}
        />
      ) : null}

      <PortfolioPanel
        strategies={bt.strategies}
        currentId={saved?.id ?? null}
        start={start}
        end={end}
        capital={capital}
        running={bt.running}
        onRun={bt.runPortfolio}
        onError={setError}
      />

      <ResearchJournalPanel
        strategyId={saved?.id ?? null}
        experimentId={result?.experimentId ?? null}
        onError={setError}
      />

      <PortfolioStressLab symbols={splitSymbols(symbol)} onError={setError} />

      {activeExperimentId ? (
        <ManifestPanel experimentId={activeExperimentId} />
      ) : null}

      {saved || result ? <ShareCard input={shareInput} /> : null}

      {edge ? (
        <div className="glass-card rounded-2xl p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">Edge report</h2>
            <span className="font-mono text-[10px] text-muted-foreground">
              grade · axes · flags · figures
            </span>
            {saved ? (
              <PublishButton strategy={saved} report={edge} onNotice={setNotice} onError={setError} />
            ) : null}
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">{edge.experimentId}</span>
          </div>
          <EdgeReportView report={edge} />
        </div>
      ) : null}

      {saved && result ? (
        <ResearchStudio
          key={`${saved.id}:${saved.version ?? saved.latestVersion}`}
          selected={saved}
          symbols={splitSymbols(symbol)}
          start={start}
          end={end}
          initialCapital={capital}
          running={bt.running}
          progress={bt.progress}
          onRun={bt.runResearch}
          onError={setError}
        />
      ) : null}

      <PaperPanel
        hasSaved={Boolean(saved)}
        hasResult={Boolean(result)}
        approved={paperApproved}
        onApproved={setPaperApproved}
        busy={paperBusy}
        onPromote={() => void promote()}
        paper={paper}
        mode={paperModeEffective}
        onMode={(mode) => {
          setPaperMode(mode);
          setPaperModeChosen(true);
        }}
        window={paperWindow}
        track={paperRuns}
        trackExperiments={paperExperiments}
        expected={researchBaseline}
      />
    </div>
  );
}

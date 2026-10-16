'use client';

// ML Research Lab — a workbench over the real Python ML engine.
// No mocked metrics: every value shown comes from a persisted dataset version,
// experiment run, evaluation or registered model returned by /api/ml.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { DesktopOnlyNotice } from '@/components/ui/desktop-only-notice';
import {
  mlClient,
  type Capabilities,
  type DatasetRecord,
  type DatasetVersion,
  type ExperimentRecord,
  type JobRecord,
  type ModelRecord,
  type ModelVersion,
  type RunResult,
} from '@/lib/ml-client';

type Tab = 'overview' | 'datasets' | 'experiments' | 'models';

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'datasets', label: 'Datasets' },
  { id: 'experiments', label: 'Experiments' },
  { id: 'models', label: 'Model Registry' },
];

const TERMINAL_JOB_STATES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'CANCEL_REQUESTED', 'TIMED_OUT', 'DEAD_LETTER']);

const fmt = (v: unknown, digits = 4) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="glass-card-subtle rounded-lg p-3" title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-white/50">{label}</div>
      <div className="text-lg font-medium text-white">{value}</div>
    </div>
  );
}

function Panel({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="glass-card rounded-xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-white/90">{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="glass-card-subtle rounded-lg border border-red-500/30 p-3 text-xs text-red-300">
      {message}
    </div>
  );
}

function Spinner({ label }: { label: string }) {
  return <div className="text-xs text-white/50">{label}…</div>;
}

const csv = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean);

function MetricsTable({ metrics }: { metrics: Record<string, unknown> }) {
  const rows = Object.entries(metrics).filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object');
  if (!rows.length) return <div className="text-xs text-white/40">no scalar metrics</div>;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {rows.map(([k, v]) => (
        <Metric key={k} label={k} value={typeof v === 'number' ? fmt(v) : String(v)} />
      ))}
    </div>
  );
}

export function MlLabScreen() {
  const [tab, setTab] = useState<Tab>('overview');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [datasets, setDatasets] = useState<DatasetRecord[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);

  // dataset builder form
  const [dsName, setDsName] = useState('Equity momentum dataset');
  const [dsSymbols, setDsSymbols] = useState('AAPL, MSFT, NVDA, AMZN, GOOGL');
  const [dsFeatures, setDsFeatures] = useState('ret_1, ret_5, ret_21, vol_21, volume_z_21');
  const [targetKind, setTargetKind] = useState('direction_binary');
  const [horizon, setHorizon] = useState(5);
  const [lastBuild, setLastBuild] = useState<{ datasetId: string; version: string; dataHash: string; quality: { ok: boolean; findings: { severity: string; message: string }[] } } | null>(null);
  const [versions, setVersions] = useState<DatasetVersion[]>([]);

  // experiment form
  const [expDataset, setExpDataset] = useState('');
  const [expVersion, setExpVersion] = useState('');
  const [expFamily, setExpFamily] = useState('logistic');
  const [splitMethod, setSplitMethod] = useState('walk_forward');
  const [nSplits, setNSplits] = useState(4);
  const [purge, setPurge] = useState(true);
  const [embargo, setEmbargo] = useState(1);
  const [seed, setSeed] = useState(42);
  const [selection, setSelection] = useState('none');
  const [background, setBackground] = useState(true);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [activeJob, setActiveJob] = useState<JobRecord | null>(null);
  const [lastResult, setLastResult] = useState<{ runId: string; result: RunResult; registered: { modelId: string; version: string } | null } | null>(null);

  // model registry
  const [modelDetail, setModelDetail] = useState<ModelVersion | null>(null);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, d, e, m] = await Promise.all([
        mlClient.capabilities(),
        mlClient.listDatasets(),
        mlClient.listExperiments(),
        mlClient.listModels(),
      ]);
      setCaps(c);
      setDatasets(d.datasets);
      setExperiments(e.experiments);
      setModels(m.models);
      // Jobs are optional (the Execution Fabric may be disabled); never fail the
      // whole refresh because of them.
      try {
        setJobs((await mlClient.listJobs()).jobs);
      } catch {
        setJobs([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load ML lab');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const availableModels = useMemo(() => (caps?.models ?? []).filter((m) => m.available), [caps]);

  const buildDataset = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await mlClient.buildDataset({
        name: dsName,
        symbols: csv(dsSymbols),
        featureNames: csv(dsFeatures),
        target: { kind: targetKind, horizon },
        missingPolicy: 'drop',
      });
      setLastBuild({ datasetId: result.datasetId, version: result.version, dataHash: result.dataHash, quality: result.quality });
      const v = await mlClient.listDatasetVersions(result.datasetId);
      setVersions(v.versions);
      setExpDataset(result.datasetId);
      setExpVersion(result.version);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'dataset build failed');
    } finally {
      setBusy(false);
    }
  }, [dsName, dsSymbols, dsFeatures, targetKind, horizon, refresh]);

  const loadVersions = useCallback(async (datasetId: string) => {
    try {
      const v = await mlClient.listDatasetVersions(datasetId);
      setVersions(v.versions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load versions');
    }
  }, []);

  const runExperiment = useCallback(async () => {
    setBusy(true);
    setError(null);
    const body = {
      datasetId: expDataset,
      datasetVersion: expVersion,
      title: `${expFamily} on ${expDataset}@${expVersion}`,
      modelFamily: expFamily,
      selection: { method: selection },
      split: { method: splitMethod, nSplits, purge, embargo },
      seed,
    };
    try {
      if (background) {
        const res = await mlClient.runExperimentBackground(body);
        setActiveJob({ jobId: res.job.jobId, status: res.job.status });
        await refresh();
      } else {
        const result = await mlClient.runExperiment(body);
        setLastResult({ runId: result.runId, result: result.result, registered: result.registered });
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'experiment failed');
    } finally {
      setBusy(false);
    }
  }, [expDataset, expVersion, expFamily, selection, splitMethod, nSplits, purge, embargo, seed, background, refresh]);

  const cancelJob = useCallback(async (jobId: string) => {
    setError(null);
    try {
      await mlClient.cancelJob(jobId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'cancel failed');
    }
  }, [refresh]);

  // Poll an active background job until it reaches a terminal state.
  const jobStatus = activeJob?.status;
  const jobId = activeJob?.jobId;
  useEffect(() => {
    if (!jobId || !jobStatus) return;
    if (TERMINAL_JOB_STATES.has(jobStatus)) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const { job } = await mlClient.getJob(jobId);
        if (cancelled) return;
        setActiveJob(job);
        if (TERMINAL_JOB_STATES.has(job.status)) {
          await refresh();
          if (job.status === 'SUCCEEDED' && job.output?.runId) {
            const { run } = await mlClient.getRun(job.output.runId);
            if (run.result) {
              setLastResult({ runId: run.id, result: run.result, registered: job.output.registered ?? null });
            }
          }
        }
      } catch {
        /* transient poll failure — keep trying until terminal */
      }
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId, jobStatus, refresh]);

  const registerLast = useCallback(async () => {
    if (!lastResult) return;
    setBusy(true);
    setError(null);
    try {
      const reg = await mlClient.registerModel({ runId: lastResult.runId, name: `${expFamily} model` });
      setLastResult({ ...lastResult, registered: { modelId: reg.modelId, version: reg.version } });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'registration failed');
    } finally {
      setBusy(false);
    }
  }, [lastResult, expFamily, refresh]);

  const reproduceLast = useCallback(async () => {
    if (!lastResult) return;
    setBusy(true);
    setError(null);
    try {
      const r = await mlClient.reproduceRun(lastResult.runId);
      alert(`Reproduced within tolerance: ${r.withinTolerance}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'reproduce failed');
    } finally {
      setBusy(false);
    }
  }, [lastResult]);

  const openModel = useCallback(async (modelId: string) => {
    setError(null);
    try {
      setModelDetail(await mlClient.getModel(modelId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load model');
    }
  }, []);

  const verifyModel = useCallback(async () => {
    if (!modelDetail) return;
    setError(null);
    try {
      const v = await mlClient.verifyModel(modelDetail.modelId, modelDetail.version);
      setVerifyMsg(`integrity ${v.ok ? 'OK' : 'FAILED'} (sha256 ${v.actual.slice(0, 12)}…)`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'verify failed');
    }
  }, [modelDetail]);

  const transition = useCallback(async (action: string) => {
    if (!modelDetail) return;
    setError(null);
    try {
      const updated = await mlClient.transitionModel(modelDetail.modelId, {
        version: modelDetail.version,
        action,
        actor: 'local',
      });
      setModelDetail(updated);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'transition failed');
    }
  }, [modelDetail, refresh]);

  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-y-auto p-4 md:p-6">
      <DesktopOnlyNotice title="ML Lab" />
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">ML Research Lab</h2>
          <p className="text-xs text-white/50">
            Datasets, temporal validation, model training, evaluation and a versioned registry.
          </p>
        </div>
        <button
          onClick={() => void refresh()}
          className="glass-card-subtle rounded-lg px-3 py-1.5 text-xs text-white/80 hover:text-white"
        >
          Refresh
        </button>
      </div>

      <div className="glass-card-subtle flex gap-1 overflow-x-auto scrollbar-hide rounded-lg p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'rounded-md px-3 py-1.5 text-xs transition-colors',
              tab === t.id ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}
      {busy && <Spinner label="working" />}

      {tab === 'overview' && (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Engine">
            {loading ? (
              <Spinner label="loading" />
            ) : caps ? (
              <>
                <Metric label="Available" value={caps.available ? 'yes' : 'no'} />
                <div className="mt-3 space-y-2">
                  {caps.models.map((m) => (
                    <div key={m.family} className="flex items-center justify-between text-xs">
                      <span className="text-white/80">{m.family}</span>
                      <span className={m.available ? 'text-emerald-300' : 'text-white/40'}>
                        {m.available ? `available (${m.tasks.join(', ')})` : 'unavailable'}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-xs text-white/40">unavailable</div>
            )}
          </Panel>
          <Panel title="Workspace">
            <div className="grid grid-cols-3 gap-2">
              <Metric label="Datasets" value={String(datasets.length)} />
              <Metric label="Experiments" value={String(experiments.length)} />
              <Metric label="Models" value={String(models.length)} />
            </div>
            <p className="mt-3 text-xs text-white/50">
              Models train on strictly chronological folds with purge/embargo; the final test period is never
              used for model selection. Optional model families report honestly when their library is absent.
            </p>
          </Panel>
        </div>
      )}

      {tab === 'datasets' && (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Build a dataset version">
            <div className="space-y-2 text-xs">
              <input className="glass-card-subtle w-full rounded-md px-2 py-1.5 text-white" value={dsName} onChange={(e) => setDsName(e.target.value)} placeholder="name" />
              <input className="glass-card-subtle w-full rounded-md px-2 py-1.5 text-white" value={dsSymbols} onChange={(e) => setDsSymbols(e.target.value)} placeholder="symbols" />
              <input className="glass-card-subtle w-full rounded-md px-2 py-1.5 text-white" value={dsFeatures} onChange={(e) => setDsFeatures(e.target.value)} placeholder="features" />
              <div className="flex gap-2">
                <select className="glass-card-subtle rounded-md px-2 py-1.5 text-white" value={targetKind} onChange={(e) => setTargetKind(e.target.value)}>
                  <option value="direction_binary">direction_binary</option>
                  <option value="forward_return">forward_return</option>
                  <option value="direction_multiclass">direction_multiclass</option>
                  <option value="volatility">volatility</option>
                  <option value="cross_sectional_rank">cross_sectional_rank</option>
                </select>
                <input type="number" min={1} className="glass-card-subtle w-24 rounded-md px-2 py-1.5 text-white" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
              </div>
              <button disabled={busy} onClick={() => void buildDataset()} className="glass-card rounded-md px-3 py-1.5 text-white disabled:opacity-50">
                Build & validate
              </button>
            </div>
            {lastBuild && (
              <div className="mt-3 text-xs">
                <div className="text-white/80">
                  {lastBuild.datasetId}@{lastBuild.version} · quality {lastBuild.quality.ok ? 'ok' : 'findings'} · sha256 {lastBuild.dataHash.slice(0, 12)}…
                </div>
                {lastBuild.quality.findings.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {lastBuild.quality.findings.map((f, i) => (
                      <li key={i} className={f.severity === 'critical' ? 'text-red-300' : 'text-amber-200/80'}>
                        [{f.severity}] {f.message}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Panel>
          <Panel title={`Datasets (${datasets.length})`}>
            {loading ? (
              <Spinner label="loading" />
            ) : datasets.length === 0 ? (
              <div className="text-xs text-white/40">no datasets yet — build one to begin</div>
            ) : (
              <div className="space-y-2">
                {datasets.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => void loadVersions(d.id)}
                    className="glass-card-subtle block w-full rounded-lg p-3 text-left text-xs hover:bg-white/5"
                  >
                    <div className="text-white/90">{d.name}</div>
                    <div className="text-white/50">
                      {d.id} · {d.versions} version(s) · {d.assetClass}
                    </div>
                  </button>
                ))}
              </div>
            )}
            {versions.length > 0 && (
              <div className="mt-3 space-y-1 text-xs">
                {versions.map((v) => (
                  <div key={v.version} className="flex justify-between text-white/60">
                    <span>
                      v{v.version} · {v.rows} rows · {v.featureCount} features
                    </span>
                    <span className={v.qualityStatus === 'ok' ? 'text-emerald-300' : 'text-amber-200'}>
                      {v.qualityStatus}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {tab === 'experiments' && (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Run an experiment">
            <div className="space-y-2 text-xs">
              <input className="glass-card-subtle w-full rounded-md px-2 py-1.5 text-white" value={expDataset} onChange={(e) => setExpDataset(e.target.value)} placeholder="datasetId" />
              <input className="glass-card-subtle w-full rounded-md px-2 py-1.5 text-white" value={expVersion} onChange={(e) => setExpVersion(e.target.value)} placeholder="version" />
              <select className="glass-card-subtle w-full rounded-md px-2 py-1.5 text-white" value={expFamily} onChange={(e) => setExpFamily(e.target.value)}>
                {availableModels.map((m) => (
                  <option key={m.family} value={m.family}>{m.family} ({m.tier})</option>
                ))}
              </select>
              <div className="flex gap-2">
                <select className="glass-card-subtle rounded-md px-2 py-1.5 text-white" value={splitMethod} onChange={(e) => setSplitMethod(e.target.value)}>
                  <option value="walk_forward">walk_forward</option>
                  <option value="chronological">chronological</option>
                  <option value="purged_kfold">purged_kfold</option>
                </select>
                <select className="glass-card-subtle rounded-md px-2 py-1.5 text-white" value={selection} onChange={(e) => setSelection(e.target.value)}>
                  <option value="none">no selection</option>
                  <option value="correlation">correlation</option>
                  <option value="variance">variance</option>
                  <option value="mutual_information">mutual_information</option>
                </select>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-white/70">
                <label className="flex items-center gap-1">
                  splits
                  <input type="number" min={2} className="glass-card-subtle w-16 rounded-md px-2 py-1 text-white" value={nSplits} onChange={(e) => setNSplits(Number(e.target.value))} />
                </label>
                <label className="flex items-center gap-1">
                  embargo
                  <input type="number" min={0} className="glass-card-subtle w-16 rounded-md px-2 py-1 text-white" value={embargo} onChange={(e) => setEmbargo(Number(e.target.value))} />
                </label>
                <label className="flex items-center gap-1">
                  purge
                  <input type="checkbox" checked={purge} onChange={(e) => setPurge(e.target.checked)} />
                </label>
                <label className="flex items-center gap-1">
                  seed
                  <input type="number" className="glass-card-subtle w-16 rounded-md px-2 py-1 text-white" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
                </label>
                <label className="flex items-center gap-1" title="Run as a durable, cancellable Execution Fabric job">
                  background
                  <input type="checkbox" checked={background} onChange={(e) => setBackground(e.target.checked)} />
                </label>
              </div>
              <button disabled={busy || !expDataset || !expVersion} onClick={() => void runExperiment()} className="glass-card rounded-md px-3 py-1.5 text-white disabled:opacity-50">
                {background ? 'Submit background job' : 'Train & evaluate'}
              </button>
            </div>
            {activeJob && (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md bg-white/5 px-3 py-2 text-xs">
                <span className="min-w-0 truncate text-white/80">
                  job {activeJob.jobId.slice(0, 12)}… · {activeJob.status}
                  {typeof activeJob.progress === 'number' ? ` · ${Math.round(activeJob.progress * 100)}%` : ''}
                  {activeJob.error ? ` · ${activeJob.error}` : ''}
                </span>
                {!TERMINAL_JOB_STATES.has(activeJob.status) && (
                  <button onClick={() => void cancelJob(activeJob.jobId)} className="glass-card-subtle rounded-md px-2 py-1 text-white/80">
                    Cancel
                  </button>
                )}
              </div>
            )}
          </Panel>
          <Panel title={`Experiments (${experiments.length})`}>
            {loading ? (
              <Spinner label="loading" />
            ) : experiments.length === 0 ? (
              <div className="text-xs text-white/40">no experiments yet</div>
            ) : (
              <div className="space-y-2">
                {experiments.map((e) => (
                  <div key={e.id} className="glass-card-subtle rounded-lg p-3 text-xs">
                    <div className="flex justify-between">
                      <span className="text-white/90">{e.title}</span>
                      <span className={e.status === 'completed' ? 'text-emerald-300' : 'text-amber-200'}>{e.status}</span>
                    </div>
                    <div className="text-white/50">
                      {e.modelFamily} · {e.datasetId}@{e.datasetVersion} · {e.runs} run(s)
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <div className="md:col-span-2">
            <Panel title={`Training jobs (${jobs.length})`}>
              {jobs.length === 0 ? (
                <div className="text-xs text-white/40">no background jobs</div>
              ) : (
                <div className="space-y-1 text-xs">
                  {jobs.map((jb) => (
                    <div key={jb.jobId} className="flex items-center justify-between rounded-md bg-white/5 px-2 py-1">
                      <span className="text-white/70">{jb.jobId.slice(0, 16)}…</span>
                      <span className={jb.status === 'SUCCEEDED' ? 'text-emerald-300' : jb.status === 'FAILED' ? 'text-red-300' : 'text-amber-200'}>
                        {jb.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
          {lastResult && (
            <div className="md:col-span-2">
              <Panel
                title={`Run ${lastResult.runId} — pooled metrics`}
                right={
                  <div className="flex gap-2">
                    <button onClick={() => void reproduceLast()} className="glass-card-subtle rounded-md px-2 py-1 text-xs text-white/80">Reproduce</button>
                    {!lastResult.registered && (
                      <button onClick={() => void registerLast()} className="glass-card rounded-md px-2 py-1 text-xs text-white">Register model</button>
                    )}
                    {lastResult.registered && (
                      <span className="text-xs text-emerald-300">
                        registered {lastResult.registered.modelId}@{lastResult.registered.version}
                      </span>
                    )}
                  </div>
                }
              >
                <MetricsTable metrics={lastResult.result.pooledMetrics} />
                <h4 className="mt-4 mb-2 text-xs font-medium text-white/80">Folds</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-white/70">
                    <thead className="text-white/40">
                      <tr>
                        <th className="py-1 pr-3">#</th>
                        <th className="py-1 pr-3">train</th>
                        <th className="py-1 pr-3">test</th>
                        <th className="py-1 pr-3">purged</th>
                        <th className="py-1 pr-3">embargoed</th>
                        <th className="py-1 pr-3">key metric</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lastResult.result.folds.map((f) => (
                        <tr key={f.index} className="border-t border-white/5">
                          <td className="py-1 pr-3">{f.index}</td>
                          <td className="py-1 pr-3">{f.nTrain}</td>
                          <td className="py-1 pr-3">{f.nTest}</td>
                          <td className="py-1 pr-3">{f.nPurged}</td>
                          <td className="py-1 pr-3">{f.nEmbargoed}</td>
                          <td className="py-1 pr-3">
                            {lastResult.result.task === 'classification'
                              ? fmt(f.metrics.accuracy)
                              : fmt(f.metrics.r2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {lastResult.result.finalFeatureImportance && (
                  <>
                    <h4 className="mt-4 mb-2 text-xs font-medium text-white/80">Final model feature importance</h4>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {Object.entries(lastResult.result.finalFeatureImportance).map(([k, v]) => (
                        <Metric key={k} label={k} value={fmt(v)} />
                      ))}
                    </div>
                  </>
                )}
                <h4 className="mt-4 mb-2 text-xs font-medium text-white/80">Final holdout evaluation</h4>
                <MetricsTable metrics={lastResult.result.finalEvaluation} />
              </Panel>
            </div>
          )}
        </div>
      )}

      {tab === 'models' && (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title={`Registered models (${models.length})`}>
            {loading ? (
              <Spinner label="loading" />
            ) : models.length === 0 ? (
              <div className="text-xs text-white/40">no models registered yet</div>
            ) : (
              <div className="space-y-2">
                {models.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => void openModel(m.id)}
                    className="glass-card-subtle block w-full rounded-lg p-3 text-left text-xs hover:bg-white/5"
                  >
                    <div className="flex justify-between">
                      <span className="text-white/90">{m.name}</span>
                      <span className="text-white/50">{m.status}</span>
                    </div>
                    <div className="text-white/50">
                      {m.id} · {m.family} · v{m.latestVersion}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Model detail">
            {!modelDetail ? (
              <div className="text-xs text-white/40">select a model</div>
            ) : (
              <div className="space-y-3 text-xs">
                <MetricsTable metrics={modelDetail.metrics as Record<string, unknown>} />
                <div className="text-white/60">
                  {modelDetail.modelId}@{modelDetail.version} · {modelDetail.family} · {modelDetail.task} · {modelDetail.status}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => void verifyModel()} className="glass-card-subtle rounded-md px-2 py-1 text-white/80">Verify artifact</button>
                  <button onClick={() => void transition('evaluate')} className="glass-card-subtle rounded-md px-2 py-1 text-white/80">Mark evaluated</button>
                  <button onClick={() => void transition('approve_research')} className="glass-card-subtle rounded-md px-2 py-1 text-white/80">Approve (research)</button>
                  <button onClick={() => void transition('archive')} className="glass-card-subtle rounded-md px-2 py-1 text-white/80">Archive</button>
                </div>
                {verifyMsg && <div className="text-emerald-300">{verifyMsg}</div>}
                <div>
                  <div className="mb-1 text-white/50">Approval history</div>
                  {modelDetail.approvals.length === 0 ? (
                    <div className="text-white/40">none</div>
                  ) : (
                    modelDetail.approvals.map((a, i) => (
                      <div key={i} className="text-white/60">
                        {a.action} · {a.actor ?? '—'} · {a.reason ?? ''}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}

export default MlLabScreen;

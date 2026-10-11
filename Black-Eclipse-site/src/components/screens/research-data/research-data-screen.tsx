'use client';

// Quant Research Data — Dataset Explorer, Builder, Data Quality Center and
// Provider health. A thin client over /api/research-data (the Python research
// system). Every number shown is the runtime's; nothing is fabricated here.

import { useCallback, useEffect, useState } from 'react';
import {
  researchDataClient,
  type DatasetManifest,
  type DatasetSummary,
  type ProviderDescriptor,
  type QualityEvent,
  type StoredSeries,
  type VerificationPolicy,
} from '@/lib/research-data/research-data-client';

type View = 'datasets' | 'build' | 'notebook' | 'quality' | 'providers';

const INTERVALS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'];
const OPERATIONS = ['summary', 'returns', 'volatility', 'max_drawdown', 'sharpe', 'correlation'];

function Panel({ title, children, actions }: { title: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="glass-card rounded-xl p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-foreground">{title}</h3>
        {actions}
      </div>
      {children}
    </div>
  );
}

function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <p className="mt-2 rounded-md bg-rose-500/10 px-2 py-1 text-xs text-rose-300">{message}</p>;
}

function DatasetsView() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [manifest, setManifest] = useState<DatasetManifest | null>(null);
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await researchDataClient.datasets();
      setDatasets(data.datasets ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to list datasets');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const open = useCallback(async (id: string) => {
    setSelected(id);
    setAnalysis(null);
    setError(null);
    try {
      const data = await researchDataClient.manifest(id);
      setManifest(data.manifest);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load manifest');
    }
  }, []);

  const runAnalyze = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const data = await researchDataClient.analyze(selected, { operations: OPERATIONS });
      setAnalysis(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'analysis failed');
    } finally {
      setBusy(false);
    }
  }, [selected]);

  const runExport = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const data = await researchDataClient.exportDataset(selected, { format: 'csv' });
      setError(null);
      alert(`Exported ${data.rowCount} rows to:\n${data.files.join('\n')}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'export failed');
    } finally {
      setBusy(false);
    }
  }, [selected]);

  const runRefresh = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const data = await researchDataClient.refresh(selected);
      setManifest(data.manifest);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'refresh failed');
    } finally {
      setBusy(false);
    }
  }, [selected, load]);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <Panel title={`Datasets (${datasets.length})`} actions={
        <button type="button" onClick={() => void load()} className="text-xs text-muted-foreground hover:text-foreground">Refresh</button>
      }>
        {datasets.length === 0 ? (
          <p className="text-xs text-muted-foreground">No datasets yet. Build one in the Build tab.</p>
        ) : (
          <ul className="space-y-1">
            {datasets.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => void open(d.id)}
                  className={`w-full rounded-lg px-2 py-1.5 text-left hover:bg-white/5 ${selected === d.id ? 'bg-white/10' : ''}`}
                >
                  <div className="truncate font-mono text-xs text-foreground">{d.name || d.id}</div>
                  <div className="truncate font-mono text-[10px] text-muted-foreground">
                    {d.id} · {d.versions} version(s) · {d.updatedAt}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Dataset detail" actions={
        selected ? (
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => void runAnalyze()} className="rounded bg-white/10 px-2 py-1 text-xs hover:bg-white/20 disabled:opacity-40">Analyze</button>
            <button type="button" disabled={busy} onClick={() => void runExport()} className="rounded bg-white/10 px-2 py-1 text-xs hover:bg-white/20 disabled:opacity-40">Export CSV</button>
            <button type="button" disabled={busy} onClick={() => void runRefresh()} className="rounded bg-white/10 px-2 py-1 text-xs hover:bg-white/20 disabled:opacity-40">Refresh</button>
          </div>
        ) : null
      }>
        {!manifest ? (
          <p className="text-xs text-muted-foreground">Select a dataset to inspect its manifest, coverage, quality and lineage.</p>
        ) : (
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Version" value={manifest.version} />
              <Stat label="Symbols" value={String(manifest.coverage.symbolCount)} />
              <Stat label="Rows" value={String(manifest.coverage.rowCount)} />
              <Stat label="Immutable" value={manifest.immutable ? 'yes' : 'no'} />
            </div>
            <div className="text-muted-foreground">
              <div>Range: {manifest.coverage.start ?? '?'} → {manifest.coverage.end ?? '?'}</div>
              <div className="truncate">Hash: {manifest.contentHash}</div>
              <div>Created: {manifest.createdAt}</div>
            </div>
            <div>
              <div className="mb-1 font-medium text-foreground">Coverage per symbol</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(manifest.coverage.perSymbolRows).map(([sym, n]) => (
                  <span key={sym} className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px]">{sym}: {n}</span>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1 font-medium text-foreground">Quality</div>
              <pre className="max-h-40 overflow-auto rounded bg-black/30 p-2 font-mono text-[10px]">{JSON.stringify(manifest.quality, null, 2)}</pre>
            </div>
            {analysis && (
              <div>
                <div className="mb-1 font-medium text-foreground">Analysis</div>
                <pre className="max-h-52 overflow-auto rounded bg-black/30 p-2 font-mono text-[10px]">{JSON.stringify(analysis, null, 2)}</pre>
              </div>
            )}
          </div>
        )}
        <ErrorNote message={error} />
      </Panel>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="truncate font-mono text-foreground">{value}</div>
    </div>
  );
}

function BuildView() {
  const [symbols, setSymbols] = useState('AAPL, MSFT');
  const [interval, setInterval] = useState('1d');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [policy, setPolicy] = useState('fresh_preferred');
  const [policies, setPolicies] = useState<VerificationPolicy[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DatasetManifest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void researchDataClient.policies().then((d) => setPolicies(d.policies ?? [])).catch(() => {});
  }, []);

  const build = useCallback(async () => {
    const list = symbols.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    if (list.length === 0) { setError('enter at least one symbol'); return; }
    setBusy(true);
    setError(null);
    try {
      const data = await researchDataClient.build({
        symbols: list, interval,
        start: start || undefined, end: end || undefined,
        verification_policy: policy, name: name || undefined,
      });
      setResult(data.manifest);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'build failed');
    } finally {
      setBusy(false);
    }
  }, [symbols, interval, start, end, policy, name]);

  return (
    <div className="max-w-2xl space-y-3">
      <Panel title="Build an immutable dataset version">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Symbols (comma-separated)">
            <input className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground outline-none focus:border-white/30" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
          </Field>
          <Field label="Interval">
            <select className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground outline-none focus:border-white/30" value={interval} onChange={(e) => setInterval(e.target.value)}>
              {INTERVALS.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
          </Field>
          <Field label="Start (YYYY-MM-DD)"><input className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground outline-none focus:border-white/30" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="End (YYYY-MM-DD)"><input className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground outline-none focus:border-white/30" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
          <Field label="Verification policy">
            <select className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground outline-none focus:border-white/30" value={policy} onChange={(e) => setPolicy(e.target.value)}>
              {policies.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Name (optional)"><input className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground outline-none focus:border-white/30" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        </div>
        <button type="button" disabled={busy} onClick={() => void build()} className="mt-3 rounded bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20 disabled:opacity-40">
          {busy ? 'Building…' : 'Build dataset'}
        </button>
        {policy && policies.length > 0 && (
          <p className="mt-2 text-[10px] text-muted-foreground">
            {policies.find((p) => p.name === policy)?.description}
          </p>
        )}
        <ErrorNote message={error} />
      </Panel>
      {result && (
        <Panel title={`Built ${result.datasetId} ${result.version}`}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-xs">
            <Stat label="Symbols" value={String(result.coverage.symbolCount)} />
            <Stat label="Rows" value={String(result.coverage.rowCount)} />
            <Stat label="Range" value={`${result.coverage.start ?? '?'} → ${result.coverage.end ?? '?'}`} />
            <Stat label="Hash" value={result.contentHash.slice(0, 12)} />
          </div>
        </Panel>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function QualityView() {
  const [events, setEvents] = useState<QualityEvent[]>([]);
  const [series, setSeries] = useState<StoredSeries[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await researchDataClient.quality();
      setEvents(data.events ?? []);
      setSeries(data.storedSeries ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load quality');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title={`Data-quality findings (${events.length})`} actions={
        <button type="button" onClick={() => void load()} className="text-xs text-muted-foreground hover:text-foreground">Refresh</button>
      }>
        {events.length === 0 ? <p className="text-xs text-muted-foreground">No findings recorded.</p> : (
          <table className="w-full text-left text-[11px]">
            <thead className="text-muted-foreground"><tr><th>Symbol</th><th>Kind</th><th>Severity</th><th>Detail</th></tr></thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-white/5">
                  <td className="py-1 font-mono">{e.symbol ?? '—'}</td>
                  <td className="py-1">{e.kind}</td>
                  <td className={`py-1 ${e.severity === 'invalid' ? 'text-rose-300' : 'text-amber-300'}`}>{e.severity}</td>
                  <td className="max-w-[220px] truncate py-1 text-muted-foreground" title={e.detail}>{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ErrorNote message={error} />
      </Panel>
      <Panel title={`Stored series (${series.length})`}>
        {series.length === 0 ? <p className="text-xs text-muted-foreground">No normalized bars stored yet.</p> : (
          <table className="w-full text-left text-[11px]">
            <thead className="text-muted-foreground"><tr><th>Symbol</th><th>Interval</th><th>Provider</th><th>Bars</th><th>Range</th></tr></thead>
            <tbody>
              {series.map((s, i) => (
                <tr key={`${s.symbol}-${s.interval}-${i}`} className="border-t border-white/5">
                  <td className="py-1 font-mono">{s.symbol}</td>
                  <td className="py-1">{s.interval}</td>
                  <td className="py-1">{s.provider}</td>
                  <td className="py-1">{s.n}</td>
                  <td className="py-1 text-muted-foreground">{s.start ?? '?'} → {s.end ?? '?'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

function ProvidersView() {
  const [providers, setProviders] = useState<ProviderDescriptor[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await researchDataClient.providers();
      setProviders(data.providers ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load providers');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <Panel title={`Providers (${providers.length})`} actions={
      <button type="button" onClick={() => void load()} className="text-xs text-muted-foreground hover:text-foreground">Refresh</button>
    }>
      <table className="w-full text-left text-[11px]">
        <thead className="text-muted-foreground"><tr><th>Provider</th><th>Timeliness</th><th>Entitlement</th><th>Intervals</th><th>Adj</th><th>Configured</th></tr></thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id} className="border-t border-white/5">
              <td className="py-1 font-mono">{p.id}</td>
              <td className="py-1">{p.timeliness}</td>
              <td className="py-1">{p.entitlement}</td>
              <td className="py-1 text-muted-foreground">{p.intervals.join(', ') || '—'}</td>
              <td className="py-1">{p.adjustments ? 'yes' : 'no'}</td>
              <td className="py-1">{p.configured === null ? 'keyless' : p.configured ? 'yes' : 'no'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorNote message={error} />
    </Panel>
  );
}

const DEFAULT_CODE = `import os, csv
rows = list(csv.DictReader(open(os.environ['ECLIPSE_DATASET_PATH'])))
print('rows', len(rows))
closes = [float(r['close']) for r in rows if r['close']]
print('mean close', (sum(closes) / len(closes)) if closes else 0)
`;

function NotebookView() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [code, setCode] = useState(DEFAULT_CODE);
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void researchDataClient.datasets().then((d) => {
      setDatasets(d.datasets ?? []);
      if ((d.datasets ?? []).length > 0) setDatasetId((prev) => prev || d.datasets[0].id);
    }).catch(() => {});
  }, []);

  const run = useCallback(async () => {
    if (!datasetId) { setError('select a dataset'); return; }
    setRunning(true);
    setError(null);
    setMeta(null);
    try {
      const result = await researchDataClient.execute(datasetId, { code, timeout_seconds: 30 });
      setOutput(result.output ?? '');
      setMeta(`${result.status} · exit=${result.exitCode} · ${result.durationMs}ms · ${result.rows} rows${result.timedOut ? ' · TIMED OUT' : ''}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'execution failed');
    } finally {
      setRunning(false);
    }
  }, [datasetId, code]);

  return (
    <div className="space-y-3">
      <Panel title="Isolated notebook" actions={
        <div className="flex items-center gap-2">
          <select
            className="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-xs text-foreground"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
          >
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name || d.id}</option>)}
          </select>
          <button type="button" disabled={running} onClick={() => void run()} className="rounded bg-white/10 px-3 py-1 text-xs hover:bg-white/20 disabled:opacity-40">
            {running ? 'Running…' : 'Run'}
          </button>
        </div>
      }>
        <p className="mb-2 text-[10px] text-muted-foreground">
          Runs in the isolated sandbox against a read-only copy of the dataset version — no
          provider credentials, no vault, no network. The dataset CSV is at
          <span className="font-mono"> os.environ[&apos;ECLIPSE_DATASET_PATH&apos;]</span>.
        </p>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          spellCheck={false}
          rows={12}
          className="w-full rounded-md border border-white/10 bg-black/30 p-2 font-mono text-[11px] text-foreground outline-none focus:border-white/30"
        />
        {meta && <p className="mt-2 font-mono text-[10px] text-muted-foreground">{meta}</p>}
        <ErrorNote message={error} />
      </Panel>
      {output !== null && (
        <Panel title="Output">
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[11px]">{output || '(no output)'}</pre>
        </Panel>
      )}
    </div>
  );
}

const VIEWS: Array<{ id: View; label: string }> = [
  { id: 'datasets', label: 'Datasets' },
  { id: 'build', label: 'Build' },
  { id: 'notebook', label: 'Notebook' },
  { id: 'quality', label: 'Data Quality' },
  { id: 'providers', label: 'Providers' },
];

export function ResearchDataScreen() {
  const [view, setView] = useState<View>('datasets');
  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-foreground">Quant Research Data</h2>
          <p className="text-xs text-muted-foreground">
            Immutable datasets, independent verification, provenance and data-quality — served by the Eclipse runtime.
          </p>
        </div>
        <div className="flex gap-1">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setView(v.id)}
              className={`rounded-lg px-2.5 py-1 text-xs ${view === v.id ? 'bg-white/15 text-foreground' : 'text-muted-foreground hover:bg-white/5'}`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      {view === 'datasets' && <DatasetsView />}
      {view === 'build' && <BuildView />}
      {view === 'notebook' && <NotebookView />}
      {view === 'quality' && <QualityView />}
      {view === 'providers' && <ProvidersView />}
    </div>
  );
}

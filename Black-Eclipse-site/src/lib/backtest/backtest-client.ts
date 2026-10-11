// ── Backtest screen client ───────────────────────────────────────────────────
// The Backtest surface talks to the Python Quant Engine through the
// `/api/backtest/*` front-door proxy. This module MUST stay client-safe (fetch
// only): it lists/creates strategies, runs backtests and reads experiments the
// runtime owns. It adds no quant logic.

export interface StrategySummary {
  id: string;
  name: string;
  description?: string | null;
  assetClass?: string | null;
  latestVersion: string;
  archived: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface StrategyRecord extends StrategySummary {
  version: string;
  spec: Record<string, unknown>;
  contentHash?: string | null;
  schemaVersion?: string | null;
}

/** A stored strategy version's immutable identity. */
export interface VersionInfo {
  version: string;
  contentHash?: string | null;
  schemaVersion?: string | null;
  createdAt: string;
}

export interface VersionMeta extends VersionInfo {
  strategyId: string;
  experimentCount: number;
  immutable: boolean;
}

/** The manifest of a portable strategy bundle. */
export interface BundleManifest {
  format: string;
  bundleVersion: number;
  schemaVersion: string;
  strategyId: string;
  strategyVersion: string;
  name: string;
  description?: string;
  contentHash: string;
  provenance: Record<string, unknown>;
}

export interface DiffChange {
  path: string;
  kind: 'added' | 'removed' | 'changed';
  a?: unknown;
  b?: unknown;
}

export interface VersionDiff {
  strategyId: string;
  a: string;
  b: string;
  sameContent: boolean;
  hashA?: string | null;
  hashB?: string | null;
  changeCount: number;
  bySection: Record<string, number>;
  changes: DiffChange[];
}

/** A strategy-graph node type in the runtime registry. */
export interface GraphNodeSpec {
  type: string;
  version: string;
  title: string;
  category: string;
  description: string;
  inputs: Array<{ name: string; type: string; required: boolean; variadic: boolean }>;
  outputs: Array<{ name: string; type: string }>;
  config: Record<string, unknown>;
  defaults: Record<string, unknown>;
}

export interface GraphDiagnostic {
  code: string;
  message: string;
  nodeId?: string;
  path?: string;
  severity: string;
}

export interface GraphCompileResult {
  ok: boolean;
  spec: Record<string, unknown> | null;
  diagnostics: GraphDiagnostic[];
  sourceMap: Record<string, string>;
  ordering: string[];
}

export interface StrategyGraph {
  schemaVersion?: string;
  strategy: {
    id: string;
    name: string;
    version?: string;
    description?: string;
    assetClass?: string | null;
  };
  nodes: Array<{ id: string; type: string; version?: string; config?: Record<string, unknown> }>;
  edges: Array<{ from: string; fromPort?: string; to: string; toPort?: string }>;
  metadata?: Record<string, unknown>;
}

export interface PythonRunInput {
  strategyCode: string;
  className?: string;
  symbols: string[];
  interval?: string;
  start?: string;
  end?: string;
  initialCapital?: number;
  riskFreeRate?: number;
  randomSeed?: number;
  params?: Record<string, unknown>;
  timeoutSeconds?: number;
  save?: boolean;
  background?: boolean;
}

export interface ImportOutcome {
  valid: boolean;
  strategy: Record<string, unknown>;
  manifest: BundleManifest;
  issues: Array<{ code: string; message: string; path: string; severity: string }>;
  warnings: string[];
  contentHash: string;
  saved?: StrategyRecord;
}

export interface MetricDefinition {
  name: string;
  value: number | null;
  unit: string;
  definition: string;
  method?: string;
}

export interface ExperimentSummary {
  id: string;
  strategyId?: string | null;
  strategyVersion?: string | null;
  kind: string;
  symbols: string[];
  interval?: string | null;
  start?: string | null;
  end?: string | null;
  initialCapital?: number | null;
  seed?: number | null;
  engineVersion?: string | null;
  status: string;
  metrics: Record<string, number | null>;
  warnings: Array<{ code: string; message: string }>;
  createdAt: string;
  hasArtifact: boolean;
}

export interface EquityPoint {
  index: number;
  ts?: string | null;
  equity: number;
}

export interface DrawdownPoint {
  index: number;
  ts?: string | null;
  drawdown: number;
}

export interface TradeRow {
  id: string;
  symbol: string;
  direction: string;
  entryTs?: string | null;
  exitTs?: string | null;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  netPnl: number;
  pnlPct: number;
  barsHeld: number;
  exitReason?: string;
}

export interface BacktestResult {
  status: string;
  experimentId?: string | null;
  metadata: Record<string, unknown>;
  configuration: Record<string, unknown>;
  metrics: Record<string, number | null>;
  metricDefinitions?: Record<string, MetricDefinition>;
  warnings: Array<{ code: string; message: string }>;
  observability: Record<string, number>;
  capability: Record<string, string>;
  trades: TradeRow[];
  orders: Array<Record<string, unknown>>;
  fills: Array<Record<string, unknown>>;
  positions: Array<Record<string, unknown>>;
  equityCurve: EquityPoint[];
  drawdownCurve: DrawdownPoint[];
  exposure: Array<Record<string, number>>;
  monthlyReturns: Array<{ month: string; return: number; endEquity: number }>;
}

export interface RunBacktestInput {
  strategyId?: string;
  strategy?: Record<string, unknown>;
  symbols?: string[];
  start?: string;
  end?: string;
  initialCapital?: number;
  riskFreeRate?: number;
  randomSeed?: number;
  save?: boolean;
  background?: boolean;
}

export interface QuantRun {
  runId: string;
  kind: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  stage: string;
  done: number;
  total: number;
  percent: number;
  message: string;
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: { type: string; message: string } | null;
  result?: Record<string, unknown>;
}

export interface CapabilityMap {
  available: boolean;
  capability: Record<string, string>;
}

export interface TrialView {
  params: Record<string, unknown>;
  score: number | null;
  status: string;
  error?: string;
  metrics: Record<string, number | null>;
}

export interface WalkForwardWindow {
  train: { start: string; end: string };
  test: { start: string; end: string };
  bestParams: Record<string, unknown>;
  inSample: Record<string, number | null>;
  outOfSample: Record<string, number | null>;
}

export interface SensitivityParam {
  values: unknown[];
  scores: Array<number | null>;
  best: number | null;
  worst: number | null;
  collapse: boolean;
  nearBest: number;
  stable: boolean;
}

/** A research run (optimization / walk-forward / Monte-Carlo / sensitivity / robustness). */
export interface ResearchResult {
  status: string;
  kind: string;
  experimentId?: string | null;
  metrics: Record<string, number | null>;
  warnings: Array<{ code: string; message: string }>;
  observability: Record<string, number>;
  configuration: Record<string, unknown>;
  // optimization
  best?: TrialView | null;
  leaderboard?: TrialView[];
  stability?: Record<string, { bestValue: unknown; values: number; nearBest: number; stable: boolean }>;
  pareto?: Array<Record<string, unknown>>;
  // walk-forward
  windows?: WalkForwardWindow[];
  inSampleAggregate?: Record<string, number | null>;
  outOfSampleAggregate?: Record<string, number | null>;
  divergence?: Record<string, number | null>;
  // monte-carlo
  returnPercentiles?: Record<string, number>;
  probabilityOfLoss?: number;
  probabilityOfRuin?: number;
  expectedDrawdown?: number | null;
  worstDrawdown?: number | null;
  returnDistribution?: { bins: number[]; counts: number[] };
  // sensitivity / robustness
  parameters?: Record<string, SensitivityParam>;
  verdict?: string;
  conclusions?: string[];
  costSensitivity?: Array<{ multiplier: number; objective: number | null; totalReturn: number | null }>;
  regime?: Array<Record<string, unknown>>;
  concentration?: { topN: number; topShare: number | null; concentrated: boolean };
}

const BASE = "/api/backtest";

export interface ResearchRequest {
  strategyId: string;
  version?: string;
  symbols?: string[];
  start?: string;
  end?: string;
  initialCapital?: number;
  riskFreeRate?: number;
  seed?: number;
  save?: boolean;
  background?: boolean;
  // optimization / walk-forward
  method?: string;
  objective?: string;
  objectives?: string[];
  maxEvaluations?: number;
  paramSpace?: Record<string, unknown>;
  // walk-forward
  trainBars?: number;
  testBars?: number;
  stepBars?: number;
  anchored?: boolean;
  // monte-carlo
  simulations?: number;
  ruinThreshold?: number;
  perturbationPct?: number;
  perturbation?: Record<string, number>;
  executionPerturbation?: Record<string, number>;
  // sensitivity / robustness
  paramRanges?: Record<string, unknown>;
  costMultipliers?: number[];
  minTrades?: number;
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (payload as { error?: unknown; detail?: unknown }).error
      ?? (payload as { detail?: unknown }).detail;
    const message = typeof detail === "string" ? detail : `request failed (${res.status})`;
    throw new Error(message);
  }
  return payload as T;
}

export const backtestClient = {
  capabilities: () => jsonFetch<CapabilityMap>("/capabilities"),

  listStrategies: (includeArchived = false) =>
    jsonFetch<{ strategies: StrategySummary[] }>(
      `/strategies${includeArchived ? "?includeArchived=true" : ""}`,
    ).then((r) => r.strategies),

  getStrategy: (id: string, version?: string) =>
    jsonFetch<{ strategy: StrategyRecord }>(
      `/strategies/${encodeURIComponent(id)}${version ? `?version=${encodeURIComponent(version)}` : ""}`,
    ).then((r) => r.strategy),

  createStrategy: (strategy: Record<string, unknown>, description?: string) =>
    jsonFetch<{ strategy: StrategyRecord; issues: unknown[] }>("/strategies", {
      method: "POST",
      body: JSON.stringify({ strategy, description }),
    }),

  listVersions: (id: string) =>
    jsonFetch<{ versions: VersionInfo[] }>(
      `/strategies/${encodeURIComponent(id)}/versions`,
    ).then((r) => r.versions),

  getVersionMeta: (id: string, version: string) =>
    jsonFetch<VersionMeta>(
      `/strategies/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}`,
    ),

  diffVersions: (id: string, a: string, b: string) =>
    jsonFetch<VersionDiff>(
      `/strategies/${encodeURIComponent(id)}/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
    ),

  /** Download a strategy as a portable bundle zip. */
  exportStrategy: async (id: string, version?: string): Promise<Blob> => {
    const url = `${BASE}/strategies/${encodeURIComponent(id)}/export${
      version ? `?version=${encodeURIComponent(version)}` : ""}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`export failed (${res.status})`);
    return res.blob();
  },

  /** The portable bundle as JSON (manifest + canonical IR). */
  getBundle: (id: string, version?: string) =>
    jsonFetch<{ bundle: { manifest: BundleManifest; strategy: Record<string, unknown> } }>(
      `/strategies/${encodeURIComponent(id)}/export?format=json${
        version ? `&version=${encodeURIComponent(version)}` : ""}`,
    ).then((r) => r.bundle),

  /** Import a bundle as a decoded object, or a base64 zip string. */
  importStrategy: (bundle: Record<string, unknown> | string, save = false) =>
    jsonFetch<ImportOutcome>("/strategies/import", {
      method: "POST",
      body: JSON.stringify(
        typeof bundle === "string" ? { bundleBase64: bundle, save } : { bundle, save },
      ),
    }),

  researchPlan: (id: string, body: Record<string, unknown> = {}) =>
    jsonFetch<{ plan: Record<string, unknown> }>(
      `/strategies/${encodeURIComponent(id)}/research-plan`,
      { method: "POST", body: JSON.stringify(body) },
    ).then((r) => r.plan),

  report: (experimentId: string, artifact = true) =>
    jsonFetch<{ experimentId: string; format: string; report: string }>(
      `/experiments/${encodeURIComponent(experimentId)}/report${artifact ? "" : "?artifact=false"}`,
    ),

  signals: (input: RunBacktestInput) =>
    jsonFetch<Record<string, unknown>>("/signals", { method: "POST", body: JSON.stringify(input) }),

  runPythonStrategy: (input: PythonRunInput) =>
    jsonFetch<BacktestResult | { runId: string; status: string } | { status: string; error: unknown }>(
      "/python/run", { method: "POST", body: JSON.stringify(input) }),

  listGraphNodes: () =>
    jsonFetch<{ nodes: GraphNodeSpec[] }>("/graph/nodes").then((r) => r.nodes),

  compileGraph: (graph: StrategyGraph) =>
    jsonFetch<GraphCompileResult>("/graph/compile", {
      method: "POST",
      body: JSON.stringify({ graph }),
    }),

  validateGraph: (graph: StrategyGraph) =>
    jsonFetch<{ valid: boolean; diagnostics: GraphDiagnostic[] }>("/graph/validate", {
      method: "POST",
      body: JSON.stringify({ graph }),
    }),

  validateStrategy: (strategy: Record<string, unknown>) =>
    jsonFetch<{ valid: boolean; issues: Array<{ code: string; message: string; path: string }> }>(
      "/validate",
      { method: "POST", body: JSON.stringify({ strategy }) },
    ),

  runBacktest: (input: RunBacktestInput) =>
    jsonFetch<BacktestResult>("/backtest", { method: "POST", body: JSON.stringify(input) }),

  listExperiments: (strategyId?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (strategyId) params.set("strategyId", strategyId);
    params.set("limit", String(limit));
    return jsonFetch<{ experiments: ExperimentSummary[] }>(`/experiments?${params}`)
      .then((r) => r.experiments);
  },

  getExperiment: (id: string, artifact = false) =>
    jsonFetch<ExperimentSummary & { artifact?: BacktestResult }>(
      `/experiments/${encodeURIComponent(id)}${artifact ? "?artifact=true" : ""}`,
    ),

  getArtifact: (id: string) =>
    jsonFetch<BacktestResult>(`/experiments/${encodeURIComponent(id)}/artifact`),

  deleteExperiment: (id: string) =>
    jsonFetch<{ deleted: boolean }>(`/experiments/${encodeURIComponent(id)}`, { method: "DELETE" }),

  compare: (experimentIds: string[]) =>
    jsonFetch<{ metrics: string[]; experiments: Array<Record<string, unknown>> }>("/compare", {
      method: "POST",
      body: JSON.stringify({ experimentIds }),
    }),

  optimize: (body: ResearchRequest) =>
    jsonFetch<ResearchResult>("/optimize", { method: "POST", body: JSON.stringify(body) }),
  walkForward: (body: ResearchRequest) =>
    jsonFetch<ResearchResult>("/walk-forward", { method: "POST", body: JSON.stringify(body) }),
  monteCarlo: (body: ResearchRequest) =>
    jsonFetch<ResearchResult>("/monte-carlo", { method: "POST", body: JSON.stringify(body) }),
  sensitivity: (body: ResearchRequest) =>
    jsonFetch<ResearchResult>("/sensitivity", { method: "POST", body: JSON.stringify(body) }),
  robustness: (body: ResearchRequest) =>
    jsonFetch<ResearchResult>("/robustness", { method: "POST", body: JSON.stringify(body) }),

  listRuns: () => jsonFetch<{ runs: QuantRun[] }>("/runs").then((r) => r.runs),
  getRun: (runId: string, result = false) =>
    jsonFetch<QuantRun>(`/runs/${encodeURIComponent(runId)}${result ? "?result=true" : ""}`),
  cancelRun: (runId: string) =>
    jsonFetch<{ cancelled: boolean; runId: string }>(
      `/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
};

/** A metric's display value (formatted, with a unit-aware suffix). */
export function formatMetric(name: string, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const pct = /(return|drawdown|rate|volatility|exposure|deviation|var_|cvar_)/.test(name);
  const count = /(count|trades|streak|period)/.test(name);
  if (count) return String(Math.round(value));
  if (pct) return `${value.toFixed(2)}%`;
  if (/pf|factor|sharpe|sortino|calmar|omega|leverage/i.test(name)) return value.toFixed(2);
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return value.toFixed(2);
}

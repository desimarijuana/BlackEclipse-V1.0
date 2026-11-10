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

export interface PortfolioBacktestInput {
  strategyIds: string[];
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

/** One graded axis of the Edge Report. */
export interface EdgeVerdictComponent {
  score: number | null;
  basis: string;
  detail: string;
}

/** One flag the grader raised (a missing measurement, a warning, a failure). */
export interface EdgeVerdictFlag {
  code: string;
  severity: "critical" | "warning" | "info";
  message: string;
}

/** The Edge Verdict: the grade, the four axes behind it and the flags. */
export interface EdgeVerdict {
  available: boolean;
  grade: string;
  score: number;
  components: Record<string, EdgeVerdictComponent>;
  flags: EdgeVerdictFlag[];
  flagCounts: { critical: number; warning: number; info: number };
  summary: string;
  assumptions?: Record<string, unknown>;
}

/** One figure of the Edge Report, drawn by the runtime's chart engine. */
export interface EdgeReportChart {
  name: string;
  title: string;
  spec?: Record<string, unknown>;
  artifactId?: string | null;
  figure?: Record<string, unknown>;
  error?: { code: string; reason: string };
}

/**
 * The Edge Report: the verdict, the document and the figures as one record.
 *
 * The runtime builds it; the browser only shows what came back. The figures
 * live in the Artifact Center, so the report is a durable document rather than
 * a picture that evaporates with the tab.
 */
export interface EdgeReport {
  status: string;
  experimentId: string;
  monteCarloExperimentId?: string | null;
  verdict: EdgeVerdict;
  markdown: string;
  summary?: string;
  warnings: Array<{ code?: string; message: string }>;
  charts: EdgeReportChart[];
  reportArtifactId?: string | null;
}

/** Side-by-side experiment comparison from `POST /quant/compare`. */
export interface ExperimentComparison {
  metrics: string[];
  experiments: Array<{
    experimentId: string;
    kind?: string;
    symbols?: string[];
    interval?: string | null;
    start?: string | null;
    end?: string | null;
    initialCapital?: number | null;
    metrics: Record<string, number | null>;
  }>;
  comparability?: Array<{ code: string; message: string }>;
}

/** A stored strategy version's immutable metadata. */
export interface StrategyVersionMeta {
  version: string;
  contentHash: string;
  schemaVersion: string;
  createdAt: string;
}

/** One structural change between two strategy versions. */
export interface StrategyDiffChange {
  path: string;
  kind: "added" | "removed" | "changed";
  a?: unknown;
  b?: unknown;
}

export interface StrategyDiff {
  strategyId: string;
  a: string;
  b: string;
  sameContent: boolean;
  hashA?: string | null;
  hashB?: string | null;
  changeCount: number;
  bySection: Record<string, number>;
  changes: StrategyDiffChange[];
}

/** The result of validating/importing a portable strategy bundle. */
export interface ImportBundleResult {
  valid: boolean;
  strategy?: Record<string, unknown>;
  issues?: Array<{ code: string; message: string; path?: string }>;
  warnings?: string[];
  saved?: unknown;
}

/** A recorded paper shadow run (a real backtest over a paper window). */
export interface PaperRunRecord {
  id: string;
  deploymentId: string;
  strategyId: string;
  version: string;
  experimentId: string;
  status: string;
  symbols: string[];
  metrics: Record<string, number | null>;
  createdAt: string;
  liveExecution: boolean;
}

/** The deterministic research specification from `POST /strategies/{id}/research-plan`. */
export interface ResearchPlan {
  strategyId?: string;
  strategyVersion?: string;
  hypothesis?: string;
  assumptions?: string[];
  acceptanceCriteria?: string[];
  potentialBiases?: string[];
  benchmark?: string;
  parameterSearch?: {
    space?: Record<string, unknown>;
    objective?: string;
    maxEvaluations?: number;
    method?: string;
  };
  notFinancialAdvice?: boolean;
}

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

export interface RunManifest {
  schemaVersion?: string;
  digest: string;
  engineVersion?: string;
  codeVersion?: string | null;
  createdAt?: string;
  strategies?: Array<{ id?: string; version?: string; contentHash?: string; assetClass?: string | null }>;
  data?: {
    symbols?: string[];
    interval?: string | null;
    series?: Record<string, { bars?: number; sha256?: string; source?: string | null }>;
  };
  environment?: Record<string, unknown>;
  configuration?: Record<string, unknown>;
  metrics?: Record<string, number | null>;
  extra?: Record<string, unknown>;
}

export interface ReproduceResult {
  status: string;
  verdict: 'REPRODUCED' | 'DIVERGED';
  dataFingerprintMatch: boolean;
  comparison: {
    reproduced: boolean;
    compared: number;
    differences: Array<{ metric: string; expected?: unknown; actual?: unknown; delta?: number }>;
  };
}

export interface ResearchSession {
  id: string;
  title: string;
  question?: string | null;
  strategyId?: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
  hypotheses?: Array<Record<string, unknown>>;
  trials?: Array<Record<string, unknown>>;
  trialCount?: number;
}

export interface ResearchJournal {
  session: ResearchSession;
  hypothesisCount: number;
  trialCount: number;
  testedHypotheses: number;
  rejectedHypotheses: Array<Record<string, unknown>>;
  hypotheses: Array<Record<string, unknown>>;
  recentTrials: Array<Record<string, unknown>>;
  openQuestions: string[];
}

export interface PortfolioOptimization {
  method: string;
  weights: number[];
  expectedReturn: number | null;
  volatility: number | null;
  sharpe: number | null;
  riskContributions: { volatility: number; share: number[]; component: number[] };
  diagnostics: Record<string, unknown>;
}

export interface StressEnvelope {
  parametric?: {
    varPct: number; varAmount: number; expectedShortfallPct: number;
    componentVarShare: number[]; volatility: number; confidence: number;
  };
  historical?: { varPct: number; expectedShortfallPct: number; observations: number };
  scenario?: {
    scenarios: Array<{ name: string; pnlPct: number; pnlAmount: number; uncoveredSymbols: string[] }>;
    worst?: { name: string; pnlPct: number } | null;
  };
}

export interface MethodFamilySummary {
  id: string;
  name: string;
  category: string;
  thesis: string;
  edge_source: string;
  instruments: string[];
  horizons: string[];
  data_requirements: string[];
  signals: string[];
  failure_modes: string[];
  best_regimes: string[];
  worst_regimes: string[];
  validation: string;
  capacity: string;
  complexity: number;
  evidence: number;
  turnover: string;
  requires: string[];
}

export interface MethodRecommendation {
  methodId: string;
  name: string;
  category: string;
  fitScore: number;
  fitPercent: number;
  reasons: string[];
  warnings: string[];
  complexity: number;
  evidence: number;
  turnover: string;
  requires: string[];
}

export interface MethodRecommendationResult {
  profile: Record<string, unknown>;
  recommendations: MethodRecommendation[];
  starterSpec?: Record<string, unknown>;
  note: string;
}

export interface MarketStructure {
  structure: string;
  insights: string[];
  metrics: Record<string, unknown>;
  candidateMethods: Array<{ methodId: string; score: number; reason: string }>;
  outOfSampleStability?: { available: boolean; stable?: boolean; warning?: string };
  note: string;
}

export interface CurrentSetups {
  symbol: string;
  interval: string;
  bar?: string | null;
  setups: Array<{
    methodId: string;
    name?: string;
    direction: 'long' | 'short' | 'none' | 'error';
    reason: string;
  }>;
  active: Array<Record<string, unknown>>;
  note: string;
}

export interface MinedMethod {
  methodId: string;
  name?: string;
  params: Record<string, unknown>;
  status: 'candidate' | 'weak' | 'rejected' | 'error';
  score: number;
  reasons: string[];
  inSample?: Record<string, number | null>;
  outOfSample?: Record<string, number | null>;
}

export interface MineResult {
  symbol: string;
  interval: string;
  trialCount: number;
  isBars: number;
  oosBars: number;
  candidates: MinedMethod[];
  selected?: MinedMethod | null;
  rejectedCount: number;
  deflatedSharpe?: { available: boolean; deflatedSharpeRatio?: number; reason?: string };
  warnings: string[];
  note: string;
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

  validateStrategy: (strategy: Record<string, unknown>) =>
    jsonFetch<{ valid: boolean; issues: Array<{ code: string; message: string; path: string }> }>(
      "/validate",
      { method: "POST", body: JSON.stringify({ strategy }) },
    ),

  /** A deterministic research specification the copilot can execute and cite. */
  researchPlan: (strategyId: string, body: Record<string, unknown> = {}) =>
    jsonFetch<{ plan: ResearchPlan }>(
      `/strategies/${encodeURIComponent(strategyId)}/research-plan`,
      { method: "POST", body: JSON.stringify(body) },
    ).then((r) => r.plan),

  runBacktest: (input: RunBacktestInput) =>
    jsonFetch<BacktestResult>("/backtest", { method: "POST", body: JSON.stringify(input) }),

  /** Run several saved strategies together over one shared window. */
  portfolioBacktest: (input: PortfolioBacktestInput) =>
    jsonFetch<BacktestResult>("/portfolio-backtest", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listExperiments: (strategyId?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (strategyId) params.set("strategyId", strategyId);
    params.set("limit", String(limit));
    return jsonFetch<{ experiments: ExperimentSummary[] }>(`/experiments?${params}`)
      .then((r) => r.experiments);
  },

  listPaperRuns: (strategyId?: string) => {
    const params = new URLSearchParams();
    if (strategyId) params.set("strategyId", strategyId);
    const query = params.toString();
    return jsonFetch<{ paperRuns: PaperRunRecord[] }>(`/paper-runs${query ? `?${query}` : ""}`)
      .then((r) => r.paperRuns);
  },

  listVersions: (strategyId: string) =>
    jsonFetch<{ versions: StrategyVersionMeta[] }>(
      `/strategies/${encodeURIComponent(strategyId)}/versions`,
    ).then((r) => r.versions),

  diffVersions: (strategyId: string, a: string, b: string) =>
    jsonFetch<StrategyDiff>(
      `/strategies/${encodeURIComponent(strategyId)}/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
    ),

  /** The portable strategy bundle as JSON (the zip form is for download). */
  exportBundle: (strategyId: string, version?: string) =>
    jsonFetch<{ bundle: Record<string, unknown> }>(
      `/strategies/${encodeURIComponent(strategyId)}/export?format=json${version ? `&version=${encodeURIComponent(version)}` : ""}`,
    ).then((r) => r.bundle),

  /** Validate (and optionally save) a portable bundle. */
  importBundle: (bundle: Record<string, unknown>, save = true) =>
    jsonFetch<ImportBundleResult>("/strategies/import", {
      method: "POST",
      body: JSON.stringify({ bundle, save }),
    }),

  getExperiment: (id: string, artifact = false) =>
    jsonFetch<ExperimentSummary & { artifact?: BacktestResult }>(
      `/experiments/${encodeURIComponent(id)}${artifact ? "?artifact=true" : ""}`,
    ),

  getArtifact: (id: string) =>
    jsonFetch<BacktestResult>(`/experiments/${encodeURIComponent(id)}/artifact`),

  /** The content-hashed reproducibility record for an experiment. */
  getManifest: (id: string) =>
    jsonFetch<{ manifest: RunManifest }>(
      `/experiments/${encodeURIComponent(id)}/manifest`,
    ).then((r) => r.manifest),

  /** Re-run an experiment from its manifest and compare metrics + data hash. */
  reproduce: (id: string) =>
    jsonFetch<ReproduceResult>(
      `/experiments/${encodeURIComponent(id)}/reproduce`, { method: "POST" },
    ),

  // ── Research sessions ────────────────────────────────────────────────────
  createSession: (body: { title: string; question?: string; strategyId?: string }) =>
    jsonFetch<ResearchSession>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  listSessions: (limit = 50) =>
    jsonFetch<{ sessions: ResearchSession[] }>(`/sessions?limit=${limit}`)
      .then((r) => r.sessions),
  getJournal: (sessionId: string) =>
    jsonFetch<ResearchJournal>(`/sessions/${encodeURIComponent(sessionId)}/journal`),
  registerHypothesis: (sessionId: string, body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>(
      `/sessions/${encodeURIComponent(sessionId)}/hypotheses`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  recordTrial: (sessionId: string, body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>(
      `/sessions/${encodeURIComponent(sessionId)}/trials`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  // ── Portfolio, risk & stress ─────────────────────────────────────────────
  optimizePortfolio: (body: Record<string, unknown>) =>
    jsonFetch<PortfolioOptimization>("/portfolio/optimize", {
      method: "POST", body: JSON.stringify(body),
    }),
  portfolioRisk: (body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>("/portfolio/risk", {
      method: "POST", body: JSON.stringify(body),
    }),
  stress: (body: Record<string, unknown>) =>
    jsonFetch<StressEnvelope>("/stress", { method: "POST", body: JSON.stringify(body) }),

  // ── Asset-class extensions ───────────────────────────────────────────────
  optionChainBacktest: (body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>("/options/backtest-chain", {
      method: "POST", body: JSON.stringify(body),
    }),
  futuresTermStructure: (body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>("/futures/term-structure", {
      method: "POST", body: JSON.stringify(body),
    }),
  futuresRollCost: (body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>("/futures/roll-cost", {
      method: "POST", body: JSON.stringify(body),
    }),
  benchmark: (answers: Record<string, unknown> = {}) =>
    jsonFetch<Record<string, unknown>>("/benchmark", {
      method: "POST", body: JSON.stringify({ answers }),
    }),

  // ── Method discovery ─────────────────────────────────────────────────────
  listMethodFamilies: (query = "") =>
    jsonFetch<{ methods: MethodFamilySummary[] }>(`/methods${query}`)
      .then((r) => r.methods),
  getMethodCard: (methodId: string, symbol?: string, interval = '1d') => {
    const params = new URLSearchParams();
    if (symbol) params.set('symbol', symbol);
    params.set('interval', interval);
    return jsonFetch<MethodFamilySummary & { playbook?: Record<string, unknown>; exampleSpec?: Record<string, unknown> }>(
      `/methods/${encodeURIComponent(methodId)}?${params.toString()}`,
    );
  },
  recommendMethods: (body: Record<string, unknown>) =>
    jsonFetch<MethodRecommendationResult>("/methods/recommend", {
      method: "POST", body: JSON.stringify(body),
    }),
  scanStructure: (body: Record<string, unknown>) =>
    jsonFetch<MarketStructure>("/methods/scan-structure", {
      method: "POST", body: JSON.stringify(body),
    }),
  methodHypotheses: (body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>("/methods/hypotheses", {
      method: "POST", body: JSON.stringify(body),
    }),
  synthesizeMethod: (body: Record<string, unknown>) =>
    jsonFetch<{ methodId: string; spec: Record<string, unknown>; valid: boolean; issues: Array<{ code: string; message: string }> }>(
      "/methods/synthesize", { method: "POST", body: JSON.stringify(body) },
    ),
  combineMethods: (body: Record<string, unknown>) =>
    jsonFetch<{ spec: Record<string, unknown> }>("/methods/combine", {
      method: "POST", body: JSON.stringify(body),
    }),
  mineMethods: (body: Record<string, unknown>) =>
    jsonFetch<MineResult>("/methods/mine", {
      method: "POST", body: JSON.stringify(body),
    }),
  currentSetups: (body: Record<string, unknown>) =>
    jsonFetch<CurrentSetups>("/methods/setups", {
      method: "POST", body: JSON.stringify(body),
    }),
  saveDiscoveredMethod: (body: Record<string, unknown>) =>
    jsonFetch<Record<string, unknown>>("/discovered-methods", {
      method: "POST", body: JSON.stringify(body),
    }),
  listDiscoveredMethods: (status?: string) =>
    jsonFetch<{ methods: Array<Record<string, unknown>> }>(
      `/discovered-methods${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    ).then((r) => r.methods),
  exportReport: (experimentId: string, format: 'html' | 'notebook' = 'html') =>
    jsonFetch<{ format: string; path: string; mimeType: string; content: string }>(
      `/experiments/${encodeURIComponent(experimentId)}/report/export`,
      { method: "POST", body: JSON.stringify({ format }) },
    ),

  /** Build the Edge Report for one experiment (and optionally a Monte-Carlo). */
  edgeReport: (input: { experimentId: string; monteCarloExperimentId?: string }) =>
    jsonFetch<EdgeReport>("/edge-report", {
      method: "POST",
      body: JSON.stringify({ renderCharts: true, ...input }),
    }),

  deleteExperiment: (id: string) =>
    jsonFetch<{ deleted: boolean }>(`/experiments/${encodeURIComponent(id)}`, { method: "DELETE" }),

  compare: (experimentIds: string[]) =>
    jsonFetch<ExperimentComparison>("/compare", {
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

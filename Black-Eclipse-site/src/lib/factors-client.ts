// Typed client for the Factor & Alpha Research Lab front door (/api/factors).
//
// The Python harness owns every computation; this module only shapes requests
// and responses so the UI can stay type-safe.

const BASE = "/api/factors";

export interface FactorRecord {
  id: string;
  name: string;
  description: string | null;
  family: string;
  direction: string | null;
  frequency: string;
  latestVersion: string;
  validationStatus: string;
  tags: string[];
  builtIn?: boolean;
}

export interface FactorVersion {
  factorId: string;
  version: string;
  expression: string;
  inputs: string[];
  normalization: string;
  lookback: number;
  definitionHash: string | null;
  changelog: string | null;
  createdAt: string;
}

export interface LibraryFactor {
  name: string;
  family: string;
  description: string;
  expression: string;
  direction?: string;
  lookback: number;
  inputs: string[];
  available: boolean;
  unavailableReason?: string;
}

export interface IcSummary {
  available?: boolean;
  reason?: string;
  meanIC?: number | null;
  stdIC?: number | null;
  informationRatio?: number | null;
  annualizedInformationRatio?: number | null;
  hitRate?: number | null;
  averageCrossSectionSize?: number | null;
  hac?: { available?: boolean; tStatistic?: number | null; pValue?: number | null; n?: number };
}

export interface IcBlock {
  series: (number | null)[];
  counts: number[];
  summary: IcSummary;
}

export interface DecayPoint {
  horizon: number;
  meanIC: number | null;
  informationRatio: number | null;
  hitRate: number | null;
  validPeriods?: number;
}

export interface EvaluationResult {
  horizons: number[];
  method: string;
  symbols: string[];
  dates: string[];
  coverage: number;
  observations: number;
  warnings: string[];
  ic: IcBlock;
  rankIC: IcBlock;
  decay: { method: string; curve: DecayPoint[]; decaySlope: number | null };
}

export interface PortfolioResult {
  quantiles: number;
  weighting: string;
  rebalance: number;
  longShort: boolean;
  costBps: number;
  periodsPerYear: number;
  turnover: { average: number | null; annualized: number | null };
  cost: { costBps: number; totalCost: number };
  quantileMetrics: Record<string, { available: boolean; totalReturn?: number; sharpe?: number | null; maxDrawdown?: number; hitRate?: number }>;
  longShortMetrics?: { available: boolean; totalReturn?: number; annualizedReturn?: number | null; sharpe?: number | null; maxDrawdown?: number; hitRate?: number };
  grossLongShortMetrics?: { available: boolean; totalReturn?: number; sharpe?: number | null };
  finalWeights: { instrument: number; weight: number }[];
  observations: number;
  warnings: string[];
}

export interface ValidationCheck {
  name: string;
  status: string;
  method: string;
  result: unknown;
  failureReason: string | null;
  severity: string;
}

export interface ValidationResult {
  outcome: string;
  validated: boolean;
  checks: ValidationCheck[];
  note: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (payload as { detail?: { message?: string }; error?: string }).detail;
    const message = detail?.message ?? (payload as { error?: string }).error ?? `HTTP ${res.status}`;
    throw new Error(message);
  }
  return payload as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const factorsClient = {
  capabilities: () => request<{ available: boolean; engineVersion: string }>("capabilities"),
  library: (availableOnly = false) =>
    request<{ library: LibraryFactor[] }>(`library?availableOnly=${availableOnly ? "true" : "false"}`),
  listFactors: (family?: string) =>
    request<{ factors: FactorRecord[] }>(`factors${family ? `?family=${encodeURIComponent(family)}` : ""}`),
  getFactor: (id: string, includeVersions = false) =>
    request<FactorRecord & { versions?: FactorVersion[] }>(`factors/${encodeURIComponent(id)}?includeVersions=${includeVersions}`),
  createFactor: (body: {
    factorId?: string;
    name: string;
    description?: string;
    family?: string;
    direction?: string;
    expression: string;
    inputs?: string[];
    lookback?: number;
    bump?: string;
  }) => post<{ factor: FactorRecord; version: FactorVersion; validation: { valid: boolean; variables: string[]; errors: unknown[] } }>("factors", body),
  validate: (body: { expression: string; sample?: Record<string, number[]> }) =>
    post<{ valid: boolean; variables: string[]; functions: string[]; coverage: number | null; errors: { code: string; message: string }[] }>("validate", body),
  evaluate: (body: { expression: string; symbols: string[]; horizons?: number[]; method?: string; interval?: string }) =>
    post<EvaluationResult>("evaluate", body),
  portfolio: (body: {
    expression: string;
    symbols: string[];
    quantiles?: number;
    weighting?: string;
    longShort?: boolean;
    rebalance?: number;
    costBps?: number;
  }) => post<PortfolioResult>("portfolio", body),
  compose: (body: { factors: { expression: string }[]; symbols: string[]; method?: string; weights?: number[] }) =>
    post<Record<string, unknown>>("compose", body),
  experiments: (limit = 50) => request<{ experiments: unknown[] }>(`experiments?limit=${limit}`),
};

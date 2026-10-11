// Typed client for the ML Research Lab front door (/api/ml).
//
// The Python harness owns every computation; this module only shapes requests
// and responses so the UI stays type-safe. It never holds state.

const BASE = "/api/ml";

export interface ModelCapability {
  family: string;
  available: boolean;
  tasks: string[];
  tier: "native" | "optional";
  reason: string | null;
}

export interface Capabilities {
  available: boolean;
  models: ModelCapability[];
}

export interface QualityFinding {
  code: string;
  severity: "info" | "warning" | "critical";
  message: string;
  detail: Record<string, unknown>;
}

export interface QualityReport {
  ok: boolean;
  findings: QualityFinding[];
  summary: Record<string, unknown>;
}

export interface DatasetRecord {
  id: string;
  name: string;
  description: string | null;
  assetClass: string;
  versions: number;
  createdAt: string;
  updatedAt: string;
}

export interface DatasetVersion {
  datasetId: string;
  version: string;
  rows: number;
  featureCount: number;
  coverage: number;
  qualityStatus: string;
  dataHash: string | null;
  createdAt: string;
  manifest: Record<string, unknown>;
}

export interface BuildDatasetResult {
  datasetId: string;
  version: string;
  artifactId: string;
  dataHash: string;
  quality: QualityReport;
  manifest: Record<string, unknown>;
  durationMs: number;
}

export interface ExperimentRecord {
  id: string;
  title: string;
  datasetId: string;
  datasetVersion: string;
  modelFamily: string;
  task: string | null;
  status: string;
  runs: number;
  createdAt: string;
}

export interface FoldResult {
  fold: number;
  status: string;
  nTrain: number;
  nTest: number;
  nPurged: number;
  nEmbargoed: number;
  metrics: Record<string, unknown>;
}

export interface RunRecord {
  id: string;
  experimentId: string;
  status: string;
  stage: string | null;
  metrics: Record<string, unknown>;
  error: { code: string; message: string } | null;
  artifactId: string | null;
  folds: FoldResult[];
  durationMs: number | null;
  createdAt: string;
  result?: RunResult | null;
}

export interface RunResult {
  task: string;
  modelFamily: string;
  folds: { index: number; status: string; nTrain: number; nTest: number; nPurged: number; nEmbargoed: number; metrics: Record<string, unknown> }[];
  pooledMetrics: Record<string, unknown>;
  foldMetricsMean: Record<string, unknown>;
  foldMetricsStd: Record<string, unknown>;
  finalEvaluation: Record<string, unknown>;
  finalFeatureImportance: Record<string, number> | null;
  dependencyVersions: Record<string, string>;
}

export interface ModelRecord {
  id: string;
  name: string;
  family: string;
  status: string;
  latestVersion: string;
  versions: number;
  updatedAt: string;
}

export interface ModelVersion {
  modelId: string;
  name: string;
  family: string;
  status: string;
  version: string;
  task: string;
  sha256: string;
  signature: Record<string, unknown>;
  metrics: Record<string, unknown>;
  approvals: { action: string; actor: string | null; reason: string | null; createdAt: string }[];
}

export interface ExperimentRunResult {
  experimentId: string;
  runId: string;
  artifactId: string;
  status: string;
  result: RunResult;
  registered: { modelId: string; version: string } | null;
}

export interface ReproduceResult {
  runId: string;
  reproduced: boolean;
  withinTolerance: boolean;
  metricDiffs: { metric: string; original: unknown; reproduced: unknown; delta: number | null; within: boolean }[];
}

export interface JobRecord {
  jobId: string;
  type?: string;
  queue?: string;
  status: string;
  progress?: number;
  attempts?: number;
  error?: string | null;
  errorClass?: string | null;
  output?: {
    status?: string;
    experimentId?: string;
    runId?: string;
    artifactId?: string;
    pooledMetrics?: Record<string, unknown>;
    finalEvaluation?: Record<string, unknown>;
    registered?: { modelId: string; version: string } | null;
  } | null;
}

export interface BackgroundRunResult {
  background: true;
  job: { jobId: string; status: string; mode: string };
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

export const mlClient = {
  capabilities: () => request<Capabilities>("capabilities"),
  listDatasets: () => request<{ datasets: DatasetRecord[] }>("datasets"),
  buildDataset: (body: Record<string, unknown>) => post<BuildDatasetResult>("datasets", body),
  listDatasetVersions: (datasetId: string) =>
    request<{ versions: DatasetVersion[] }>(`datasets/${encodeURIComponent(datasetId)}/versions`),
  getDatasetVersion: (datasetId: string, version: string) =>
    request<{ datasetId: string; version: string; dataHash: string; manifest: Record<string, unknown> }>(
      `datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(version)}`,
    ),
  listExperiments: () => request<{ experiments: ExperimentRecord[] }>("experiments"),
  runExperiment: (body: Record<string, unknown>) => post<ExperimentRunResult>("experiments", body),
  runExperimentBackground: (body: Record<string, unknown>) =>
    post<BackgroundRunResult>("experiments", { ...body, background: true }),
  listJobs: () => request<{ jobs: JobRecord[] }>("jobs"),
  getJob: (jobId: string) => request<{ job: JobRecord }>(`jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) => post<{ cancellation: unknown }>(`jobs/${encodeURIComponent(jobId)}/cancel`, {}),
  listRuns: (experimentId: string) =>
    request<{ runs: RunRecord[] }>(`experiments/${encodeURIComponent(experimentId)}/runs`),
  getRun: (runId: string) => request<{ run: RunRecord }>(`runs/${encodeURIComponent(runId)}`),
  reproduceRun: (runId: string) => post<ReproduceResult>(`runs/${encodeURIComponent(runId)}/reproduce`, {}),
  listModels: () => request<{ models: ModelRecord[] }>("models"),
  registerModel: (body: { runId: string; name?: string; owner?: string }) =>
    post<{ modelId: string; version: string }>("models/register", body),
  getModel: (modelId: string, version?: string) =>
    request<ModelVersion>(`models/${encodeURIComponent(modelId)}${version ? `?version=${encodeURIComponent(version)}` : ""}`),
  transitionModel: (modelId: string, body: { version: string; action: string; actor?: string; reason?: string }) =>
    post<ModelVersion>(`models/${encodeURIComponent(modelId)}/transition`, body),
  verifyModel: (modelId: string, version?: string) =>
    request<{ modelId: string; version: string; ok: boolean; expected: string; actual: string }>(
      `models/${encodeURIComponent(modelId)}/verify${version ? `?version=${encodeURIComponent(version)}` : ""}`,
    ),
  predict: (modelId: string, body: { features: number[][]; version?: string }) =>
    post<{ modelId: string; version: string; task: string; pred: (number | null)[]; proba: number[][] | null }>(
      `models/${encodeURIComponent(modelId)}/predict`,
      body,
    ),
};

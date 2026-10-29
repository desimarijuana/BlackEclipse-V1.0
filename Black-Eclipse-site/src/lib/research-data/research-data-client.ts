// Client for the Python research-data API (proxied through /api/research-data).
// All state lives in the runtime; this module only shapes requests/responses.

export interface VerificationPolicy {
  name: string;
  requireVerification: boolean;
  minSources: number;
  maxAgeSeconds: number | null;
  failOnMaterialConflict: boolean;
  allowSingleSource: boolean;
  requireAuthoritative: boolean;
  description: string;
}

export interface ProviderDescriptor {
  id: string;
  label: string;
  capabilities: string[];
  assetTypes: string[];
  realtime: boolean;
  historical: boolean;
  streaming: boolean;
  credentialRef: string | null;
  configured: boolean | null;
  implemented: boolean;
  timeliness: string;
  entitlement: string;
  intervals: string[];
  adjustments: boolean;
  rateLimit: Record<string, unknown>;
}

export interface DatasetSummary {
  id: string;
  name: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
  versions: number;
}

export interface DatasetManifest {
  datasetId: string;
  version: string;
  name: string;
  contentHash: string;
  createdAt: string;
  immutable: boolean;
  request: Record<string, unknown>;
  coverage: {
    symbols: string[];
    symbolCount: number;
    rowCount: number;
    perSymbolRows: Record<string, number>;
    start: string | null;
    end: string | null;
  };
  quality: Record<string, unknown>;
  lineage: Record<string, unknown>;
}

export interface QualityEvent {
  id: number;
  capability: string;
  symbol: string | null;
  provider: string | null;
  kind: string;
  severity: string;
  detail: string;
  createdAt: string;
}

export interface StoredSeries {
  symbol: string;
  interval: string;
  adjusted: number;
  provider: string;
  n: number;
  start: string | null;
  end: string | null;
}

const BASE = "/api/research-data";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (payload as { detail?: unknown }).detail;
    throw new Error(
      typeof detail === "string" ? detail : (payload as { error?: string }).error ?? `HTTP ${res.status}`,
    );
  }
  return payload as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return jsonFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const researchDataClient = {
  policies: () => jsonFetch<{ policies: VerificationPolicy[] }>("/policies"),
  providers: () => jsonFetch<{ providers: ProviderDescriptor[] }>("/providers"),
  health: () => jsonFetch<{ health: unknown[]; metrics: unknown }>("/health"),
  calendar: (market: string, year?: number) =>
    jsonFetch<{ market: string; openNow: boolean; nextOpen: string | null; holidays: string[] }>(
      `/calendar?market=${encodeURIComponent(market)}${year ? `&year=${year}` : ""}`,
    ),
  quality: (limit = 50) =>
    jsonFetch<{ events: QualityEvent[]; storedSeries: StoredSeries[] }>(`/quality?limit=${limit}`),
  /**
   * The stored-series catalogue (symbol, interval, bar count, range, provider).
   * `null` means the runtime could not answer — distinct from "no series".
   */
  storedSeries: async (limit = 200): Promise<StoredSeries[] | null> => {
    const payload = await jsonFetch<{ available?: boolean; series?: StoredSeries[] }>(
      `/series?limit=${limit}`,
    );
    if (payload.available === false) return null;
    return payload.series ?? [];
  },
  datasets: (limit = 100) => jsonFetch<{ datasets: DatasetSummary[] }>(`/datasets?limit=${limit}`),
  manifest: (datasetId: string, version?: string) =>
    jsonFetch<{ manifest: DatasetManifest }>(
      `/datasets/${encodeURIComponent(datasetId)}${version ? `?version=${encodeURIComponent(version)}` : ""}`,
    ),
  versions: (datasetId: string) =>
    jsonFetch<{ versions: Array<{ version: string; contentHash: string; createdAt: string }>; latest: DatasetManifest }>(
      `/datasets/${encodeURIComponent(datasetId)}/versions`,
    ),
  build: (body: {
    symbols: string[];
    interval?: string;
    start?: string;
    end?: string;
    adjusted?: boolean;
    verification_policy?: string;
    name?: string;
    dataset_id?: string;
  }) => post<{ status: string; manifest: DatasetManifest }>("/datasets/build", body),
  analyze: (datasetId: string, body: { operations: string[]; symbol?: string }) =>
    post<{ status: string; results: Record<string, unknown> }>(
      `/datasets/${encodeURIComponent(datasetId)}/analyze`,
      body,
    ),
  exportDataset: (datasetId: string, body: { format?: string; as_of?: string }) =>
    post<{ status: string; files: string[]; rowCount: number }>(
      `/datasets/${encodeURIComponent(datasetId)}/export`,
      body,
    ),
  refresh: (datasetId: string) =>
    post<{ status: string; manifest: DatasetManifest }>(
      `/datasets/${encodeURIComponent(datasetId)}/refresh`,
      {},
    ),
  marketData: (body: { symbols: string[]; interval?: string; start?: string; end?: string; verification_policy?: string }) =>
    post<{ status: string; results: unknown[] }>("/market-data", body),
  verify: (body: { symbols: string[]; policy?: string }) =>
    post<{ status: string; outcomes: unknown[] }>("/verify", body),
  execute: (datasetId: string, body: { code: string; version?: string; timeout_seconds?: number }) =>
    post<{ status: string; output: string; exitCode: number | null; timedOut: boolean; durationMs: number; rows: number }>(
      `/datasets/${encodeURIComponent(datasetId)}/execute`,
      body,
    ),
  fundamentals: (symbol: string) =>
    post<{ status: string; fundamentals?: Record<string, unknown> }>("/fundamentals", { symbol }),
  macro: (seriesId: string, quantity?: number) =>
    post<{ status: string; macro?: Record<string, unknown> }>("/macro", { series_id: seriesId, quantity }),
};

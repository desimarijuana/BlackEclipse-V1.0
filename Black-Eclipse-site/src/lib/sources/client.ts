// ── Sources client ───────────────────────────────────────────────────────────
// Typed wrappers over `/api/sources/*`, which proxies the Python `/sources`
// routes. Nothing here reads a file: the UI only ever receives bounded cards,
// search hits and read windows.

export interface SourceRoot {
  id: string;
  path: string;
  label: string;
  created_at: string;
  last_scan_at: string | null;
  file_count: number;
  total_bytes: number;
  status: string;
  error: string | null;
}

export interface SourceFile {
  id: number;
  root_id: string;
  relpath: string;
  name: string;
  ext: string;
  size: number;
  mtime: number;
  klass: string;
  magic: string | null;
  indexed_at: string | null;
  chunk_count: number;
  scanned_at: string | null;
  root_path: string;
}

export interface SourceColumn {
  name: string;
  type?: string;
}

export interface SourceCard {
  path: string;
  name: string;
  klass: string;
  size: number;
  mtime: number;
  magic: string | null;
  head: string;
  tail: string;
  truncated: boolean;
  columns: SourceColumn[];
  rows_hint: number | null;
  delimiter: string | null;
  pages: number | null;
  width: number | null;
  height: number | null;
  duration_s: number | null;
  entries: number | null;
  indexed: boolean;
  chunks: number;
  index_state: string;
  warnings: string[];
}

export interface SourceHit {
  root_id: string;
  relpath: string;
  name: string;
  klass: string;
  size: number;
  mtime: number;
  score: number;
  engine: string;
  snippet: string | null;
  line: number | null;
  offset: number | null;
  page: number | null;
  chunk_id: number | null;
}

export interface SourceSearchResult {
  query: string;
  plan: {
    mode: string;
    engines: string[];
    reason: string;
    candidates: number;
    budget_bytes: number;
    budget_seconds: number;
  };
  hits: SourceHit[];
  scannedFiles: number;
  scannedBytes: number;
  elapsedMs: number;
  truncated: boolean;
  warnings: string[];
}

export interface SourceStats {
  roots: SourceRoot[];
  files: number;
  bytes: number;
  indexedFiles: number;
  chunks: number;
  fts: boolean;
  classes: Record<string, { files: number; bytes: number }>;
  semantic: { available: boolean; reason: string };
}

export interface ScanState {
  rootId: string;
  running: boolean;
  status?: string;
  filesSeen?: number;
  added?: number;
  updated?: number;
  unchanged?: number;
  removed?: number;
  bytesSeen?: number;
  elapsedMs?: number;
  truncated?: boolean;
  error?: string | null;
  root?: SourceRoot | null;
}

export interface SourceOpenResult {
  root: SourceRoot;
  file: SourceFile;
  card: SourceCard;
}

export interface ReadWindowResult {
  relpath: string;
  name: string;
  klass: string;
  offset: number;
  requested: number;
  read: number;
  eof: boolean;
  truncated: boolean;
  text?: string;
  bytesBase64?: string;
}

export interface SqlResult {
  ok: boolean;
  sql: string;
  source: string | null;
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
  bytes_read: number | null;
  error: string | null;
}

export interface IndexResult {
  indexed: number;
  skipped: number;
  chunks: number;
  bytes: number;
  reasons: Record<string, number>;
  elapsedMs: number;
  unindexed?: number;
  semantic?: { available: boolean; reason?: string; embedded?: number; model?: string };
}

export class SourceApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/sources${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: { code?: string; message?: string }; error?: string }).detail;
    const message =
      (detail && typeof detail === "object" ? detail.message : undefined) ||
      (body as { error?: string }).error ||
      `Request failed (${res.status})`;
    throw new SourceApiError(message, detail?.code ?? "REQUEST_FAILED", res.status);
  }
  return body as T;
}

export function listRoots(): Promise<{ roots: SourceRoot[] }> {
  return request("/roots");
}

export function addRoot(path: string, label?: string): Promise<{ root: SourceRoot }> {
  return request("/roots", { method: "POST", body: JSON.stringify({ path, label }) });
}

export function removeRoot(rootId: string): Promise<{ removed: boolean }> {
  return request(`/roots/${encodeURIComponent(rootId)}`, { method: "DELETE" });
}

export function startScan(rootId: string): Promise<{ scan: ScanState }> {
  return request(`/roots/${encodeURIComponent(rootId)}/scan`, { method: "POST" });
}

export function scanStatus(rootId: string): Promise<{ scan: ScanState }> {
  return request(`/roots/${encodeURIComponent(rootId)}/scan`);
}

export function cancelScans(): Promise<{ cancelled: boolean }> {
  return request("/scan/cancel", { method: "POST" });
}

export function sourceStats(): Promise<SourceStats> {
  return request("/stats");
}

export function listFiles(
  rootId: string,
  prefix = "",
  limit = 200,
): Promise<{ root: SourceRoot; prefix: string; files: SourceFile[]; truncated: boolean }> {
  const params = new URLSearchParams({ rootId, prefix, limit: String(limit) });
  return request(`/list?${params.toString()}`);
}

export function openSource(args: {
  rootId?: string | null;
  relpath?: string | null;
  path?: string | null;
}): Promise<SourceOpenResult> {
  return request("/open", {
    method: "POST",
    body: JSON.stringify({
      rootId: args.rootId ?? null,
      relpath: args.relpath ?? null,
      path: args.path ?? null,
    }),
  });
}

export function readWindow(args: {
  rootId?: string | null;
  relpath?: string | null;
  path?: string | null;
  offset?: number;
  length?: number;
}): Promise<ReadWindowResult> {
  return request("/read", { method: "POST", body: JSON.stringify(args) });
}

export function searchSources(args: {
  query: string;
  mode?: "auto" | "metadata" | "text" | "raw" | "similar";
  rootIds?: string[];
  klass?: string;
  pathPrefix?: string;
  limit?: number;
}): Promise<SourceSearchResult> {
  return request("/search", { method: "POST", body: JSON.stringify(args) });
}

export function runSourceSql(args: {
  sql: string;
  rootId?: string | null;
  relpath?: string | null;
  path?: string | null;
  maxRows?: number;
  allRootFiles?: boolean;
}): Promise<SqlResult> {
  return request("/sql", { method: "POST", body: JSON.stringify(args) });
}

export function indexSources(args: {
  rootIds?: string[];
  limitFiles?: number;
  budgetS?: number;
  semantic?: boolean;
}): Promise<IndexResult> {
  return request("/index", { method: "POST", body: JSON.stringify(args) });
}

export function humanBytes(size: number): string {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let value = Number(size) || 0;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${value.toFixed(0)} B` : `${value.toFixed(1)} ${units[unit]}`;
}

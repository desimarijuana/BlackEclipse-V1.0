// Unified Search client — thin front-door proxy to the Python `/search/*`
// operator routes. No state, no store.

import type {
  EmbeddingResolution,
  SearchAdminStats,
  SearchDocumentRow,
  SearchEventRow,
  SearchQueryBody,
  SearchResult,
} from "./search-types";

const BASE = "/api/harness/search";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path ? `/${path}` : ""}`, { cache: "no-store" });
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path ? `/${path}` : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return (await res.json()) as T;
}

export function fetchSearchHealth(): Promise<{ available: boolean; ok?: boolean; embeddingAvailable?: boolean; reason?: string }> {
  return getJson("health");
}

export function fetchSearchStats(): Promise<SearchAdminStats> {
  return getJson("stats");
}

export function fetchSearchModels(): Promise<Record<string, unknown>> {
  return getJson("models");
}

export function fetchSearchEvents(limit = 50, kind?: string): Promise<{ success: boolean; events: SearchEventRow[] }> {
  const query = kind ? `?limit=${limit}&kind=${encodeURIComponent(kind)}` : `?limit=${limit}`;
  return getJson(`events${query}`);
}

export function listSearchDocuments(params: { namespace?: string; state?: string; limit?: number } = {}): Promise<{ success: boolean; documents: SearchDocumentRow[] }> {
  const search = new URLSearchParams();
  if (params.namespace) search.set("namespace", params.namespace);
  if (params.state) search.set("state", params.state);
  search.set("limit", String(params.limit ?? 50));
  return getJson(`documents?${search.toString()}`);
}

export function deleteSearchDocument(documentId: string): Promise<{ success: boolean }> {
  return fetch(`${BASE}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" }).then((r) => r.json());
}

export async function runSearch(body: SearchQueryBody): Promise<{ success: boolean; result: SearchResult }> {
  return postJson("", body);
}

export async function debugSearch(body: SearchQueryBody): Promise<{ success: boolean; trace: Record<string, unknown> }> {
  return postJson("debug", body);
}

export async function bulkIndexSearch(namespaces?: string[]): Promise<{ success: boolean; summary: Record<string, unknown> }> {
  return postJson("index", { namespaces: namespaces ?? null });
}

export async function reindexSearchDocument(documentId: string, reembed = false): Promise<{ success: boolean; result: Record<string, unknown> }> {
  return postJson(`reindex/${encodeURIComponent(documentId)}?reembed=${reembed}`, {});
}

export interface EmbeddingStatusResponse {
  success: boolean;
  resolution: EmbeddingResolution;
  savedConfig: Record<string, unknown>;
  reindexScheduled?: boolean;
  vectorSpaceChanged?: boolean;
  ok?: boolean;
  reason?: string;
  dimensions?: number;
  elapsedMs?: number;
}

export function applySearchEmbedding(body: {
  provider: string;
  model?: string;
  dimensions?: number;
  reindex?: boolean;
}): Promise<EmbeddingStatusResponse> {
  return postJson("embedding/apply", body);
}

export function clearSearchEmbedding(): Promise<EmbeddingStatusResponse> {
  return postJson("embedding/clear", {});
}

export function testSearchEmbedding(): Promise<EmbeddingStatusResponse> {
  return postJson("embedding/test", {});
}

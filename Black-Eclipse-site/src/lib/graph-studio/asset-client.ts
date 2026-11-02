// SERVER-ONLY: front door for the graph asset store.
//
// The browser uploads a file to the Next route; this module forwards the raw
// bytes to the Python runtime, which owns the bounded store. No file content is
// parsed or persisted on the Next side.

import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { HarnessRuntimeUnavailable } from "@/lib/harness/python-client";

export interface GraphAssetMeta {
  assetId: string;
  ref: string;
  name: string;
  mime: string;
  bytes: number;
  sha256: string;
  createdAt: string;
  expiresAt: string | null;
}

async function runtimeFetch(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<Response> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const { timeoutMs = 120_000, ...rest } = init;
  const operatorToken = runtimeCallbackToken();
  return fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: {
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(rest.headers ?? {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function readError(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({} as Record<string, unknown>));
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return `runtime returned ${res.status}`;
}

export async function uploadGraphAsset(
  name: string,
  mime: string,
  bytes: ArrayBuffer,
): Promise<GraphAssetMeta> {
  const query = new URLSearchParams({ name, mime, owner: "local" });
  const res = await runtimeFetch(`/graph/assets?${query.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: bytes,
    timeoutMs: 60_000,
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as GraphAssetMeta;
}

export async function listGraphAssets(limit = 100): Promise<GraphAssetMeta[]> {
  const res = await runtimeFetch(`/graph/assets?limit=${limit}&owner=local`, {
    method: "GET",
    timeoutMs: 30_000,
  });
  if (!res.ok) throw new Error(await readError(res));
  const body = (await res.json()) as { assets?: GraphAssetMeta[] };
  return Array.isArray(body.assets) ? body.assets : [];
}

export async function getGraphAsset(assetId: string): Promise<GraphAssetMeta> {
  const res = await runtimeFetch(`/graph/assets/${encodeURIComponent(assetId)}?owner=local`, {
    method: "GET",
    timeoutMs: 30_000,
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as GraphAssetMeta;
}

export async function getGraphAssetContent(
  assetId: string,
): Promise<{ bytes: ArrayBuffer; mime: string; name: string }> {
  const res = await runtimeFetch(`/graph/assets/${encodeURIComponent(assetId)}/content?owner=local`, {
    method: "GET",
    timeoutMs: 60_000,
  });
  if (!res.ok) throw new Error(await readError(res));
  const bytes = await res.arrayBuffer();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return {
    bytes,
    mime: res.headers.get("content-type") ?? "application/octet-stream",
    name: match?.[1] ?? "file",
  };
}

export async function deleteGraphAsset(assetId: string): Promise<void> {
  const res = await runtimeFetch(`/graph/assets/${encodeURIComponent(assetId)}?owner=local`, {
    method: "DELETE",
    timeoutMs: 30_000,
  });
  if (!res.ok) throw new Error(await readError(res));
}

export interface GraphImageMeta {
  assetId: string;
  name: string;
  mime: string;
  width: number;
  height: number;
  bytes: number;
  sha256: string;
  createdAt?: string;
}

export async function uploadGraphImage(
  name: string,
  mime: string,
  bytes: ArrayBuffer,
): Promise<GraphImageMeta> {
  const query = new URLSearchParams({ name, mime });
  const res = await runtimeFetch(`/graph/assets/images?${query.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: bytes,
    timeoutMs: 60_000,
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as GraphImageMeta;
}

export async function getGraphImage(assetId: string): Promise<GraphImageMeta> {
  const res = await runtimeFetch(`/graph/assets/images/${encodeURIComponent(assetId)}`, {
    method: "GET",
    timeoutMs: 30_000,
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as GraphImageMeta;
}

export async function deleteGraphImage(assetId: string): Promise<void> {
  const res = await runtimeFetch(`/graph/assets/images/${encodeURIComponent(assetId)}`, {
    method: "DELETE",
    timeoutMs: 30_000,
  });
  if (!res.ok) throw new Error(await readError(res));
}

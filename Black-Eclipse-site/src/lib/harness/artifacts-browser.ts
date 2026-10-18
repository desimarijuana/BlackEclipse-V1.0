// ─── Artifact Center BROWSER client ──────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/artifacts/**`), which proxy to
// the Python runtime. This module MUST stay client-safe: no Node built-ins, no
// server-only runtime helpers. Fetch only, so the screen mounts without pulling
// server code into the browser bundle.

export type ArtifactCategory =
  | "document" | "image" | "spreadsheet" | "dataset" | "chart" | "code"
  | "script" | "log" | "audio" | "video" | "archive" | "link" | "report"
  | "financial" | "backtest" | "presentation" | "other";

export type ArtifactStatus =
  | "ACTIVE" | "PROCESSING" | "FAILED" | "MISSING"
  | "ARCHIVED" | "DELETED" | "PURGED";

export type PreviewStatus = "PENDING" | "PROCESSING" | "READY" | "FAILED" | "UNSUPPORTED";

export interface Artifact {
  id: string;
  name: string;
  originalName: string | null;
  description: string;
  category: ArtifactCategory;
  mimeType: string;
  extension: string;
  sizeBytes: number | null;
  checksum: string | null;
  storageBackend: string;
  storageKey: string | null;
  ownerId: string;
  workspaceId: string | null;
  projectId: string | null;
  conversationId: string | null;
  agentId: string | null;
  taskId: string | null;
  runId: string | null;
  parentArtifactId: string | null;
  sourceType: string;
  sourceTool: string | null;
  status: ArtifactStatus;
  previewStatus: PreviewStatus;
  previewKind: string | null;
  thumbnailKey: string | null;
  favorite: boolean;
  pinned: boolean;
  versionNumber: number;
  tags: string[];
  collectionIds: string[];
  metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
  deletedAt: string | null;
  lastAccessedAt: string | null;
}

export interface ArtifactVersion {
  id: string;
  artifactId: string;
  versionNumber: number;
  storageKey: string | null;
  checksum: string | null;
  sizeBytes: number | null;
  mimeType: string | null;
  changeNote: string | null;
  createdAt: string;
}

export interface ArtifactCollection {
  id: string;
  name: string;
  description: string;
  parentId: string | null;
  artifactCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ArtifactPreview {
  kind: string;
  status: PreviewStatus;
  mimeType: string;
  name: string;
  sizeBytes: number | null;
  thumbnailKey: string | null;
  text: string | null;
  hasDownload: boolean;
}

export interface ArtifactPage {
  artifacts: Artifact[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export interface ListParams {
  q?: string;
  category?: ArtifactCategory;
  status?: ArtifactStatus;
  tags?: string[];
  projectId?: string;
  agentId?: string;
  taskId?: string;
  runId?: string;
  collectionId?: string;
  favorite?: boolean;
  includeArchived?: boolean;
  sort?: string;
  limit?: number;
  offset?: number;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: unknown };
  if (!res.ok) {
    const detail = body.detail;
    const message =
      typeof detail === "object" && detail && "message" in detail
        ? String((detail as { message: unknown }).message)
        : typeof detail === "string"
          ? detail
          : body.error ?? `request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

export async function listArtifacts(params: ListParams = {}): Promise<ArtifactPage> {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) value.forEach((v) => q.append(key, String(v)));
    else q.set(key, String(value));
  });
  const suffix = q.toString() ? `?${q.toString()}` : "";
  const body = await api<ArtifactPage & { success: boolean }>(`/api/artifacts${suffix}`);
  return {
    artifacts: body.artifacts ?? [],
    total: body.total ?? 0,
    limit: body.limit ?? 50,
    offset: body.offset ?? 0,
    hasMore: body.hasMore ?? false,
  };
}

export async function getArtifact(id: string): Promise<Artifact> {
  const body = await api<{ artifact: Artifact }>(`/api/artifacts/${encodeURIComponent(id)}`);
  return body.artifact;
}

export async function registerArtifact(input: {
  name: string;
  contentBase64?: string;
  sourcePath?: string;
  description?: string;
  tags?: string[];
  category?: ArtifactCategory;
}): Promise<Artifact> {
  const body = await api<{ artifact: Artifact }>("/api/artifacts", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.artifact;
}

export async function updateArtifact(
  id: string,
  fields: Partial<{ name: string; description: string; tags: string[]; favorite: boolean; category: ArtifactCategory }>,
): Promise<Artifact> {
  const body = await api<{ artifact: Artifact }>(`/api/artifacts/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(fields),
  });
  return body.artifact;
}

export async function archiveArtifact(id: string): Promise<Artifact> {
  const body = await api<{ artifact: Artifact }>(`/api/artifacts/${encodeURIComponent(id)}/archive`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.artifact;
}

export async function restoreArtifact(id: string): Promise<Artifact> {
  const body = await api<{ artifact: Artifact }>(`/api/artifacts/${encodeURIComponent(id)}/restore`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.artifact;
}

export async function deleteArtifact(id: string): Promise<Artifact> {
  const body = await api<{ artifact: Artifact }>(`/api/artifacts/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  return body.artifact;
}

export async function listVersions(id: string): Promise<ArtifactVersion[]> {
  const body = await api<{ versions: ArtifactVersion[] }>(
    `/api/artifacts/${encodeURIComponent(id)}/versions`,
  );
  return body.versions ?? [];
}

export async function getPreview(id: string): Promise<ArtifactPreview> {
  const body = await api<{ preview: ArtifactPreview }>(
    `/api/artifacts/${encodeURIComponent(id)}/preview`,
  );
  return body.preview;
}

export async function listCollections(): Promise<ArtifactCollection[]> {
  const body = await api<{ collections: ArtifactCollection[] }>("/api/artifacts/collections");
  return body.collections ?? [];
}

export async function createCollection(name: string, description = ""): Promise<ArtifactCollection> {
  const body = await api<{ collection: ArtifactCollection }>("/api/artifacts/collections", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
  return body.collection;
}

export async function listTags(): Promise<string[]> {
  const body = await api<{ tags: string[] }>("/api/artifacts/tags");
  return body.tags ?? [];
}

export async function bulkAction(
  artifactIds: string[],
  action: string,
  extra: { tags?: string[]; collectionId?: string } = {},
): Promise<{ succeeded: string[]; failed: { artifactId: string; code: string }[] }> {
  return api("/api/artifacts/bulk", {
    method: "POST",
    body: JSON.stringify({ artifactIds, action, ...extra }),
  });
}

export async function getStats(): Promise<{
  total: number;
  totalBytes: number;
  byStatus: Record<string, number>;
  byCategory: Record<string, number>;
}> {
  const body = await api<{ stats: { total: number; totalBytes: number; byStatus: Record<string, number>; byCategory: Record<string, number> } }>(
    "/api/artifacts/stats",
  );
  return body.stats;
}

/** A same-origin URL the browser can fetch the original bytes from. */
export function downloadUrl(id: string, version?: number): string {
  const suffix = version ? `?version=${version}` : "";
  return `/api/artifacts/${encodeURIComponent(id)}/download${suffix}`;
}

/**
 * A same-origin URL that PLAYS INLINE: `Content-Disposition: inline` and byte
 * ranges honored, so a `<video>`/`<audio>` element can start, seek and scrub.
 * Authorization is unchanged — the artifact proxy still presents the operator
 * credential on the server side.
 */
export function inlineUrl(id: string, version?: number): string {
  const suffix = version ? `&version=${version}` : "";
  return `/api/artifacts/${encodeURIComponent(id)}/download?inline=1${suffix}`;
}

/** A same-origin URL for an artifact's generated thumbnail, if any. */
export function thumbnailUrl(id: string): string {
  return `/api/artifacts/${encodeURIComponent(id)}/thumbnail`;
}

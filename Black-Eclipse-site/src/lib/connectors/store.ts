// ── Connector store (server-only) ───────────────────────────────────────────
// JDDS persistence for operator-configured connectors, datasets, fields and
// records. All structured values are JSON strings (Prisma + SQLite has no Json
// column here). Credentials are stored ONLY as AES-GCM payloads.
//
// Custom records are written exclusively to `CustomDatasetRecord`. Canonical
// market tables (`Asset`, `Price`, `Candles`, …) are never touched here — that
// is the core data-integrity guarantee of this layer.

import { prisma } from "@/lib/db";
import { encryptSecret, decryptSecret } from "./secrets";
import type { AuthConfig, Capability } from "./types";
import type { CustomConnectorConfig, CustomParam } from "./custom-rest";
import { syncCustomConnectors } from "./runtime";
import { mapResponseDetailed, type DatasetSchema } from "./mapping";

export interface ConnectorInput {
  name: string;
  description?: string;
  baseUrl: string;
  path: string;
  capabilities: Capability[];
  params?: CustomParam[];
  headers?: Record<string, string>;
  auth: Pick<AuthConfig, "scheme" | "header" | "username">;
  /** Plaintext secret from the browser, encrypted immediately. Omit to keep. */
  secret?: string;
  enabled?: boolean;
}

function parseJSON<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function toConfig(row: {
  id: string;
  name: string;
  description: string | null;
  baseUrl: string;
  path: string;
  capabilities: string;
  params: string;
  headers: string;
  authScheme: string;
  authHeader: string | null;
  authUsername: string | null;
  secretEncrypted: string | null;
  enabled: boolean;
}): CustomConnectorConfig {
  return {
    id: row.id,
    name: row.name,
    description: row.description ?? undefined,
    baseUrl: row.baseUrl,
    path: row.path,
    capabilities: parseJSON<Capability[]>(row.capabilities, []),
    params: parseJSON<CustomParam[]>(row.params, []),
    headers: parseJSON<Record<string, string>>(row.headers, {}),
    auth: {
      scheme: (row.authScheme as AuthConfig["scheme"]) ?? "none",
      header: row.authHeader ?? undefined,
      username: row.authUsername ?? undefined,
    },
    authSecretEncrypted: row.secretEncrypted ?? undefined,
    enabled: row.enabled,
  };
}

/** Shape safe to return to a browser — never includes the secret. */
export function toPublicConnector(row: {
  id: string;
  name: string;
  description: string | null;
  baseUrl: string;
  path: string;
  capabilities: string;
  params: string;
  headers: string;
  authScheme: string;
  authHeader: string | null;
  authUsername: string | null;
  secretEncrypted: string | null;
  enabled: boolean;
  healthState: string;
  lastTested: Date | null;
  lastSuccess: Date | null;
  lastError: string | null;
  lastHttpStatus: number | null;
  lastLatencyMs: number | null;
}) {
  return {
    id: row.id,
    name: row.name,
    description: row.description,
    baseUrl: row.baseUrl,
    path: row.path,
    capabilities: parseJSON<Capability[]>(row.capabilities, []),
    params: parseJSON<CustomParam[]>(row.params, []),
    headers: parseJSON<Record<string, string>>(row.headers, {}),
    auth: { scheme: row.authScheme, header: row.authHeader, username: row.authUsername },
    hasSecret: Boolean(row.secretEncrypted),
    enabled: row.enabled,
    health: {
      state: row.healthState,
      lastTested: row.lastTested,
      lastSuccess: row.lastSuccess,
      lastError: row.lastError,
      httpStatus: row.lastHttpStatus,
      latencyMs: row.lastLatencyMs,
    },
  };
}

export type PublicConnector = ReturnType<typeof toPublicConnector>;

/** All connectors, newest first. */
export async function listConnectorRows() {
  return prisma.dataConnector.findMany({ orderBy: { createdAt: "desc" } });
}

/** Load every enabled connector into the in-process registry. */
export async function loadConnectorsIntoRegistry(): Promise<void> {
  const rows = await listConnectorRows();
  syncCustomConnectors(rows.map(toConfig));
}

export async function createConnector(input: ConnectorInput) {
  const secretEncrypted = input.secret ? encryptSecret(input.secret) : null;
  const row = await prisma.dataConnector.create({
    data: {
      name: input.name,
      description: input.description ?? null,
      baseUrl: input.baseUrl,
      path: input.path,
      capabilities: JSON.stringify(input.capabilities),
      params: JSON.stringify(input.params ?? []),
      headers: JSON.stringify(input.headers ?? {}),
      authScheme: input.auth.scheme,
      authHeader: input.auth.header ?? null,
      authUsername: input.auth.username ?? null,
      secretEncrypted,
      enabled: input.enabled ?? true,
    },
  });
  await loadConnectorsIntoRegistry();
  return row;
}

export async function updateConnector(id: string, input: Partial<ConnectorInput>) {
  const data: Record<string, unknown> = {};
  if (input.name !== undefined) data.name = input.name;
  if (input.description !== undefined) data.description = input.description;
  if (input.baseUrl !== undefined) data.baseUrl = input.baseUrl;
  if (input.path !== undefined) data.path = input.path;
  if (input.capabilities !== undefined) data.capabilities = JSON.stringify(input.capabilities);
  if (input.params !== undefined) data.params = JSON.stringify(input.params);
  if (input.headers !== undefined) data.headers = JSON.stringify(input.headers);
  if (input.auth !== undefined) {
    data.authScheme = input.auth.scheme;
    data.authHeader = input.auth.header ?? null;
    data.authUsername = input.auth.username ?? null;
  }
  // An omitted secret keeps the stored one; an empty string clears it.
  if (input.secret !== undefined) {
    data.secretEncrypted = input.secret === "" ? null : encryptSecret(input.secret);
  }
  if (input.enabled !== undefined) data.enabled = input.enabled;

  const row = await prisma.dataConnector.update({ where: { id }, data });
  await loadConnectorsIntoRegistry();
  return row;
}

export async function deleteConnector(id: string): Promise<void> {
  await prisma.dataConnector.delete({ where: { id } });
  await loadConnectorsIntoRegistry();
}

/** Persist a health snapshot (application-level strings, no Prisma enum). */
export async function recordHealth(
  id: string,
  health: {
    state: string;
    httpStatus?: number;
    latencyMs?: number;
    lastError?: string;
  }
): Promise<void> {
  const now = new Date();
  await prisma.dataConnector.update({
    where: { id },
    data: {
      healthState: health.state,
      lastTested: now,
      lastSuccess: health.state === "CONNECTED" ? now : undefined,
      lastError: health.lastError ? health.lastError.slice(0, 300) : null,
      lastHttpStatus: health.httpStatus ?? null,
      lastLatencyMs: health.latencyMs ?? null,
    },
  });
}

/** Resolve the decrypted secret for a connector (server-side only). */
export async function connectorSecret(id: string): Promise<string | undefined> {
  const row = await prisma.dataConnector.findUnique({ where: { id }, select: { secretEncrypted: true } });
  if (!row?.secretEncrypted) return undefined;
  return decryptSecret(row.secretEncrypted);
}

// ── Datasets ────────────────────────────────────────────────────────────────

export interface DatasetInput {
  name: string;
  description?: string;
  connectorId?: string | null;
  schema: DatasetSchema;
  /** Parameter name → comma-separated defaults for scheduled pulls. */
  pullParams?: Record<string, string>;
  refreshEnabled?: boolean;
  refreshIntervalMin?: number;
}

const MIN_REFRESH_MIN = 5;
const MAX_REFRESH_MIN = 24 * 60;

export async function saveDataset(input: DatasetInput) {
  const refreshIntervalMin =
    input.refreshIntervalMin !== undefined
      ? Math.min(Math.max(Math.round(input.refreshIntervalMin), MIN_REFRESH_MIN), MAX_REFRESH_MIN)
      : undefined;

  const dataset = await prisma.customDataset.upsert({
    where: { name: input.name },
    update: {
      description: input.description ?? null,
      connectorId: input.connectorId ?? null,
      recordPath: input.schema.recordPath,
      timestampField: input.schema.timestampField ?? null,
      ...(input.pullParams !== undefined ? { pullParams: JSON.stringify(input.pullParams) } : {}),
      ...(input.refreshEnabled !== undefined ? { refreshEnabled: input.refreshEnabled } : {}),
      ...(refreshIntervalMin !== undefined ? { refreshIntervalMin } : {}),
    },
    create: {
      name: input.name,
      description: input.description ?? null,
      connectorId: input.connectorId ?? null,
      recordPath: input.schema.recordPath,
      timestampField: input.schema.timestampField ?? null,
      pullParams: JSON.stringify(input.pullParams ?? {}),
      refreshEnabled: input.refreshEnabled ?? false,
      refreshIntervalMin: refreshIntervalMin ?? 60,
    },
  });

  // Replace field definitions (fields are structural, not user data).
  await prisma.customDatasetField.deleteMany({ where: { datasetId: dataset.id } });
  await prisma.customDatasetField.createMany({
    data: input.schema.fields.map((field, index) => ({
      datasetId: dataset.id,
      name: field.name,
      fieldType: field.type,
      sourcePath: field.sourcePath,
      required: field.required ?? false,
      identity: field.identity ?? false,
      unit: field.unit ?? null,
      description: field.description ?? null,
      position: index,
    })),
  });

  return dataset;
}

export async function listDatasets() {
  return prisma.customDataset.findMany({
    include: { fields: { orderBy: { position: "asc" } }, _count: { select: { records: true } } },
    orderBy: { createdAt: "desc" },
  });
}

export async function getDatasetSchema(datasetId: string): Promise<(DatasetSchema & { id: string; connectorId: string | null }) | null> {
  const row = await prisma.customDataset.findUnique({
    where: { id: datasetId },
    include: { fields: { orderBy: { position: "asc" } } },
  });
  if (!row) return null;
  return {
    id: row.id,
    connectorId: row.connectorId,
    dataset: row.name,
    description: row.description ?? undefined,
    recordPath: row.recordPath,
    timestampField: row.timestampField ?? undefined,
    fields: row.fields.map((f) => ({
      name: f.name,
      type: f.fieldType as DatasetSchema["fields"][number]["type"],
      sourcePath: f.sourcePath,
      required: f.required,
      identity: f.identity,
      unit: f.unit ?? undefined,
      description: f.description ?? undefined,
    })),
  };
}

export interface IngestOutcome {
  /** Rows written (inserted or updated). */
  written: number;
  /** Rows the response contained, before mapping/dedup. */
  extracted: number;
  /**
   * Rows discarded, with the reason. Reported honestly so callers can tell the
   * operator "imported 8 of 10" instead of implying a complete import.
   */
  rejected: number;
  rejectedRequired: number;
  rejectedIdentity: number;
  /** Rows that collapsed onto an identical recordKey (last-write-wins). */
  deduped: number;
}

/**
 * Ingest a raw response into a dataset.
 *
 * Idempotent by design: `(datasetId, recordKey)` is unique, so re-importing the
 * same response upserts in place. Writes to canonical tables are impossible from
 * here — `CustomDatasetRecord` is the only table touched.
 */
export async function ingestRecords(
  datasetId: string,
  raw: unknown,
  provenance: string = "CUSTOM",
  options: { now?: Date } = {}
): Promise<IngestOutcome> {
  const schema = await getDatasetSchema(datasetId);
  if (!schema) throw new Error(`Unknown dataset: ${datasetId}`);

  const outcome = mapResponseDetailed(raw, schema);

  const now = options.now ?? new Date();
  let written = 0;

  for (const record of outcome.records) {
    await prisma.customDatasetRecord.upsert({
      where: { datasetId_recordKey: { datasetId, recordKey: record.recordKey } },
      update: {
        values: JSON.stringify(record.values),
        provenance,
        retrievedAt: now,
      },
      create: {
        datasetId,
        recordKey: record.recordKey,
        values: JSON.stringify(record.values),
        provenance,
        retrievedAt: now,
      },
    });
    written++;
  }

  return {
    written,
    extracted: outcome.extracted,
    rejected: outcome.rejectedRequired + outcome.rejectedIdentity,
    rejectedRequired: outcome.rejectedRequired,
    rejectedIdentity: outcome.rejectedIdentity,
    deduped: outcome.deduped,
  };
}

export async function listRecords(datasetId: string, limit = 200) {
  return prisma.customDatasetRecord.findMany({
    where: { datasetId },
    orderBy: { retrievedAt: "desc" },
    take: limit,
  });
}

/** Delete a dataset and (by cascade) its fields and records. */
export async function deleteDataset(datasetId: string): Promise<void> {
  await prisma.customDataset.delete({ where: { id: datasetId } });
}

// ── Query helpers (used by the agent tools) ─────────────────────────────────

export async function findDatasetByName(name: string) {
  return prisma.customDataset.findFirst({
    where: { name },
    include: { fields: { orderBy: { position: "asc" } } },
  });
}

export interface RecordQuery {
  /** Exact-match filters on mapped field values (case-insensitive). */
  filters?: Record<string, string>;
  limit?: number;
}

export interface ParsedRecord {
  id: string;
  recordKey: string;
  values: Record<string, unknown>;
  provenance: string;
  retrievedAt: Date;
}

/**
 * Query a dataset's records. Filters are exact matches evaluated in JS because
 * SQLite via Prisma cannot query inside the JSON `values` column — this is a
 * deliberate trade-off, bounded by `limit`.
 */
export async function queryRecords(datasetId: string, query: RecordQuery = {}): Promise<ParsedRecord[]> {
  const limit = Math.min(Math.max(query.limit ?? 20, 1), 100);
  const rows = await prisma.customDatasetRecord.findMany({
    where: { datasetId },
    orderBy: { retrievedAt: "desc" },
    take: query.filters && Object.keys(query.filters).length > 0 ? 1000 : limit,
  });

  const parsed: ParsedRecord[] = rows.map((r) => ({
    id: r.id,
    recordKey: r.recordKey,
    values: parseJSON<Record<string, unknown>>(r.values, {}),
    provenance: r.provenance,
    retrievedAt: r.retrievedAt,
  }));

  const filters = Object.entries(query.filters ?? {});
  if (filters.length === 0) return parsed.slice(0, limit);

  return parsed
    .filter((record) =>
      filters.every(([key, expected]) => {
        const actual = record.values[key];
        if (actual === undefined || actual === null) return false;
        return String(actual).toLowerCase() === expected.toLowerCase();
      })
    )
    .slice(0, limit);
}

/** Dataset summary rows safe to describe to an agent (no secrets involved). */
export async function datasetSummaries() {
  const rows = await prisma.customDataset.findMany({
    include: { fields: { orderBy: { position: "asc" } }, _count: { select: { records: true } } },
    orderBy: { createdAt: "desc" },
  });
  return rows.map((d) => ({
    id: d.id,
    name: d.name,
    description: d.description,
    recordPath: d.recordPath,
    connectorId: d.connectorId,
    recordCount: d._count.records,
    fields: d.fields.map((f) => ({ name: f.name, type: f.fieldType, identity: f.identity })),
  }));
}

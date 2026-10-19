// ─── Operator-declared dataset capability (Phase 16 remainder) ──────────────
// Collects records from a DATASET the operator declared (Settings → Data
// Sources): a custom REST connector plus a record path and a mapped field
// schema. This is the READ half — the bridge never writes; the caller (`acquire`)
// writes its own CSV + manifest. The connector platform owns the transport
// (https-only, DNS-pinned, size-capped `safeGet`) and the credentials; this
// capability only selects a DECLARED dataset by name, fills the connector's OWN
// declared parameters with caller-supplied values (never a URL, host, header or
// secret), and maps the response through the existing deterministic
// `mapResponseDetailed` — no model, nothing guessed. Only datasets the OPERATOR
// declared are reachable: an undeclared name is `not_found`.
//
// Deliberately NOT recorded in the market-data SourceHealth ledger: the
// connector platform's own row (`DataConnector.healthState`) owns the health of
// an operator route, and an operator-chosen source name must not leak into the
// market-data route vocabulary.

import { getConnector as registryGetConnector } from "@/lib/connectors/registry";
import {
  findDatasetByName,
  getDatasetSchema,
  loadConnectorsIntoRegistry,
} from "@/lib/connectors/store";
import { mapResponseDetailed, type DatasetSchema } from "@/lib/connectors/mapping";
import type { DataConnector } from "@/lib/connectors/types";
import { unavailableClass } from "./data-bridge-result";
import type { DataBridgeResult } from "./data-bridge-types";

// One call returns at most this many records; the provider-side response is
// already streamed-capped by the connector transport, and the Python budget
// bounds what is written.
const MAX_RECORDS = 2_000;
// A connector's declared parameter count is small; a larger map is a mistake,
// not a request.
const MAX_VALUES = 25;

export interface DatasetRecordsDeps {
  /** Ensure the in-process registry mirrors JDDS (injectable for tests). */
  load?: () => Promise<void>;
  findDataset?: typeof findDatasetByName;
  schema?: typeof getDatasetSchema;
  getConnector?: (id: string) => DataConnector | undefined;
}

/**
 * Coerce caller values to the flat string map the connector's declared
 * parameters expect. A JSON string is accepted (the tool surfaces pass one);
 * a nested value is refused — it could only end up percent-encoded into a query
 * parameter, which is never what a caller means.
 */
function flatValues(raw: unknown): Record<string, string> | "invalid" {
  let source: unknown = raw;
  if (typeof raw === "string") {
    if (!raw.trim()) return {};
    try {
      source = JSON.parse(raw);
    } catch {
      return "invalid";
    }
  }
  if (source === undefined || source === null) return {};
  if (typeof source !== "object" || Array.isArray(source)) return "invalid";
  const entries = Object.entries(source as Record<string, unknown>);
  if (entries.length > MAX_VALUES) return "invalid";
  const out: Record<string, string> = {};
  for (const [key, value] of entries) {
    if (value === null || value === undefined) continue;
    if (typeof value === "object") return "invalid";
    out[key] = String(value);
  }
  return out;
}

export async function customDatasetRecordsCapability(
  params: Record<string, unknown>,
  deps?: DatasetRecordsDeps,
): Promise<DataBridgeResult> {
  const name = String(params.dataset ?? "").trim();
  if (!name) return unavailableClass("invalid_request", "dataset is required");
  const values = flatValues(params.values);
  if (values === "invalid") {
    return unavailableClass("invalid_request", "values must be a flat map of parameter name to value");
  }

  const findDataset = deps?.findDataset ?? findDatasetByName;
  const dataset = await findDataset(name).catch(() => null);
  if (!dataset) return unavailableClass("not_found", `no connected dataset named "${name}"`);
  if (!dataset.connectorId) {
    return unavailableClass(
      "incomplete",
      `dataset "${name}" has no connector attached (Settings → Data Sources)`,
    );
  }

  const load = deps?.load ?? loadConnectorsIntoRegistry;
  try {
    await load();
  } catch {
    return unavailableClass("source_failure", "the connector registry could not be loaded");
  }
  const getConnector = deps?.getConnector ?? registryGetConnector;
  const connector = getConnector(dataset.connectorId);
  if (!connector) {
    return unavailableClass(
      "not_found",
      `connector ${dataset.connectorId} is not available (missing or disabled)`,
    );
  }
  const capability = connector.capabilities[0];
  if (!capability) {
    return unavailableClass("incomplete", `connector "${connector.name}" declares no capability`);
  }

  const schema: DatasetSchema | null = await (deps?.schema ?? getDatasetSchema)(dataset.id).catch(
    () => null,
  );
  if (!schema) return unavailableClass("not_found", `dataset "${name}" has no schema`);

  const fetched = await connector.fetch({ capability, params: values });
  if (!fetched.ok) {
    return unavailableClass("source_failure", fetched.error?.message ?? "the connector fetch failed");
  }
  const outcome = mapResponseDetailed(fetched.data, schema);
  const records = outcome.records
    .slice(0, MAX_RECORDS)
    .map((record) => ({ recordKey: record.recordKey, values: record.values }));
  return {
    status: "OK",
    dataset: { id: dataset.id, name: dataset.name },
    connector: { id: connector.id, name: connector.name },
    provenance: fetched.provenance,
    fields: schema.fields.map((field) => field.name),
    retrievedAt: fetched.retrievedAt,
    extracted: outcome.extracted,
    rejectedRequired: outcome.rejectedRequired,
    rejectedIdentity: outcome.rejectedIdentity,
    deduped: outcome.deduped,
    count: records.length,
    truncated: outcome.records.length > records.length,
    records,
  };
}

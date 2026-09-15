// ── Dataset refresh (multi-value pull) ──────────────────────────────────────
// Expands a dataset's declared parameter values into one request per value and
// ingests the results. This is what makes a per-symbol API usable for a
// universe instead of one symbol at a time.
//
// Bounds are explicit: at most MAX_VALUES_PER_PULL values per run, each request
// goes through the same hardened outbound path, and calls are spaced out so a
// scheduled pull can never become a request storm against the operator's API or
// this process (better-sqlite3 writes are synchronous).

import { prisma } from "@/lib/db";
import { getConnector } from "./registry";
import { registerBuiltinConnectors } from "./builtins";
import { loadConnectorsIntoRegistry, ingestRecords, type IngestOutcome } from "./store";

/** Hard ceiling on requests per pull — a typo in a list must not fan out. */
export const MAX_VALUES_PER_PULL = 25;
/** Pause between requests, to protect the operator's API and our event loop. */
export const INTER_REQUEST_DELAY_MS = 250;

export interface PullValueResult {
  value: string;
  ok: boolean;
  written: number;
  extracted: number;
  rejected: number;
  deduped: number;
  error?: string;
}

export interface PullSummary {
  /** Values requested (after expansion + clamping). */
  requested: number;
  /** Values actually attempted. */
  attempted: number;
  /** Values whose request succeeded. */
  succeeded: number;
  /** Values whose request failed. */
  failed: number;
  /** Total rows written across all values. */
  written: number;
  /** Total rows the responses contained. */
  extracted: number;
  /** Total rows discarded (missing identity / required). */
  rejected: number;
  /** Values dropped because MAX_VALUES_PER_PULL was exceeded. */
  overflow: number;
  /** How many requests were NOT made because the cap was hit. */
  truncated: boolean;
  provenance: string;
  results: PullValueResult[];
}

/** Split a parameter value into individual values. `"BTC,ETH"` → two values. */
export function expandValues(raw: string): string[] {
  return raw
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

/**
 * Decide which values to fetch for a parameter.
 * - an explicit list (comma-separated) wins,
 * - otherwise a declared literal is used as-is,
 * - otherwise the parameter has no value and the pull cannot proceed.
 */
export function valuesFor(param: { name: string; value: string }, provided?: string): string[] {
  if (provided && provided.trim() !== "") return expandValues(provided);
  const template = param.value.match(/^\{\{(\w+)\}\}$/);
  if (template) return [];
  return [param.value];
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Pull a dataset through its connector, once per value of the parameter that
 * drives it.
 *
 * `values` maps parameter name → comma-separated value list (or a single
 * value). Parameters with no supplied and no declared value are reported as an
 * error rather than silently fetching the wrong URL.
 *
 * `delayMs` spaces requests out to protect the operator's API; pass 0 to
 * disable (used by tests).
 */
export async function pullDataset(
  datasetId: string,
  options: { values?: Record<string, string>; now?: Date; delayMs?: number } = {}
): Promise<PullSummary> {
  const delayMs = options.delayMs ?? INTER_REQUEST_DELAY_MS;
  const dataset = await prisma.customDataset.findUnique({ where: { id: datasetId } });
  if (!dataset) throw new Error(`Unknown dataset: ${datasetId}`);
  if (!dataset.connectorId) throw new Error(`Dataset "${dataset.name}" has no connector attached`);

  registerBuiltinConnectors();
  await loadConnectorsIntoRegistry();
  const connector = getConnector(dataset.connectorId);
  if (!connector) throw new Error(`Connector not found: ${dataset.connectorId}`);

  const declared = JSON.parse(dataset.pullParams || "{}") as Record<string, string>;
  const supplied = options.values ?? declared;

  // Work out, per parameter, the list of values to request.
  const plan = new Map<string, string[]>();
  const missing: string[] = [];

  const declaredParams = await declaredParameters(dataset.connectorId);
  for (const param of declaredParams) {
    const values = valuesFor(param, supplied[param.name]);
    if (values.length === 0) {
      missing.push(param.name);
      continue;
    }
    plan.set(param.name, values);
  }

  if (missing.length > 0) {
    throw new Error(`Missing value for parameter(s): ${missing.join(", ")}`);
  }

  // Requests are driven by the longest value list; a connector with no
  // parameters still makes exactly one request.
  const perValue = plan.size === 0 ? 1 : Math.max(...[...plan.values()].map((v) => v.length), 1);
  const truncated = perValue > MAX_VALUES_PER_PULL;
  const cycles = Math.min(perValue, MAX_VALUES_PER_PULL);

  const results: PullValueResult[] = [];
  let written = 0;
  let extracted = 0;
  let rejected = 0;
  let provenance = "CUSTOM";

  for (let i = 0; i < cycles; i++) {
    // Build this cycle's parameter values (short lists repeat their single value).
    const params: Record<string, string> = {};
    const label: string[] = [];
    for (const [name, values] of plan) {
      const value = values.length === 1 ? values[0] : values[i] ?? values[values.length - 1];
      params[name] = value;
      label.push(value);
    }
    const labelText = label.join("|") || "(no params)";

    const capability = connector.capabilities[0];
    const fetchResult = await connector.fetch({ capability, params });

    if (!fetchResult.ok) {
      results.push({
        value: labelText,
        ok: false,
        written: 0,
        extracted: 0,
        rejected: 0,
        deduped: 0,
        error: fetchResult.error?.message ?? "Fetch failed",
      });
      if (i < cycles - 1) await sleep(delayMs);
      continue;
    }

    provenance = fetchResult.provenance;
    const outcome: IngestOutcome = await ingestRecords(datasetId, fetchResult.data, provenance, {
      now: options.now,
    });
    written += outcome.written;
    extracted += outcome.extracted;
    rejected += outcome.rejected;
    results.push({
      value: labelText,
      ok: true,
      written: outcome.written,
      extracted: outcome.extracted,
      rejected: outcome.rejected,
      deduped: outcome.deduped,
    });

    if (i < cycles - 1) await sleep(delayMs);
  }

  const succeeded = results.filter((r) => r.ok).length;

  return {
    requested: perValue,
    attempted: results.length,
    succeeded,
    failed: results.length - succeeded,
    written,
    extracted,
    rejected,
    overflow: Math.max(0, perValue - cycles),
    truncated,
    provenance,
    results,
  };
}

/** Read the connector's declared parameter definitions from JDDS. */
async function declaredParameters(connectorId: string): Promise<Array<{ name: string; value: string }>> {
  const row = await prisma.dataConnector.findUnique({
    where: { id: connectorId },
    select: { params: true },
  });
  if (!row) return [];
  try {
    const parsed = JSON.parse(row.params);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((p): p is { name: string; value: string } => Boolean(p) && typeof p.name === "string")
      .map((p) => ({ name: p.name, value: typeof p.value === "string" ? p.value : "" }));
  } catch {
    return [];
  }
}

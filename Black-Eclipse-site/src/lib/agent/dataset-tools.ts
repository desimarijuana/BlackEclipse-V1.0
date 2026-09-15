// ── Connector / dataset tools for the agent ─────────────────────────────────
// Extends the research agent with the ability to read operator-connected data:
// discover datasets, inspect one, and query its records. Follows the
// `ToolDefinition` contract in `tools.ts` (same shape as `journal-tools.ts`).
//
// Provenance is always stated in the tool output so the LLM can distinguish
// operator data from canonical scraper data — it never invents a source.

import type { ToolDefinition } from "./tools";
import { datasetSummaries, findDatasetByName, queryRecords } from "@/lib/connectors/store";

function formatRecordLine(record: { recordKey: string; values: Record<string, unknown> }): string {
  const pairs = Object.entries(record.values)
    .map(([k, v]) => `${k}=${v === undefined || v === null ? "—" : String(v)}`)
    .join(", ");
  return `  - [${record.recordKey}] ${pairs}`;
}

/** List the operator's connected datasets (names, fields, record counts). */
async function listDatasets(): Promise<string> {
  const datasets = await datasetSummaries();
  if (datasets.length === 0) {
    return "No custom datasets are connected. The operator can add one in Settings → Data Sources.";
  }
  return datasets
    .map((d) => {
      const fields = d.fields.map((f) => `${f.name}:${f.type}${f.identity ? " (identity)" : ""}`).join(", ");
      return [
        `Dataset "${d.name}"${d.description ? ` — ${d.description}` : ""}`,
        `  Records: ${d.recordCount} | recordPath: ${d.recordPath} | source: ${d.connectorId ?? "unmapped"}`,
        `  Fields: ${fields || "none"}`,
      ].join("\n");
    })
    .join("\n\n");
}

/** Inspect one dataset's schema. */
async function describeDataset(name: string): Promise<string> {
  const dataset = await findDatasetByName(name);
  if (!dataset) {
    const available = (await datasetSummaries()).map((d) => d.name).join(", ");
    return `No dataset named "${name}".${available ? ` Available: ${available}` : ""}`;
  }
  const fields = dataset.fields.map((f) => {
    const flags = [f.required ? "required" : null, f.identity ? "identity" : null].filter(Boolean).join(", ");
    return `  - ${f.name} (${f.fieldType}) from "${f.sourcePath}"${flags ? ` [${flags}]` : ""}`;
  });
  return [
    `Dataset: ${dataset.name}`,
    dataset.description ? `Description: ${dataset.description}` : null,
    `recordPath: ${dataset.recordPath}`,
    `Fields:\n${fields.join("\n") || "  (none)"}`,
  ]
    .filter(Boolean)
    .join("\n");
}

/**
 * Query records from a dataset. Filters are exact-match on mapped field names;
 * values are compared case-insensitively.
 */
async function queryDataset(
  name: string,
  filters: Record<string, string>,
  limit: number
): Promise<string> {
  const dataset = await findDatasetByName(name);
  if (!dataset) {
    const available = (await datasetSummaries()).map((d) => d.name).join(", ");
    return `No dataset named "${name}".${available ? ` Available: ${available}` : ""}`;
  }

  const rows = await queryRecords(dataset.id, { filters, limit });
  if (rows.length === 0) {
    const filterText = Object.entries(filters).map(([k, v]) => `${k}=${v}`).join(", ");
    return `Dataset "${name}" has no records matching ${filterText || "(no filter)"}.`;
  }

  const provenance = rows[0]?.provenance ?? "CUSTOM";
  return [
    `Dataset "${name}" — ${rows.length} record(s)${Object.keys(filters).length ? ` matching ${Object.entries(filters).map(([k, v]) => `${k}=${v}`).join(", ")}` : ""}`,
    `Provenance: ${provenance} (operator data source, not the built-in scraper)`,
    ...rows.map(formatRecordLine),
  ].join("\n");
}

function coerceFilters(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== "object") return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (value === null || value === undefined) continue;
    out[key] = String(value);
  }
  return out;
}

export const DATASET_TOOLS: ToolDefinition[] = [
  {
    name: "list_datasets",
    description:
      "List the operator's connected custom data sources (datasets), with their fields and record counts. Use this first to discover what custom data is available.",
    parameters: {
      type: "object",
      properties: {},
    },
    execute: () => listDatasets(),
  },
  {
    name: "describe_dataset",
    description:
      "Describe one custom dataset's schema: fields, types, which field is the record identity, and the recordPath used to extract records.",
    parameters: {
      type: "object",
      properties: {
        dataset: { type: "string", description: "Dataset name, e.g. 'binance_tickers'." },
      },
      required: ["dataset"],
    },
    execute: (a) => describeDataset(String(a.dataset || "")),
  },
  {
    name: "query_dataset",
    description:
      "Query records from a connected custom dataset, optionally filtering by mapped field values. Returns plain-text records plus their provenance.",
    parameters: {
      type: "object",
      properties: {
        dataset: { type: "string", description: "Dataset name, e.g. 'binance_tickers'." },
        filters: {
          type: "object",
          description:
            "Optional exact-match filters on mapped field names, e.g. { \"symbol\": \"AAPL\" }. Case-insensitive.",
        },
        limit: { type: "number", description: "Max records to return (default 20, max 100)." },
      },
      required: ["dataset"],
    },
    execute: (a) =>
      queryDataset(
        String(a.dataset || ""),
        coerceFilters(a.filters),
        Number.isFinite(Number(a.limit)) ? Number(a.limit) : 20
      ),
  },
];

export function getDatasetTool(name: string): ToolDefinition | undefined {
  return DATASET_TOOLS.find((t) => t.name === name);
}

export function datasetToolSchemas() {
  return DATASET_TOOLS.map((t) => ({
    type: "function",
    function: {
      name: t.name,
      description: t.description,
      parameters: t.parameters,
    },
  }));
}

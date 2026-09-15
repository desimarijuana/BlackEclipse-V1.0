import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  deleteDataset,
  getDatasetSchema,
  ingestRecords,
  listDatasets,
  listRecords,
  saveDataset,
} from "@/lib/connectors/store";
import { pullDataset } from "@/lib/connectors/refresh";
import type { DatasetSchema, FieldType } from "@/lib/connectors/mapping";
import { FIELD_TYPES } from "@/lib/connectors/mapping";

export const dynamic = "force-dynamic";

// GET /api/datasets            — list datasets with field metadata + record counts
// GET /api/datasets?id=...     — one dataset with its recent records
export async function GET(request: Request) {
  try {
    const id = new URL(request.url).searchParams.get("id");
    if (id) {
      const schema = await getDatasetSchema(id);
      if (!schema) return NextResponse.json({ error: "Dataset not found" }, { status: 404 });
      const records = await listRecords(id);
      return NextResponse.json({
        dataset: schema,
        records: records.map((r) => ({
          id: r.id,
          recordKey: r.recordKey,
          values: JSON.parse(r.values) as unknown,
          provenance: r.provenance,
          retrievedAt: r.retrievedAt,
        })),
      });
    }
    const datasets = await listDatasets();
    return NextResponse.json({
      datasets: datasets.map((d) => ({
        id: d.id,
        name: d.name,
        description: d.description,
        connectorId: d.connectorId,
        recordPath: d.recordPath,
        fieldCount: d.fields.length,
        recordCount: d._count.records,
        pullParams: JSON.parse(d.pullParams || "{}") as Record<string, string>,
        refreshEnabled: d.refreshEnabled,
        refreshIntervalMin: d.refreshIntervalMin,
        lastRefreshAt: d.lastRefreshAt,
        nextRefreshAt: d.nextRefreshAt,
        updatedAt: d.updatedAt,
      })),
    });
  } catch (err) {
    console.error("[api/datasets] GET error:", err);
    return NextResponse.json({ error: "Failed to load datasets" }, { status: 500 });
  }
}

interface SaveBody {
  id?: string;
  name?: string;
  description?: string;
  connectorId?: string | null;
  schema?: DatasetSchema;
  /** Parameter name → comma-separated default values for scheduled pulls. */
  pullParams?: Record<string, string>;
  refreshEnabled?: boolean;
  refreshIntervalMin?: number;
}

function validateSchema(schema: unknown): { ok: true; schema: DatasetSchema } | { ok: false; error: string } {
  if (!schema || typeof schema !== "object") return { ok: false, error: "schema is required" };
  const s = schema as Record<string, unknown>;
  if (typeof s.recordPath !== "string" || s.recordPath.trim() === "") {
    return { ok: false, error: "recordPath is required" };
  }
  if (!Array.isArray(s.fields) || s.fields.length === 0) {
    return { ok: false, error: "At least one field mapping is required" };
  }
  const fields = (s.fields as unknown[])
    .filter((f): f is Record<string, unknown> => Boolean(f) && typeof f === "object")
    .map((f) => ({
      name: String(f.name ?? ""),
      type: (FIELD_TYPES.includes(f.type as FieldType) ? f.type : "string") as FieldType,
      sourcePath: String(f.sourcePath ?? ""),
      required: Boolean(f.required),
      identity: Boolean(f.identity),
      unit: typeof f.unit === "string" ? f.unit : undefined,
      description: typeof f.description === "string" ? f.description : undefined,
    }));
  if (fields.some((f) => !f.name || !f.sourcePath)) {
    return { ok: false, error: "Every field needs a name and a source path" };
  }
  if (!fields.some((f) => f.identity)) {
    return { ok: false, error: "Mark at least one field as the record identity (for deduplication)" };
  }
  return {
    ok: true,
    schema: {
      dataset: typeof s.dataset === "string" ? s.dataset : "dataset",
      description: typeof s.description === "string" ? s.description : undefined,
      recordPath: s.recordPath,
      timestampField: typeof s.timestampField === "string" ? s.timestampField : undefined,
      fields,
    },
  };
}

// POST /api/datasets — create/update a dataset definition.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "datasets-save");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json()) as SaveBody;
    if (!body.name || body.name.trim() === "") {
      return NextResponse.json({ error: "Dataset name is required" }, { status: 400 });
    }
    const validated = validateSchema(body.schema);
    if (!validated.ok) return NextResponse.json({ error: validated.error }, { status: 400 });

    const dataset = await saveDataset({
      name: body.name.trim(),
      description: body.description,
      connectorId: body.connectorId ?? null,
      schema: { ...validated.schema, dataset: body.name.trim() },
      pullParams: body.pullParams,
      refreshEnabled: body.refreshEnabled,
      refreshIntervalMin: body.refreshIntervalMin,
    });
    return NextResponse.json({ dataset: { id: dataset.id, name: dataset.name } }, { status: 201 });
  } catch (err) {
    console.error("[api/datasets] POST error:", err);
    return NextResponse.json({ error: "Failed to save dataset" }, { status: 500 });
  }
}

interface IngestBody {
  datasetId?: string;
  connectorId?: string;
  /** Parameter name → single value or comma-separated list (multi-value pull). */
  params?: Record<string, string>;
  /** Inline payload, used when the wizard already holds a sample response. */
  payload?: unknown;
}

// PUT /api/datasets — ingest records for a dataset.
//
// Three modes:
//   1. `payload` only        → map and store an inline response.
//   2. `params` supplied     → multi-value pull: one request per value.
//   3. neither               → pull using the dataset's saved pullParams.
//
// Writes ONLY to CustomDatasetRecord; canonical Asset/Price/Candles rows are
// never touched.
export async function PUT(request: Request) {
  const blocked = guardMutation(request, "datasets-ingest");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json()) as IngestBody;
    if (!body.datasetId) return NextResponse.json({ error: "datasetId is required" }, { status: 400 });

    // Inline payload path — no connector involved.
    if (body.payload !== undefined) {
      const outcome = await ingestRecords(body.datasetId, body.payload, "CUSTOM");
      return NextResponse.json({ ok: true, ...outcome, provenance: "CUSTOM" });
    }

    // Connector pull path (single or multi-value).
    try {
      const summary = await pullDataset(body.datasetId, { values: body.params });
      const ok = summary.failed === 0;
      return NextResponse.json(
        { ok, ...summary, provenance: summary.provenance },
        { status: ok ? 200 : 207 }
      );
    } catch (err) {
      // A missing value / unattached connector is a client error, not an outage.
      const message = err instanceof Error ? err.message : "Pull failed";
      const isClientError = /Missing value|no connector attached|Unknown dataset/i.test(message);
      return NextResponse.json(
        { error: message, code: isClientError ? "invalid_config" : "network" },
        { status: isClientError ? 400 : 502 }
      );
    }
  } catch (err) {
    console.error("[api/datasets] PUT error:", err);
    return NextResponse.json({ error: "Failed to ingest records" }, { status: 500 });
  }
}

// DELETE /api/datasets?id=... — remove a dataset and its records (canonical
// market tables are never touched).
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "datasets-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const id = new URL(request.url).searchParams.get("id");
    if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });
    await deleteDataset(id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/datasets] DELETE error:", err);
    return NextResponse.json({ error: "Failed to delete dataset" }, { status: 500 });
  }
}

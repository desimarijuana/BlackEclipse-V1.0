import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { ingestRecords, saveDataset } from "@/lib/connectors/store";
import type { DatasetSchema } from "@/lib/connectors/mapping";

export const dynamic = "force-dynamic";

// POST /api/scraper/datasets — persist the rows a generated scraper collected.
//
// The scraper lane (the Python runtime) collects rows from a page and asks the
// front door to keep them. The rows land in `CustomDatasetRecord` — the SAME
// store the dataset wizard uses — so a scraped table becomes an ordinary
// dataset: queryable, re-importable, and clearly NOT a canonical market table.
//
// Honesty rules that travel with the data:
//   * the provenance of every row is `SCRAPER`, never `CUSTOM`/a source name —
//     a scraped row is collected page data, not a verified source;
//   * each row carries a content-derived `record_key`, so re-running the same
//     scraper UPDATES the same rows instead of duplicating them;
//   * the write is idempotent and bounded, and it reports what it dropped.

const MAX_ROWS = 5_000;
const MAX_COLUMNS = 64;
const MAX_NAME_CHARS = 64;
const MAX_CELL_CHARS = 2_000;
const RECORD_KEY_FIELD = "record_key";
const PROVENANCE = "SCRAPER";

interface IngestBody {
  name?: string;
  description?: string;
  sourceUrl?: string;
  purpose?: string;
  columns?: string[];
  rows?: Record<string, string>[];
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, MAX_NAME_CHARS);
}

function boundedCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : String(value);
  return text.slice(0, MAX_CELL_CHARS);
}

/** A stable key from the row's own content, so a re-run updates in place. */
function contentKey(values: Record<string, string>): string {
  const joined = Object.keys(values)
    .sort()
    .map((key) => `${key}=${values[key] ?? ""}`)
    .join("\n");
  // A short, stable digest: FNV-1a. Not a security primitive — a row identity.
  let hash = 0x811c9dc5;
  for (let i = 0; i < joined.length; i += 1) {
    hash ^= joined.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `r${hash.toString(16).padStart(8, "0")}`;
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "scraper-datasets");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const body = (await request.json()) as IngestBody;
    const name = slug(String(body.name ?? "").trim());
    if (!name) {
      return NextResponse.json({ error: "A dataset name is required" }, { status: 400 });
    }
    if (!Array.isArray(body.columns) || body.columns.length === 0) {
      return NextResponse.json({ error: "At least one column is required" }, { status: 400 });
    }
    if (!Array.isArray(body.rows)) {
      return NextResponse.json({ error: "rows must be a list" }, { status: 400 });
    }
    if (body.rows.length > MAX_ROWS) {
      return NextResponse.json(
        { error: `At most ${MAX_ROWS} rows can be stored in one collection` },
        { status: 400 },
      );
    }

    const columns = Array.from(
      new Set(
        body.columns
          .map((column) => String(column ?? "").trim())
          .filter((column) => column && column !== RECORD_KEY_FIELD),
      ),
    ).slice(0, MAX_COLUMNS);
    if (columns.length === 0) {
      return NextResponse.json({ error: "No usable columns" }, { status: 400 });
    }

    const rows = body.rows.map((row) => {
      const values: Record<string, string> = {};
      for (const column of columns) {
        values[column] = boundedCell(row?.[column]);
      }
      return { ...values, [RECORD_KEY_FIELD]: contentKey(values) };
    });

    const datasetName = `scraped_${name}`;
    const description = [String(body.description ?? "").trim(), body.sourceUrl ? `source: ${body.sourceUrl}` : "", body.purpose ? `purpose: ${body.purpose}` : ""]
      .filter(Boolean)
      .join(" — ")
      .slice(0, 600);

    const schema: DatasetSchema = {
      dataset: datasetName,
      description: description || undefined,
      recordPath: "rows[*]",
      fields: [
        { name: RECORD_KEY_FIELD, type: "string", sourcePath: RECORD_KEY_FIELD, identity: true },
        ...columns.map((column) => ({
          name: column,
          type: "string" as const,
          sourcePath: column,
        })),
      ],
    };

    const dataset = await saveDataset({ name: datasetName, description, schema });
    const outcome = await ingestRecords(dataset.id, { rows }, PROVENANCE);
    return NextResponse.json({
      ok: true,
      dataset: { id: dataset.id, name: datasetName },
      provenance: PROVENANCE,
      ...outcome,
    });
  } catch (err) {
    console.error("[api/scraper/datasets] POST error:", err);
    return NextResponse.json({ error: "Failed to store the collected rows" }, { status: 500 });
  }
}

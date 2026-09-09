import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { getOrCreateProfile, bulkImportTrades } from "@/lib/journal/data";
import { parseImportText, buildTemplate, IMPORT_FORMATS, type ImportFormat } from "@/lib/journal/import";

export const dynamic = "force-dynamic";

// GET /api/journal/import?format=mt4 — download a CSV template for a format.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const format = (searchParams.get("format") ?? "generic") as ImportFormat;
  const meta = IMPORT_FORMATS.find((f) => f.id === format);
  if (!meta) return NextResponse.json({ error: "Unknown format" }, { status: 400 });
  const csv = buildTemplate(format);
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": `attachment; filename="blackeclipse-${format}-template.csv"`,
    },
  });
}

// POST /api/journal/import — bulk import trades from CSV text.
// Body: { text: string, format?: ImportFormat }
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "journal-import", { limit: 10, windowMs: 60_000 });
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  try {
    const body = await request.json().catch(() => ({}));
    const text = typeof body.text === "string" ? body.text : "";
    if (!text.trim()) {
      return NextResponse.json({ error: "No CSV text provided" }, { status: 400 });
    }
    const format = (typeof body.format === "string" ? body.format : undefined) as ImportFormat | undefined;
    const { rows, format: detected, skipped } = parseImportText(text, format);
    if (rows.length === 0) {
      return NextResponse.json({ error: "No valid rows found in the CSV", skipped }, { status: 400 });
    }
    if (rows.length > 500) {
      return NextResponse.json({ error: "Too many rows (max 500)" }, { status: 400 });
    }
    const profileId = await getOrCreateProfile();
    const result = await bulkImportTrades(profileId, rows);
    return NextResponse.json({ success: true, format: detected, skipped, ...result });
  } catch (err) {
    console.error("[api/journal/import] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Import failed" },
      { status: 500 },
    );
  }
}

import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { getOrCreateProfile, bulkImportTrades, type CreateTradeInput } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// POST /api/journal/import — bulk import trades from CSV rows.
// Body: { rows: CreateTradeInput[] }
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "journal-import", { limit: 10, windowMs: 60_000 });
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  try {
    const body = await request.json().catch(() => ({}));
    const rows = Array.isArray(body.rows) ? (body.rows as CreateTradeInput[]) : [];
    if (rows.length === 0) {
      return NextResponse.json({ error: "No rows to import" }, { status: 400 });
    }
    if (rows.length > 500) {
      return NextResponse.json({ error: "Too many rows (max 500)" }, { status: 400 });
    }
    const profileId = await getOrCreateProfile();
    const result = await bulkImportTrades(profileId, rows);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    console.error("[api/journal/import] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Import failed" },
      { status: 500 },
    );
  }
}

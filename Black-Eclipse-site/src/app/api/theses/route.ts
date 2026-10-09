import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listTheses, createThesis } from "@/lib/theses/store";
import { THESIS_STATUSES, type ThesisInput } from "@/lib/theses/types";

export const dynamic = "force-dynamic";

// GET /api/theses?symbol=AAPL&status=active — list persisted theses.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  try {
    const theses = await listTheses({
      symbol: searchParams.get("symbol") || undefined,
      status: searchParams.get("status") || undefined,
    });
    return NextResponse.json({ theses });
  } catch (err) {
    console.error("[api/theses] GET error:", err);
    return NextResponse.json({ theses: [] }, { status: 500 });
  }
}

// POST /api/theses — create a thesis (revision 1 is recorded automatically).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "theses-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Partial<ThesisInput>;
    if (!body.symbol || !body.marketId || !body.title || !body.hypothesis) {
      return NextResponse.json(
        { error: "symbol, marketId, title and hypothesis are required" },
        { status: 400 },
      );
    }
    if (body.status && !THESIS_STATUSES.includes(body.status)) {
      return NextResponse.json({ error: "invalid status" }, { status: 400 });
    }
    const thesis = await createThesis({
      symbol: body.symbol,
      marketId: body.marketId,
      companyName: body.companyName ?? null,
      title: body.title,
      hypothesis: body.hypothesis,
      status: body.status,
      assumptions: body.assumptions ?? [],
      catalysts: body.catalysts ?? [],
      risks: body.risks ?? [],
      metrics: body.metrics ?? [],
      reviewDate: body.reviewDate ?? null,
      sourceArtifacts: body.sourceArtifacts ?? [],
    });
    return NextResponse.json({ success: true, thesis }, { status: 201 });
  } catch (err) {
    console.error("[api/theses] POST error:", err);
    return NextResponse.json({ error: "Failed to create thesis" }, { status: 500 });
  }
}

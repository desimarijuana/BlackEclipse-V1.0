import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { addEvidence, getThesis } from "@/lib/theses/store";
import { assessAssumptionImpacts, isStance, summarizeThesis } from "@/lib/theses/analysis";

export const dynamic = "force-dynamic";

// POST /api/theses/[id]/evidence — record supporting/contradicting evidence and
// return its deterministic impact on the stated assumptions. The thesis's own
// text is NOT modified here: a human reviews the impact and edits deliberately.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "theses-evidence");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as {
      stance?: unknown;
      summary?: unknown;
      sourceUrl?: string | null;
      sourceType?: string | null;
      publishedAt?: string | null;
    };
    if (!isStance(body.stance) || typeof body.summary !== "string" || !body.summary.trim()) {
      return NextResponse.json(
        { error: "stance (supporting|contradicting) and summary are required" },
        { status: 400 },
      );
    }
    const added = await addEvidence(id, {
      stance: body.stance,
      summary: body.summary,
      sourceUrl: body.sourceUrl ?? null,
      sourceType: body.sourceType ?? null,
      publishedAt: body.publishedAt ?? null,
    });
    if (!added) return NextResponse.json({ error: "Thesis not found" }, { status: 404 });
    const thesis = await getThesis(id);
    if (!thesis) return NextResponse.json({ error: "Thesis not found" }, { status: 404 });
    return NextResponse.json(
      {
        success: true,
        evidence: added,
        health: summarizeThesis(thesis),
        impact: assessAssumptionImpacts(thesis.assumptions, thesis.evidence),
      },
      { status: 201 },
    );
  } catch (err) {
    console.error("[api/theses] evidence POST error:", err);
    return NextResponse.json({ error: "Failed to add evidence" }, { status: 500 });
  }
}

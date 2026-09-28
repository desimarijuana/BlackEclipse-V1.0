import { NextResponse } from "next/server";
import { getSkillPromotionEvidence } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id/promotion-evidence?version= — operator evidence (advisory).
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const url = new URL(request.url);
    const version = url.searchParams.get("version");
    if (!version) return NextResponse.json({ error: "version is required" }, { status: 400 });
    const data = await getSkillPromotionEvidence(id, version);
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "promotion evidence failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

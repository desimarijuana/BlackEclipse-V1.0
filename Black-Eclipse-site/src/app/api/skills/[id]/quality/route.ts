import { NextResponse } from "next/server";
import { getSkillQuality } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id/quality — per-skill/version quality metrics (derived).
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const url = new URL(request.url);
    const data = await getSkillQuality(id, url.searchParams.get("version") || undefined);
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "quality lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

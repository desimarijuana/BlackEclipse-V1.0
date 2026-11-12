import { NextResponse } from "next/server";
import { compareSkillVersions } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id/quality/compare?older=&newer= — version regression view.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const url = new URL(request.url);
    const older = url.searchParams.get("older");
    const newer = url.searchParams.get("newer");
    if (!older || !newer) {
      return NextResponse.json({ error: "older and newer are required" }, { status: 400 });
    }
    const data = await compareSkillVersions(id, older, newer);
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "quality comparison failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { getSkillPreflight } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id/preflight — dependency/tool/permission preflight (read-only).
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const data = await getSkillPreflight(id);
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "preflight failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

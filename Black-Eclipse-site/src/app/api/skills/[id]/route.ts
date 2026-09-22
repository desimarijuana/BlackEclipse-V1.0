import { NextResponse } from "next/server";
import { getSkill } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id — full skill detail (validation, versions, history).
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const skill = await getSkill(id);
    if (!skill) return NextResponse.json({ error: "Skill not found" }, { status: 404 });
    return NextResponse.json({ success: true, skill });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

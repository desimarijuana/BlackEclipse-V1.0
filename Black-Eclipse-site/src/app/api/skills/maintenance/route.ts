import { NextResponse } from "next/server";
import { getSkillMaintenance } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/maintenance — read-only staleness/maintenance report.
export async function GET() {
  try {
    const data = await getSkillMaintenance();
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "maintenance report failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { getAuthoringMeta } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/authoring/tools — tools/permissions available to author a skill.
export async function GET() {
  try {
    return NextResponse.json({ success: true, ...(await getAuthoringMeta()) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "authoring metadata failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { learningJourney } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/learning/journey — the derived learning/provenance graph. Read-only.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const data = await learningJourney({
      kind: url.searchParams.get("kind") || undefined,
      status: url.searchParams.get("status") || undefined,
      since: url.searchParams.get("since") || undefined,
    });
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "journey failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { getOnboarding } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/onboarding — static, read-only first-run explanation + starter skills.
export async function GET() {
  try {
    const data = await getOnboarding();
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "onboarding unavailable" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

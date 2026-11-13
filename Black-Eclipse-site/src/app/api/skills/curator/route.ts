import { NextResponse } from "next/server";
import { getSkillCuratorReport } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/curator — read-only curator ledger (runs + proposals).
export async function GET() {
  try {
    const data = await getSkillCuratorReport();
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "curator report failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

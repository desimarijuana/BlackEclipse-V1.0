import { NextResponse } from "next/server";
import { getSkillVersionHistory } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id/version-history — versions with patch/eval/canary metadata.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const body = await getSkillVersionHistory(id);
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "version history failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

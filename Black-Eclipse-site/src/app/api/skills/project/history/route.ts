import { NextResponse } from "next/server";
import { projectTrustHistory } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/project/history — append-only project trust/approval/revoke
// audit history (who/what/when/level). Read only; hashes and ids, never content.
export async function GET(request: Request) {
  try {
    const path = new URL(request.url).searchParams.get("path") ?? undefined;
    const history = await projectTrustHistory(path);
    return NextResponse.json({ success: true, history });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "project trust history failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

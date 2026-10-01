import { NextResponse } from "next/server";
import { listCodeApprovals } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const approvals = await listCodeApprovals();
    return NextResponse.json({ success: true, approvals });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "approvals failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

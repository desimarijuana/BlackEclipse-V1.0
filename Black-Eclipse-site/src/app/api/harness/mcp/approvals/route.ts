import { NextResponse } from "next/server";
import { listMCPApprovals } from "@/lib/harness/clients/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/approvals — pending/decided effectful-tool approvals.
export async function GET(request: Request) {
  try {
    const status = new URL(request.url).searchParams.get("status") || undefined;
    const approvals = await listMCPApprovals(status);
    return NextResponse.json({ success: true, approvals });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP approval list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

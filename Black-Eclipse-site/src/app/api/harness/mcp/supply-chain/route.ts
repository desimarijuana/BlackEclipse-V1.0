import { NextResponse } from "next/server";
import { getMCPSupplyChain } from "@/lib/harness/clients/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/supply-chain — the offline, read-only supply-chain report.
// Never triggers a network call; a refresh is operator-gated and on-demand.
// The report contains no secrets; a read route carries no mutation guard.
export async function GET() {
  try {
    const data = await getMCPSupplyChain();
    return NextResponse.json({ ...data, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP supply-chain report failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

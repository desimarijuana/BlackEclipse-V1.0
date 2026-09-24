import { NextResponse } from "next/server";
import { listMCPIntegrations, listMCPWorkflows } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/meta — finance presets + workflow templates (read-only).
// This is the task-oriented layer: what a user recognises, not raw tool names.
export async function GET() {
  try {
    const [integrations, workflows] = await Promise.all([listMCPIntegrations(), listMCPWorkflows()]);
    return NextResponse.json({ success: true, integrations, workflows });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP meta failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

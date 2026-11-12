import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { installMCPIntegration } from "@/lib/harness/clients/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/integrations/[id]/install — write a recommended preset
// into the config as a DISABLED, nothing-selected entry (operator-gated).
// Install is not activation; the user still reviews, adds a secret and selects.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-install-integration");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const result = await installMCPIntegration(id);
    return NextResponse.json({ ...result, success: result.success !== false });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP install failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

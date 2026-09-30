import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { mcpOauthLogout } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/servers/[id]/logout — clear stored OAuth credentials
// (operator-gated). The server stays configured but disconnected.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-oauth-logout");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const result = await mcpOauthLogout(id);
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP logout failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

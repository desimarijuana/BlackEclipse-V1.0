import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { mcpOauthLogin } from "@/lib/harness/clients/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/servers/[id]/login — start an OAuth device-code login
// (operator-gated). The token is stored encrypted and never returned here.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-oauth-login");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const body = (await request.json().catch(() => ({}))) as { scope?: string };
    const result = await mcpOauthLogin(id, body.scope ?? "");
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP login failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

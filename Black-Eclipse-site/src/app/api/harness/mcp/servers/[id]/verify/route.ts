import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { verifyMCPServer } from "@/lib/harness/clients/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/servers/:id/verify — operator-triggered credential
// verification. Calls ONE operator-chosen read tool with operator-supplied
// arguments, bounded by a short timeout. It is NEVER automatic, never at boot,
// and never in a loop, and the response body is never returned (only a
// content-free verdict). Separate from Test, which only proves the process
// started and listed tools.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-verify");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as {
      tool?: string;
      arguments?: Record<string, unknown>;
    };
    const tool = typeof body.tool === "string" ? body.tool.trim() : "";
    if (!tool) {
      return NextResponse.json({ error: "a read tool name is required" }, { status: 400 });
    }
    const result = await verifyMCPServer(id, tool, body.arguments ?? {});
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP verify failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

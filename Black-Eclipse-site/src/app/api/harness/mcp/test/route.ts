import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { testMCPServer } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { MCPServerInput } from "@/lib/harness/mcp-types";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/test — connect + discover a candidate config without
// persisting or activating it (operator-gated at the front door; the runtime
// independently authorizes by loopback/token).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "mcp-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { server?: MCPServerInput };
    if (!body.server || typeof body.server.command !== "string" || !body.server.command.trim()) {
      return NextResponse.json({ error: "server.command is required" }, { status: 400 });
    }
    const result = await testMCPServer(body.server);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP test failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

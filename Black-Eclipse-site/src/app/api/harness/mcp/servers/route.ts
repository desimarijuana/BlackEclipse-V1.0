import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listMCPServers, upsertMCPServer, isOperatorRequest } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { MCPServerInput } from "@/lib/harness/mcp-types";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/servers — the MCP server catalog (secret-free).
export async function GET() {
  try {
    const data = await listMCPServers();
    return NextResponse.json({ ...data, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// POST /api/harness/mcp/servers — add or replace a server (operator-gated).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "mcp-servers");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { server?: MCPServerInput; envKeys?: string[] };
    const server = body.server;
    if (!server || typeof server.id !== "string" || !server.id.trim()) {
      return NextResponse.json({ error: "server.id is required" }, { status: 400 });
    }
    if (typeof server.command !== "string" || !server.command.trim()) {
      return NextResponse.json({ error: "server.command is required" }, { status: 400 });
    }
    const envKeys = Array.isArray(body.envKeys) ? body.envKeys.filter((k) => typeof k === "string") : undefined;
    const result = await upsertMCPServer(server, isOperatorRequest(request), envKeys);
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP save failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

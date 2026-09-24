import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { deleteMCPServer } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// DELETE /api/harness/mcp/servers/:id — remove a server (operator-gated at the
// front door; the runtime independently authorizes by loopback/token).
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-servers-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const result = await deleteMCPServer(id);
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const notFound = err instanceof Error && /404/.test(err.message);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP delete failed" },
      { status: unavailable ? 503 : notFound ? 404 : 400 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { confirmMCPCatalog } from "@/lib/harness/clients/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/servers/:id/confirm — record the operator's review of a
// server's current catalog digest. This is what lets an annotation-sourced
// read-only tool activate; a changed catalog requires re-confirmation.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-confirm");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const result = await confirmMCPCatalog(id);
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP confirm failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

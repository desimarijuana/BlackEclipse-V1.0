import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { decideMCPApproval } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/approvals/:id/decide — approve/deny an effectful call.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-approval-decide");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as { approve?: unknown; reason?: unknown; remember?: unknown };
    const approval = await decideMCPApproval(
      id,
      Boolean(body.approve),
      typeof body.reason === "string" ? body.reason : "",
      Boolean(body.remember),
    );
    return NextResponse.json({ success: true, approval });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const notFound = err instanceof Error && /404/.test(err.message);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP approval decision failed" },
      { status: unavailable ? 503 : notFound ? 404 : 400 }
    );
  }
}

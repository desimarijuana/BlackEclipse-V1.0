import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { decideCodeApproval } from "@/lib/harness/code-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "code-approval-decide");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { approve?: boolean; reason?: string };
  try {
    const result = await decideCodeApproval(id, Boolean(body.approve), body.reason ?? "");
    return NextResponse.json({ success: true, result });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "decide failed" }, { status: 500 });
  }
}

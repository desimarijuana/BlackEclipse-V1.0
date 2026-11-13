import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { rejectCuratorProposal } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/curator/proposals/[id]/reject — operator rejection.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "skill-curator-reject");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    let notes = "";
    try {
      const body = (await request.json()) as { notes?: string };
      notes = body?.notes ?? "";
    } catch {
      // no body
    }
    const data = await rejectCuratorProposal(id, notes);
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "curator rejection failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { approveCuratorProposal } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/curator/proposals/[id]/approve — operator approval.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "skill-curator-approve");
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
    const data = await approveCuratorProposal(id, notes);
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "curator approval failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

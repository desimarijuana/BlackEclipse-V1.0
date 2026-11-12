import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { rollbackEvolutionCandidate } from "@/lib/harness/clients/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "evolution-rollback");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { reason?: string };
  try {
    const result = await rollbackEvolutionCandidate(id, body.reason ?? "");
    return NextResponse.json({ success: true, result });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "rollback failed" }, { status: 500 });
  }
}

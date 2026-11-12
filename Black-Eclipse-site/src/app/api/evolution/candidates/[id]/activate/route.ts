import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { activateEvolutionCandidate } from "@/lib/harness/clients/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "evolution-activate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { canary?: boolean };
  try {
    const result = await activateEvolutionCandidate(id, Boolean(body.canary));
    return NextResponse.json({ success: true, result });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "activate failed" }, { status: 500 });
  }
}

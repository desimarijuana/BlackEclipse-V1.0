import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { evaluateEvolutionCandidate } from "@/lib/harness/clients/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "evolution-evaluate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const result = await evaluateEvolutionCandidate(id);
    return NextResponse.json({ success: true, result });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "evaluate failed" }, { status: 500 });
  }
}

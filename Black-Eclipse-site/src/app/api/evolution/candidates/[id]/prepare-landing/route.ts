import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { prepareEvolutionLanding } from "@/lib/harness/clients/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "evolution-prepare-landing");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const result = await prepareEvolutionLanding(id);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "prepare landing failed" },
      { status: 400 },
    );
  }
}

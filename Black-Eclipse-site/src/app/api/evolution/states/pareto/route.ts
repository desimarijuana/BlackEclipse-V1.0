import { NextResponse } from "next/server";
import { getEvolutionStatesPareto } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  try {
    const result = await getEvolutionStatesPareto({
      scope: params.get("scope") ?? undefined,
      limit: Number(params.get("limit") ?? 100),
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "pareto frontier failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

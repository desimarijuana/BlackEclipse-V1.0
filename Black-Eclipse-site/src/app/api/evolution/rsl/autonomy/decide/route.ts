import { NextResponse } from "next/server";
import { decideEvolutionAutonomy } from "@/lib/harness/evolution-client";
import type { EvolutionAutonomyDecideInput } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Partial<
      EvolutionAutonomyDecideInput
    >;
    if (typeof body.risk !== "string" || !body.risk.trim()) {
      return NextResponse.json(
        { error: "risk is required" },
        { status: 400 },
      );
    }
    const result = await decideEvolutionAutonomy({
      ...body,
      risk: body.risk,
    });
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "autonomy decision failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

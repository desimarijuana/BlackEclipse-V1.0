import { NextResponse } from "next/server";
import { listEvolutionStates } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const limit = Number(params.get("limit") ?? 50);
  try {
    const result = await listEvolutionStates({
      scope: params.get("scope") ?? undefined,
      status: params.get("status") ?? undefined,
      limit: Number.isFinite(limit) ? Math.max(1, Math.min(200, limit)) : 50,
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "state list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

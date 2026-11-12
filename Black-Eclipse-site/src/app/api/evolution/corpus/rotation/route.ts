import { NextResponse } from "next/server";
import { getEvolutionRotationPreview } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const countValue = Number(params.get("count") ?? 12);
  try {
    const result = await getEvolutionRotationPreview({
      quarter: params.get("quarter") ?? undefined,
      count: Number.isFinite(countValue) ? countValue : 12,
    });
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "rotation preview failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

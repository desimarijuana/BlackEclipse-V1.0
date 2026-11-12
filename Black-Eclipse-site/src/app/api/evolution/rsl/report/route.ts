import { NextResponse } from "next/server";
import { getEvolutionRslReport } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const daysValue = Number(params.get("days") ?? 7);
  const limitValue = Number(params.get("limit") ?? 10);
  try {
    const report = await getEvolutionRslReport({
      days: Number.isFinite(daysValue) ? daysValue : 7,
      scope: params.get("scope") ?? undefined,
      limit: Number.isFinite(limitValue) ? limitValue : 10,
    });
    return NextResponse.json({ ...report, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "rsl report failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

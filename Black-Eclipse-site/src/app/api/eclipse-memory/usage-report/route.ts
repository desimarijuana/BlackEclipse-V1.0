import { NextResponse } from "next/server";
import { memoryUsageReport } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/usage-report — real-usage measurement (read-only).
// Complements the synthetic labeled evals, which only prove the detector
// implements its rules. Bounded, content-free, writes nothing.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const windowDays = Number(url.searchParams.get("windowDays") ?? "30") || 30;
  try {
    const body = await memoryUsageReport(windowDays);
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "usage report failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

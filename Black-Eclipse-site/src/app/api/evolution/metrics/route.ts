import { NextResponse } from "next/server";
import { evolutionMetrics } from "@/lib/harness/evolution-client";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const days = Number(new URL(request.url).searchParams.get("windowDays") ?? 90);
  try {
    const metrics = await evolutionMetrics(
      Number.isFinite(days) ? Math.max(1, Math.min(365, days)) : 90,
    );
    return NextResponse.json({ success: true, metrics });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "metrics failed" }, { status: 500 });
  }
}

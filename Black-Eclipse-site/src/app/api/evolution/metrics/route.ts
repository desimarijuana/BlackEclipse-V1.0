import { NextResponse } from "next/server";
import { evolutionMetrics } from "@/lib/harness/evolution-client";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const metrics = await evolutionMetrics();
    return NextResponse.json({ success: true, metrics });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "metrics failed" }, { status: 500 });
  }
}

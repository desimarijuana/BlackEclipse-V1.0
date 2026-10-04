import { NextResponse } from "next/server";
import { getRuntimeRouting, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/model-runtime/routing — the task profiles, aliases and active
// routing policy. Read-only.
export async function GET() {
  try {
    const routing = await getRuntimeRouting();
    return NextResponse.json({ success: true, ...routing });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/routing] GET error:", err);
    return NextResponse.json({ error: "Failed to load routing config" }, { status });
  }
}

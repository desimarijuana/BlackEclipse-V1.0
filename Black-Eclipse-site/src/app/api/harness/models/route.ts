import { NextResponse } from "next/server";
import { listModelProviders, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/models — the universal provider catalog owned by the Python
// runtime (first-party LangChain integrations + every OpenAI-compatible
// endpoint).
export async function GET() {
  try {
    const providers = await listModelProviders();
    return NextResponse.json({ success: true, providers });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/models] GET error:", err);
    return NextResponse.json({ error: "Failed to load model catalog" }, { status });
  }
}

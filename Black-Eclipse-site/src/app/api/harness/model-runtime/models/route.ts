import { NextResponse } from "next/server";
import { listRuntimeModels, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/model-runtime/models?provider=<id> — the normalized model
// registry (capabilities, context window, pricing, status). Read-only.
export async function GET(request: Request) {
  try {
    const provider = new URL(request.url).searchParams.get("provider") ?? undefined;
    const models = await listRuntimeModels(provider || undefined);
    return NextResponse.json({ success: true, models });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/models] GET error:", err);
    return NextResponse.json({ error: "Failed to load models" }, { status });
  }
}

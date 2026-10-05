import { NextResponse } from "next/server";
import { discoverRuntimeModels, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/model-runtime/providers/<id>/discover — probe a live provider
// (a local server's installed models, a router's catalog) and register what it
// serves. Connection details are forwarded to the runtime for this one probe and
// are never persisted or echoed back. A failed probe returns ok:false + reason.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const result = await discoverRuntimeModels(id, {
      baseUrl: typeof body.baseUrl === "string" ? body.baseUrl : undefined,
      apiKey: typeof body.apiKey === "string" ? body.apiKey : undefined,
      model: typeof body.model === "string" ? body.model : undefined,
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/providers/[id]/discover] POST error:", err);
    return NextResponse.json({ error: "Failed to discover models" }, { status });
  }
}

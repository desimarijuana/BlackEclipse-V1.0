import { NextResponse } from "next/server";
import { memoryProviderStatus } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/memory-providers/status — provider health/capabilities (content-free).
export async function GET() {
  try {
    const body = await memoryProviderStatus();
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "provider status failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

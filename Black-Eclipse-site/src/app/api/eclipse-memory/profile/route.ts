import { NextResponse } from "next/server";
import { memoryProfile } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/profile — the compact prompt profile projection:
// selected memories, excluded memories + reasons, char/token estimate, preview.
export async function GET(request: Request) {
  try {
    const scopeId = new URL(request.url).searchParams.get("scopeId") || undefined;
    const result = await memoryProfile(scopeId);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "profile generation failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

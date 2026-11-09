import { NextResponse } from "next/server";
import { memoryLifecycle } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/lifecycle?view=… — counts + a named lifecycle view.
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const body = await memoryLifecycle(
      searchParams.get("view") ?? undefined,
      searchParams.get("scopeId") ?? undefined,
      Number(searchParams.get("limit") ?? 50),
      Number(searchParams.get("offset") ?? 0)
    );
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "lifecycle lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { memoryProviderTest } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/memory-providers/test — bounded, non-destructive provider probe
// (health + capped search). Operator-gated.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-provider-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { provider?: string };
    const result = await memoryProviderTest(body.provider ?? "native");
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "provider test failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

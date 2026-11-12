import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { resetMemory } from "@/lib/harness/clients/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/reset — memory-domain reset; explicit confirm required.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-reset");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { confirm?: boolean };
    if (body.confirm !== true) {
      return NextResponse.json({ error: "reset requires confirm=true" }, { status: 400 });
    }
    const result = await resetMemory(true, true);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "reset failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

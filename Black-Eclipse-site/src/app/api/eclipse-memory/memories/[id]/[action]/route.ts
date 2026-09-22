import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { archiveMemory, reviewMemory } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/memories/:id/:action — archive | review.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;
  if (action !== "archive" && action !== "review") {
    return NextResponse.json({ error: "unsupported action" }, { status: 404 });
  }
  const blocked = guardMutation(request, `eclipse-memory-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const result =
      action === "archive"
        ? await archiveMemory(id, true, typeof body.status === "string" ? body.status : "archived")
        : await reviewMemory(id, true, body.approve !== false);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

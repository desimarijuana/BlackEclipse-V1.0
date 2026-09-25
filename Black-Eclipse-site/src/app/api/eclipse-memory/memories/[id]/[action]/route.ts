import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { archiveMemory, renewMemory, restoreMemory, reviewMemory } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

const SUPPORTED = new Set(["archive", "review", "restore", "renew"]);

// POST /api/eclipse-memory/memories/:id/:action — archive | review | restore | renew.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;
  if (!SUPPORTED.has(action)) {
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
        : action === "review"
          ? await reviewMemory(id, true, body.approve !== false)
          : action === "restore"
            ? await restoreMemory(id, true)
            : await renewMemory(id, true, typeof body.days === "number" ? body.days : undefined);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

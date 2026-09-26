import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { MemoryFileName } from "@/lib/harness/memory-files";
import { diffText, listRevisions, rollbackFile } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/files/history?file=USER_PROFILE.md[&revision=rev_...]
// Returns the revision history, and for a named revision the bounded diff
// between its `before` state and its `after` state.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const file = (url.searchParams.get("file") ?? "USER_PROFILE.md") as MemoryFileName;
    const revisionId = url.searchParams.get("revision");
    const revisions = await listRevisions(file);
    const revision = revisionId ? revisions.find((r) => r.revision === revisionId) ?? null : null;
    const diff = revision && revision.before !== null
      ? diffText(revision.before, revision.after)
      : null;
    return NextResponse.json({ success: true, file, revisions, revision, diff });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "history failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
// POST /api/eclipse-memory/files/history — operator: roll one file back to a
// named revision (atomic, and itself recorded as a new revision).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-files-rollback");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const file = String(body.file ?? "USER_PROFILE.md") as MemoryFileName;
    const revision = String(body.revision ?? "");
    const result = await rollbackFile(file, revision);
    return NextResponse.json({ success: result.restored, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "rollback failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

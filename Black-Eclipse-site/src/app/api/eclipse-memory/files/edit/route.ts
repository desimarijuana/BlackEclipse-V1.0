import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { FileEditOperation } from "@/lib/harness/memory-files";
import { applyFileEdit } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

const OPERATIONS = new Set<FileEditOperation>([
  "add", "replace", "archive", "restore", "merge", "split", "reorder", "consolidate",
]);

// POST /api/eclipse-memory/files/edit — a targeted Markdown edit with an
// `expectedVersion` stale-edit guard. Writes atomically after a backup revision;
// returns the resulting entries so the caller may route them through the gated
// import pipeline. The file is never the source of truth.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-files-edit");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const operation = String(body.operation ?? "") as FileEditOperation;
    if (!OPERATIONS.has(operation)) {
      return NextResponse.json({ error: `unsupported operation: ${operation}` }, { status: 400 });
    }
    const result = await applyFileEdit({
      operation,
      file: String(body.file ?? "") as never,
      memoryId: body.memoryId ? String(body.memoryId) : undefined,
      expectedVersion: body.expectedVersion ? String(body.expectedVersion) : undefined,
      content: body.content !== undefined ? String(body.content) : undefined,
    });
    return NextResponse.json(result, { status: result.ok ? 200 : 409 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "file edit failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

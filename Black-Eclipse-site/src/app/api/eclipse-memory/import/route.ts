import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { importMemory } from "@/lib/harness/clients/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { MemoryExportDocument } from "@/lib/harness/eclipse-memory-types";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/import — validated import through the normal pipeline.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-import");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as {
      document?: MemoryExportDocument;
      dryRun?: boolean;
    };
    if (!body.document) {
      return NextResponse.json({ error: "a document is required" }, { status: 400 });
    }
    const result = await importMemory(body.document, true, body.dryRun === true);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "import failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

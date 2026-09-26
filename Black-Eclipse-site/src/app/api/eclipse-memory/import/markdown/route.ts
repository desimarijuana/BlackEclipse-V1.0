import { NextResponse } from "next/server";
import { importMemory } from "@/lib/harness/eclipse-memory-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { backupMemoryFiles, previewMemoryImport, toExportDocument } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/import/markdown — preview what WOULD be imported.
export async function GET() {
  try {
    const parsed = await previewMemoryImport();
    return NextResponse.json({ success: true, preview: true, ...parsed });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "import preview failed" },
      { status: 500 }
    );
  }
}

// POST /api/eclipse-memory/import/markdown — operator: apply the import.
// Backs up first, then writes each parsed entry through the normal gated
// pipeline. `{ dryRun: true }` previews through the runtime without writing.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-files-import");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { dryRun?: boolean };
    const parsed = await previewMemoryImport();
    const document = toExportDocument(parsed);
    const backupDir = body.dryRun ? null : await backupMemoryFiles();
    const report = await importMemory(document, true, Boolean(body.dryRun));
    return NextResponse.json({ ...report, backupDir, ignored: parsed.ignored });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "markdown import failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

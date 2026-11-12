import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { restoreMemoryFiles } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/files/restore — operator: restore the last (or a
// named) backup of the Markdown files.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-files-restore");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { backupId?: string };
    const result = await restoreMemoryFiles(body.backupId);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "restore failed" },
      { status: 400 }
    );
  }
}

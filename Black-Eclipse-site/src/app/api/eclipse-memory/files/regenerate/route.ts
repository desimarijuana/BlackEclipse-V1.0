import { NextResponse } from "next/server";
import { listMemories, memoryProfile } from "@/lib/harness/eclipse-memory-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { backupMemoryFiles, memoryFilesRoot, regenerateMemoryFiles } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/files/regenerate — operator: write all four Markdown
// files from the current database (after backing up the previous state).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-files-regenerate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const backupDir = await backupMemoryFiles();
    const [memories, profile] = await Promise.all([listMemories({ limit: 500 }), memoryProfile()]);
    const snapshot = await regenerateMemoryFiles(memories, profile);
    return NextResponse.json({ success: true, root: memoryFilesRoot(), backupDir, files: Object.keys(snapshot.files) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory file regeneration failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

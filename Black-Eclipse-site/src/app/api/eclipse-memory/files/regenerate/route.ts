import { NextResponse } from "next/server";
import { listMemories, memoryProfile } from "@/lib/harness/eclipse-memory-client";
import { listSkills } from "@/lib/harness/skills-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { memoryFilesRoot, regenerateMemoryFiles } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/files/regenerate — operator: write all Markdown files
// from the current database. `regenerateMemoryFiles` backs up the previous state
// and writes each file atomically (temp + fsync + rename).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-files-regenerate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const [memories, profile, skills] = await Promise.all([
      listMemories({ limit: 500 }),
      memoryProfile(),
      listSkills().catch(() => ({ skills: [] as Array<{ id: string; name: string; status: string; version?: string }> })),
    ]);
    const skillIndex = (skills.skills ?? []).map((s) => ({ id: s.id, name: s.name, status: s.status, version: s.version }));
    const snapshot = await regenerateMemoryFiles(memories, profile, skillIndex);
    return NextResponse.json({ success: true, root: memoryFilesRoot(), backupDir: snapshot.backupDir, files: Object.keys(snapshot.files) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory file regeneration failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

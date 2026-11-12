import { NextResponse } from "next/server";
import { listMemories, memoryProfile } from "@/lib/harness/clients/eclipse-memory-client";
import { listSkills } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { memoryFilesRoot, renderMemoryFiles } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/files — the generated Markdown projection (read-only).
// Generates in memory and returns the content for preview; it does NOT write.
export async function GET() {
  try {
    const [memories, profile, skills] = await Promise.all([
      listMemories({ limit: 500 }),
      memoryProfile(),
      listSkills().catch(() => ({ skills: [] as Array<{ id: string; name: string; status: string; version?: string }> })),
    ]);
    const root = memoryFilesRoot();
    const skillIndex = (skills.skills ?? []).map((s) => ({ id: s.id, name: s.name, status: s.status, version: s.version }));
    return NextResponse.json({ success: true, root, files: renderMemoryFiles(memories, profile, skillIndex) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory file generation failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

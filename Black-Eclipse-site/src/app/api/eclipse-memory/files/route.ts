import { NextResponse } from "next/server";
import { listMemories, memoryProfile } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { memoryFilesRoot, renderMemoryFiles } from "@/lib/harness/memory-files";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/files — the generated Markdown projection (read-only).
// Generates in memory and returns the content for preview; it does NOT write.
export async function GET() {
  try {
    const [memories, profile] = await Promise.all([listMemories({ limit: 500 }), memoryProfile()]);
    const root = memoryFilesRoot();
    return NextResponse.json({ success: true, root, files: renderMemoryFiles(memories, profile) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory file generation failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

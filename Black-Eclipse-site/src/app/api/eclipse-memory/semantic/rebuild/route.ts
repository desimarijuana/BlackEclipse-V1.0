import { NextResponse } from "next/server";
import { rebuildSemanticIndex } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/semantic/rebuild — clear/rebuild the optional local
// semantic index. Honest: v1 backends hold no persistent index, so this reports
// that fact. It never deletes memory and never downloads a model.
export async function POST() {
  try {
    const body = await rebuildSemanticIndex();
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "semantic rebuild failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { getMemory } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/memories/:id — one memory with evidence + links.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const detail = await getMemory(id);
    if (!detail) return NextResponse.json({ error: "Memory not found" }, { status: 404 });
    return NextResponse.json({ success: true, ...detail });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

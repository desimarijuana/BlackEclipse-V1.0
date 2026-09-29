import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/semantic-status — RETIRED tombstone.
// The optional semantic candidate layer was removed on the evidence that it
// added no measurable recall at a safe threshold (deterministic normalization
// closed the gap). Kept so an old client gets a truthful answer, not a 404.
export async function GET() {
  return NextResponse.json({
    success: true,
    retired: true,
    mode: "lexical",
    lexicalActive: true,
    semanticEnabled: false,
    semanticAvailable: false,
    reason:
      "the semantic candidate layer was removed; deterministic lexical detection is authoritative",
    doc: "docs/harness/memory-contradiction-detection.md",
  });
}

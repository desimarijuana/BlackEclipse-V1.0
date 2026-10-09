import { NextResponse } from "next/server";
import { listRevisions } from "@/lib/theses/store";

export const dynamic = "force-dynamic";

// GET /api/theses/[id]/revisions — the immutable version history (newest first).
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const revisions = await listRevisions(id);
  return NextResponse.json({ revisions });
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getThesis, updateThesis, deleteThesis } from "@/lib/theses/store";
import { THESIS_STATUSES, type ThesisUpdate } from "@/lib/theses/types";

export const dynamic = "force-dynamic";

// GET /api/theses/[id] — one thesis with evidence.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const thesis = await getThesis(id);
  if (!thesis) return NextResponse.json({ error: "Thesis not found" }, { status: 404 });
  return NextResponse.json({ thesis });
}

// PATCH /api/theses/[id] — update; appends an immutable revision first.
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "theses-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as ThesisUpdate;
    if (body.status && !THESIS_STATUSES.includes(body.status)) {
      return NextResponse.json({ error: "invalid status" }, { status: 400 });
    }
    const thesis = await updateThesis(id, body);
    if (!thesis) return NextResponse.json({ error: "Thesis not found" }, { status: 404 });
    return NextResponse.json({ success: true, thesis });
  } catch (err) {
    console.error("[api/theses] PATCH error:", err);
    return NextResponse.json({ error: "Failed to update thesis" }, { status: 500 });
  }
}

// DELETE /api/theses/[id]
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "theses-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const ok = await deleteThesis(id);
    if (!ok) return NextResponse.json({ error: "Thesis not found" }, { status: 404 });
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/theses] DELETE error:", err);
    return NextResponse.json({ error: "Failed to delete thesis" }, { status: 500 });
  }
}

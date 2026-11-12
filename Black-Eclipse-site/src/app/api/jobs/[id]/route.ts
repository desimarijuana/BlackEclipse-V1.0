import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { deleteJob, getJob, updateJob } from "@/lib/harness/clients/jobs-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const job = await getJob(id);
    return NextResponse.json({ success: true, job });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "job not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "job-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  try {
    const job = await updateJob(id, body);
    return NextResponse.json({ success: true, job });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "job update failed" }, { status: 400 });
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "job-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    await deleteJob(id);
    return NextResponse.json({ success: true, deleted: id });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "job delete failed" }, { status: 500 });
  }
}

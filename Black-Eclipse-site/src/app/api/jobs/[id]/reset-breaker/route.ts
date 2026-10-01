import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { resetJobBreaker } from "@/lib/harness/jobs-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "job-reset-breaker");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const job = await resetJobBreaker(id);
    return NextResponse.json({ success: true, job });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "reset failed" }, { status: 500 });
  }
}

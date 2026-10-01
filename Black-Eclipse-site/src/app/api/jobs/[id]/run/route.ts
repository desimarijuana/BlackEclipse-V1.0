import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { runJobNow } from "@/lib/harness/jobs-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "job-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const result = await runJobNow(id);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "run failed" }, { status: 500 });
  }
}

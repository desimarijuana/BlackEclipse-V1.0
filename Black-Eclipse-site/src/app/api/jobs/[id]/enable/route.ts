import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { setJobEnabled } from "@/lib/harness/clients/jobs-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "job-enable");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    const job = await setJobEnabled(id, true);
    return NextResponse.json({ success: true, job });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "enable failed" }, { status: 500 });
  }
}

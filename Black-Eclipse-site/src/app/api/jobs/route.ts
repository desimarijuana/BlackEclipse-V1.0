import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { createJob, listJobs, type CreateJobInput } from "@/lib/harness/jobs-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const jobs = await listJobs();
    return NextResponse.json({ success: true, jobs });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "job list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "job-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as CreateJobInput;
    const result = await createJob(body);
    return NextResponse.json({ success: true, job: result.job, webhookToken: result.webhookToken });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "job create failed" }, { status: 500 });
  }
}

import { NextResponse } from "next/server";
import { listJobTemplates } from "@/lib/harness/clients/jobs-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const templates = await listJobTemplates();
    return NextResponse.json({ success: true, templates });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "template list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

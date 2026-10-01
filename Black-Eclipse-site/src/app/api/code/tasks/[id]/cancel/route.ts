import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { cancelCodeTask } from "@/lib/harness/code-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "code-task-cancel");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    return NextResponse.json({ success: true, ...(await cancelCodeTask(id)) });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "cancel failed" }, { status: 500 });
  }
}

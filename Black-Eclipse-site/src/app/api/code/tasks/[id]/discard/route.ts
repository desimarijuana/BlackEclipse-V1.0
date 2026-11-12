import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { discardCodeTask } from "@/lib/harness/clients/code-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "code-task-discard");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  try {
    return NextResponse.json({ success: true, ...(await discardCodeTask(id)) });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "discard failed" }, { status: 500 });
  }
}

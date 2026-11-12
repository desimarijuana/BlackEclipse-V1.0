import { NextResponse } from "next/server";
import { runShell } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/code/shell — one command through the host shell for the terminal panel.
export async function POST(req: Request) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      command?: string;
      cwd?: string;
      timeoutS?: number;
    };
    if (!body.command || typeof body.command !== "string") {
      return NextResponse.json({ error: "command is required" }, { status: 400 });
    }
    const result = await runShell(body.command, { cwd: body.cwd, timeoutS: body.timeoutS });
    return NextResponse.json({ success: true, result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "shell run failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

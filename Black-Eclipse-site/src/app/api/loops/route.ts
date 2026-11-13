import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  createLoop,
  listLoops,
  type CreateLoopInput,
} from "@/lib/harness/clients/autonomy-client";
import { resolveRunModelSettings } from "@/lib/harness/run-service";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

const KINDS = ["loop", "heartbeat"] as const;
const MODES = ["fixed", "self_paced"] as const;

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const loops = await listLoops({
      sessionId: url.searchParams.get("sessionId") ?? undefined,
      status: url.searchParams.get("status") ?? undefined,
    });
    return NextResponse.json({ success: true, loops });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "loop list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "loop-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Partial<CreateLoopInput>;
    const sessionId = typeof body.sessionId === "string" ? body.sessionId.trim() : "";
    const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
    if (!sessionId) return NextResponse.json({ error: "sessionId is required" }, { status: 400 });
    if (!prompt) return NextResponse.json({ error: "prompt is required" }, { status: 400 });
    const kind = (body.kind ?? "loop") as (typeof KINDS)[number];
    if (!KINDS.includes(kind)) {
      return NextResponse.json({ error: "unknown loop kind" }, { status: 400 });
    }
    const mode = (body.mode ?? "fixed") as (typeof MODES)[number];
    if (!MODES.includes(mode)) {
      return NextResponse.json({ error: "unknown loop mode" }, { status: 400 });
    }
    const model =
      body.model && (body.model.provider || body.model.model)
        ? body.model
        : await resolveRunModelSettings(undefined);
    const loop = await createLoop({
      sessionId,
      kind,
      prompt,
      mode,
      intervalSeconds: typeof body.intervalSeconds === "number" ? body.intervalSeconds : undefined,
      maxTicks: typeof body.maxTicks === "number" ? body.maxTicks : undefined,
      workspaceId: typeof body.workspaceId === "string" ? body.workspaceId : undefined,
      model: { provider: model.provider, model: model.model, baseUrl: model.baseUrl },
    });
    return NextResponse.json({ success: true, loop });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "loop create failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

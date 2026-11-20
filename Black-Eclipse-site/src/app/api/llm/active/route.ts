import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { setActiveModel } from "@/lib/agent/connection";
import { invalidateSettingsCache } from "@/lib/settings-route-cache";

export const dynamic = "force-dynamic";

/**
 * POST /api/llm/active — switch the active model for an already-connected
 * provider without re-entering the key. Body: { providerId, model, baseUrl? }.
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "llm-active");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const providerId = typeof body.providerId === "string" ? body.providerId : "";
  const model = typeof body.model === "string" ? body.model : "";
  if (!providerId || !model.trim()) {
    return NextResponse.json({ ok: false, message: "providerId and model are required." }, { status: 400 });
  }

  const result = await setActiveModel({
    providerId,
    model,
    baseUrl: typeof body.baseUrl === "string" ? body.baseUrl : undefined,
    connectionId: typeof body.connectionId === "string" ? body.connectionId : undefined,
  });
  if (result.ok) invalidateSettingsCache();
  return NextResponse.json(result, { status: result.ok ? 200 : 400 });
}

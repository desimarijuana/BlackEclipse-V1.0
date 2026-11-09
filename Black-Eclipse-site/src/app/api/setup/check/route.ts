import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import { runSetupCheck } from "@/lib/setup/check";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

// POST /api/setup/check — run real, bounded readiness probes. A stored key with
// a rejected request is reported as failed, never as success.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "setup-check");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const limited = rateLimit("setup-check", { limit: 6, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json(
      { error: `Too many checks — retry in ${limited.retryAfterSec}s` },
      { status: 429 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as {
    ai?: unknown;
    aiConfig?: unknown;
    sources?: unknown;
  };

  const aiConfig =
    body.aiConfig && typeof body.aiConfig === "object"
      ? (() => {
          const raw = body.aiConfig as Record<string, unknown>;
          return {
            baseUrl: typeof raw.baseUrl === "string" ? raw.baseUrl : undefined,
            model: typeof raw.model === "string" ? raw.model : undefined,
            apiKey: typeof raw.apiKey === "string" ? raw.apiKey : undefined,
          };
        })()
      : undefined;

  try {
    const result = await runSetupCheck({
      ai: body.ai !== false,
      aiConfig,
      sources: Array.isArray(body.sources)
        ? body.sources.filter((id): id is string => typeof id === "string")
        : undefined,
    });
    return NextResponse.json(result);
  } catch (err) {
    console.error("[api/setup/check] error:", err);
    return NextResponse.json({ error: "Check failed" }, { status: 500 });
  }
}

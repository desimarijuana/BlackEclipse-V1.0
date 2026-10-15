import { guardMutation } from "@/lib/api-guard";
import { executeCommandFromText, type CommandResult } from "@/lib/harness/command-router";
import { isOperatorRequest } from "@/lib/harness/skills-client";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// POST /api/harness/command — execute a slash command directly.
//
// The chat surfaces intercept routed commands inline; this route is the explicit
// entry point (and the one an external caller/tool can use). It runs the SAME
// shared router, so parse/resolve/validate/authorize/execute/render are identical.
// Body: { text: string }
export async function POST(request: Request): Promise<Response> {
  const blocked = guardMutation(request, "harness-command");
  if (blocked) {
    return Response.json(blocked.body, { status: blocked.status });
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!text) return Response.json({ error: "text is required" }, { status: 400 });
  if (text.length > 4000) return Response.json({ error: "text too long (max 4000 chars)" }, { status: 400 });

  const result: CommandResult | null = await executeCommandFromText(text, {
    operator: isOperatorRequest(request),
  });

  if (!result) {
    return Response.json({ success: false, error: "not a command" }, { status: 400 });
  }
  return Response.json({ success: result.ok, result });
}

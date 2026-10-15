import { guardMutation } from "@/lib/api-guard";
import { executeCommandFromText, type CommandResult } from "@/lib/harness/command-router";
import { buildAgentInstruction } from "@/lib/harness/command-agent";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { chatWithAgent } from "@/lib/harness/run-service";

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

  // Agent-turn commands (e.g. `/skill`) run the agent loop: they rewrite the
  // query into a directive and produce a normal answer. `chatWithAgent` applies
  // the same rewrite, so pass the raw text straight through.
  const agentCommand = buildAgentInstruction(text);
  if (agentCommand) {
    try {
      const out = await chatWithAgent(text);
      return Response.json({
        success: out.status === "completed",
        result: {
          ok: out.status === "completed",
          command: agentCommand.command,
          commandId: "skill.author",
          status: out.status,
          output: out.output,
          ...(out.error ? { error: { code: "AGENT_ERROR", message: out.error } } : {}),
          audit: {
            commandId: "skill.author",
            command: agentCommand.command,
            actor: "user",
            operator: isOperatorRequest(request),
            status: out.status,
            handlerTarget: "agent.skill.author",
            at: new Date().toISOString(),
            durationMs: 0,
          },
        },
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return Response.json({ success: false, error: message }, { status: 503 });
    }
  }

  const result: CommandResult | null = await executeCommandFromText(text, {
    operator: isOperatorRequest(request),
  });

  if (!result) {
    return Response.json({ success: false, error: "not a command" }, { status: 400 });
  }
  return Response.json({ success: result.ok, result });
}

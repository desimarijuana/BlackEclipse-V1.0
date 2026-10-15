import { describe, it, expect, vi, beforeEach } from "vitest";

// The direct command route runs the SAME shared router. This test locks the
// front-door contract: validation, unknown-command handling, and honest status.

const executeCommandFromText = vi.fn();
const buildAgentInstruction = vi.fn();
const chatWithAgent = vi.fn();

vi.mock("@/lib/harness/command-router", () => ({
  executeCommandFromText: (...args: unknown[]) => executeCommandFromText(...args),
}));

vi.mock("@/lib/harness/command-agent", () => ({
  buildAgentInstruction: (...args: unknown[]) => buildAgentInstruction(...args),
}));

vi.mock("@/lib/harness/run-service", () => ({
  chatWithAgent: (...args: unknown[]) => chatWithAgent(...args),
}));

vi.mock("@/lib/harness/skills-client", () => ({
  isOperatorRequest: () => false,
}));

vi.mock("@/lib/api-guard", () => ({
  guardMutation: () => null,
}));

import { POST } from "@/app/api/harness/command/route";

function post(body: unknown): Request {
  return new Request("http://localhost:3000/api/harness/command", {
    method: "POST",
    headers: { origin: "http://localhost:3000", "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/harness/command", () => {
  beforeEach(() => {
    executeCommandFromText.mockReset();
    buildAgentInstruction.mockReset();
    chatWithAgent.mockReset();
    // Default: not an agent-turn command.
    buildAgentInstruction.mockReturnValue(null);
  });

  it("rejects an empty body", async () => {
    const res = await POST(post({}));
    expect(res.status).toBe(400);
    expect(executeCommandFromText).not.toHaveBeenCalled();
  });

  it("rejects text that is not a command", async () => {
    executeCommandFromText.mockResolvedValueOnce(null);
    const res = await POST(post({ text: "just chatting" }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/not a command/i);
  });

  it("returns the routed result on success", async () => {
    executeCommandFromText.mockResolvedValueOnce({
      ok: true, command: "skills", commandId: "skills.list", status: "completed",
      output: "ok", audit: { commandId: "skills.list" },
    });
    const res = await POST(post({ text: "/skills" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.success).toBe(true);
    expect(body.result.command).toBe("skills");
  });

  it("reports a non-ok command result honestly", async () => {
    executeCommandFromText.mockResolvedValueOnce({
      ok: false, command: "market", commandId: "markets.market", status: "unavailable",
      output: "not available", error: { code: "COMMAND_UNAVAILABLE", message: "nope" },
      audit: { commandId: "markets.market" },
    });
    const res = await POST(post({ text: "/market" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.success).toBe(false);
    expect(body.result.status).toBe("unavailable");
  });

  it("runs an agent-turn command (/skill) through the chat path", async () => {
    buildAgentInstruction.mockReturnValueOnce({ command: "skill", instruction: "author a skill" });
    chatWithAgent.mockResolvedValueOnce({ status: "completed", output: "Created skill `x`.", runId: "run_1" });
    const res = await POST(post({ text: "/skill x do y" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.success).toBe(true);
    expect(body.result.commandId).toBe("skill.author");
    expect(chatWithAgent).toHaveBeenCalled();
  });
});

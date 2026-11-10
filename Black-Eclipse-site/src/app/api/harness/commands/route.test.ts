import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/harness/command-plugins", () => ({
  loadProjectCommands: vi.fn(async () => ({ commands: [], errors: [] })),
}));

import { loadProjectCommands } from "@/lib/harness/command-plugins";
import type { CommandSpec } from "@/lib/harness/command-registry";
import { GET } from "./route";

const projectSpec: CommandSpec = {
  id: "project.morning-brief",
  name: "morning-brief",
  aliases: ["brief"],
  summary: "Produce my morning market brief.",
  description: "Summarize overnight moves.",
  category: "research",
  tags: ["brief"],
  version: "1.0.0",
  status: "available",
  args: [],
  flags: [],
  handler: { type: "agent", target: "agent.plugin" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "async",
  output: { type: "markdown", summary: "A brief." },
  examples: ["/morning-brief"],
  source: "project",
  agentPrompt: "Produce my morning brief.",
};

function get(headers?: Record<string, string>): Request {
  return new Request("http://localhost/api/harness/commands", { headers });
}

describe("GET /api/harness/commands", () => {
  beforeEach(() => {
    vi.mocked(loadProjectCommands).mockResolvedValue({ commands: [], errors: [] });
  });

  it("returns the builtin catalog plus validated project commands", async () => {
    vi.mocked(loadProjectCommands).mockResolvedValueOnce({ commands: [projectSpec], errors: ["bad pack"] });
    const res = await GET(get());
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.version).toBe(1);
    expect(body.errors).toEqual(["bad pack"]);
    expect(body.commands.find((c: { name: string }) => c.name === "status")).toMatchObject({
      source: "builtin",
      available: true,
    });
    const project = body.commands.find((c: { name: string }) => c.name === "morning-brief");
    expect(project).toMatchObject({ source: "project", available: true });
    expect(project.agentPrompt).toBeUndefined();
  });

  it("returns 304 when the ETag still matches", async () => {
    const first = await GET(get());
    const etag = first.headers.get("etag");
    expect(etag).toBeTruthy();
    const second = await GET(get({ "if-none-match": etag! }));
    expect(second.status).toBe(304);
    expect(second.headers.get("etag")).toBe(etag);
  });
});

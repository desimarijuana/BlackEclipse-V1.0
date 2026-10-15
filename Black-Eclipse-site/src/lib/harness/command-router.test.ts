import { describe, it, expect, vi } from "vitest";

import {
  executeCommand,
  executeCommandFromText,
  isRoutedCommand,
  type CommandDeps,
} from "./command-router";
import { bindArgs, tokenizeArgs } from "./command-parser";
import { resolveCommand } from "./command-registry";
import type { SkillDetail, SkillDraft, SkillExecutionResult, SkillSummary } from "./skills-types";

function summary(id: string, extra: Partial<SkillSummary> = {}): SkillSummary {
  return {
    id,
    name: id,
    version: "1.0.0",
    description: `${id} description`,
    category: "research",
    tags: [],
    status: "enabled",
    riskLevel: "low",
    permissions: [],
    requiredTools: [],
    evaluationStatus: "passed",
    ...extra,
  };
}

function detail(id: string): SkillDetail {
  return {
    id,
    name: id,
    version: "1.0.0",
    description: `${id} description`,
    category: "research",
    tags: [],
    status: "enabled",
    riskLevel: "low",
    permissions: [],
    requiredTools: [],
    evaluationStatus: "passed",
    instructions: "do the thing",
    storedStatus: "enabled",
    inputSchema: { type: "object" },
    outputSchema: null,
    requiredSkills: [],
    limits: { maxSteps: 10, timeoutMs: 30_000, maxToolCalls: 10 },
    author: "tester",
    compatibleRuntime: ">=0.1",
    sourceRunId: null,
    deprecation: null,
    validation: { ok: true, skillId: id, version: "1.0.0", checks: [], errors: [] },
    versions: [],
    executions: [],
    evaluations: [],
    reviews: [],
    events: [],
  };
}

function execution(overrides: Partial<SkillExecutionResult> = {}): SkillExecutionResult {
  return {
    status: "completed",
    skillId: "crypto-onchain-research",
    version: "1.0.0",
    runId: "run_skill_1",
    output: "BTC on-chain activity is elevated.",
    outputValidated: true,
    error: null,
    evidence: [],
    warnings: [],
    missingData: [],
    limitations: [],
    metrics: { toolCalls: 3, modelSteps: 2 },
    ...overrides,
  };
}

function makeDeps(overrides: Partial<CommandDeps["skills"]> = {}): CommandDeps {
  return {
    frontDoor: {
      request: vi.fn(async (path: string) => {
        if (path.startsWith("/api/quote")) {
          return { ok: true, status: 200, data: { quotes: [{ symbol: "AAPL", name: "Apple", price: 100, changePercent: 1.5, currency: "$", freshness: "live", found: true }] } };
        }
        if (path === "/api/backtest/strategies") return { ok: true, status: 200, data: { strategies: [{ id: "s1", name: "Momentum", version: "1" }] } };
        if (path === "/api/backtest/backtest") return { ok: true, status: 200, data: { result: { sharpe: 1.2, totalReturn: 0.3 } } };
        if (path === "/api/research/run") return { ok: true, status: 200, data: { success: true, result: { answer: "Answer text", sources: [{ title: "S", url: "https://e.com" }], status: { state: "completed" }, claims: [] } } };
        if (path === "/api/terminal/execute") return { ok: true, status: 200, data: { stdout: "ok\n", stderr: "", exitCode: 0 } };
        if (path === "/api/code/tasks") return { ok: true, status: 200, data: { task: { id: "task_1", status: "created" } } };
        return { ok: true, status: 200, data: {} };
      }),
    },
    skills: {
      list: vi.fn(async () => [summary("crypto-onchain-research", { category: "research" })]),
      discover: vi.fn(async () => [summary("crypto-onchain-research")]),
      get: vi.fn(async (id: string) => (id === "missing" ? null : detail(id))),
      preflight: vi.fn(async (id: string) => ({ ok: true, reasons: [], validation: {}, dependencyGraph: {}, skillId: id })),
      validateInput: vi.fn(async () => ({ valid: true, issues: [] })),
      execute: vi.fn(async () => execution()),
      evaluate: vi.fn(async () => ({ status: "passed", dimensions: [{ name: "manifest_validation", status: "passed", detail: "ok" }] })),
      enable: vi.fn(async () => ({ ok: true })),
      disable: vi.fn(async () => ({ ok: true })),
      learnFromSource: vi.fn(async () => ({
        ok: true,
        draft: { id: "new-skill", version: "1.0.0", status: "draft", evaluationStatus: "not_evaluated" } as unknown as SkillDraft,
      })),
      learnFromRun: vi.fn(async () => ({ ok: true, created: [{ id: "cand_1", title: "candidate" }] })),
      ...overrides,
    },
    tasks: {
      listPlans: vi.fn(async () => ({ plans: [{ id: "plan_1", name: "P", status: "RUNNING", progress: 0.5 }] })),
      listTasks: vi.fn(async () => ({ tasks: [{ id: "task_1", title: "T", status: "TODO", priority: "NORMAL" }] })),
    },
    workflows: { list: vi.fn(async () => [{ id: "wf_1", version: "1", steps: [1, 2] }]) },
    runtime: {
      health: vi.fn(async () => ({ ok: true, tools: ["a", "b"], providers: ["openai"] })),
      models: vi.fn(async () => [{ id: "openai", label: "OpenAI", models: ["gpt-4"], available: true }]),
      agents: vi.fn(async () => ({ agents: [{ id: "eclipse-agent", name: "Eclipse" }], defaultAgentId: "eclipse-agent" })),
    },
    market: {
      providers: vi.fn(async () => ({
        status: "ok",
        providerCount: 1,
        implementedCount: 1,
        providers: [{ id: "yahoo", label: "Yahoo", configured: true, implemented: true }],
        available: true,
      })),
      health: vi.fn(async () => ({ available: true, cache: { entries: 3, hits: 5, misses: 1 } })),
    },
    portfolio: {
      list: vi.fn(async () => [{
        id: "pf_1", name: "Main", baseCurrency: "USD", ownerId: null, description: null,
        costBasisMethod: "FIFO", status: "active", createdAt: "2026-01-01", updatedAt: "2026-01-01",
      }]),
    },
    memory: {
      overview: vi.fn(async () => ({ total: 2, active: 2 })),
      list: vi.fn(async () => [{ id: "mem_1", memoryType: "fact", scope: "global", status: "active", subject: "s" }]),
    },
    mcp: {
      list: vi.fn(async () => ({ servers: [{ id: "srv_1", name: "Filesystem", transport: "stdio", enabled: true, untrusted: false }] })),
    },
    usage: {
      summary: vi.fn(async () => ({
        windowDays: 30, since: "2026-01-01",
        totals: { runs: 5, promptTokens: 10, completionTokens: 20, totalTokens: 30, modelSteps: 4, toolCalls: 3, toolErrors: 0, completed: 4, failed: 1, cancelled: 0, runsWithUsage: 5 },
        byModel: [], byDay: [], recent: [],
      })),
    },
    now: () => 1_000,
  } as unknown as CommandDeps;
}

const ctx = { operator: false } as const;
const opCtx = { operator: true } as const;

describe("executeCommandFromText", () => {
  it("returns null for ordinary prose", async () => {
    expect(await executeCommandFromText("hello world", ctx, makeDeps())).toBeNull();
  });

  it("reports an unknown command", async () => {
    const res = (await executeCommandFromText("/frobnicate now", ctx, makeDeps()))!;
    expect(res.status).toBe("unknown");
    expect(res.ok).toBe(false);
    expect(res.output).toContain("No command");
  });

  it("reports invalid/missing arguments with a usage hint", async () => {
    const res = (await executeCommandFromText("/skills show", ctx, makeDeps()))!;
    expect(res.status).toBe("invalid");
    expect(res.output).toContain("Usage:");
    expect(res.output).toContain("skill-id");
  });

  it("reports an unavailable command explicitly, never as functional", async () => {
    const spec = {
      ...resolveCommand("help")!,
      id: "x.fake",
      name: "fake",
      aliases: [],
      status: "unavailable" as const,
      handler: { type: "unsupported" as const, target: "x.fake" },
      unavailabilityReason: "not wired yet",
    };
    const res = await executeCommand(
      { spec, name: "fake", rest: "", unknown: false, raw: "/fake" },
      bindArgs(spec, tokenizeArgs("")),
      ctx,
      makeDeps(),
    );
    expect(res.status).toBe("unavailable");
    expect(res.output).toContain("not available");
  });

  it("gets quotes via the front door", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/quote AAPL", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("AAPL");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      expect.stringContaining("/api/quote?symbols=AAPL"),
      expect.anything(),
    );
  });

  it("runs research and renders the answer with sources", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText('/research "NVIDIA position"', ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("Answer text");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      "/api/research/run",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("lists strategies when /backtest has no id, and backtests with one", async () => {
    const deps = makeDeps();
    const list = (await executeCommandFromText("/backtest", ctx, deps))!;
    expect(list.status).toBe("completed");
    expect(list.output).toContain("Momentum");
    const run = (await executeCommandFromText("/backtest s1", ctx, deps))!;
    expect(run.status).toBe("completed");
    expect(run.output).toContain("sharpe");
  });

  it("runs a terminal command and shows its output", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/terminal ls -la", opCtx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("ok");
  });

  it("denies /terminal for a non-operator", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/terminal ls", ctx, deps))!;
    expect(res.status).toBe("denied");
    expect(deps.frontDoor.request).not.toHaveBeenCalled();
  });

  it("creates a code task", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/code add a loading state", opCtx, deps))!;
    expect(res.status).toBe("completed");
    expect(deps.frontDoor.request).toHaveBeenCalledWith("/api/code/tasks", expect.objectContaining({ method: "POST" }));
  });

  it("executes /help from the registry only", async () => {
    const res = (await executeCommandFromText("/help", ctx, makeDeps()))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("eclipse-response");
    expect(res.output).toContain("skills");
  });

  it("executes /status from real runtime health", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/status", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(deps.runtime.health).toHaveBeenCalled();
  });

  it("lists skills and searches skills", async () => {
    const deps = makeDeps();
    const list = (await executeCommandFromText("/skills", ctx, deps))!;
    expect(list.status).toBe("completed");
    expect(list.output).toContain("crypto-onchain-research");

    const search = (await executeCommandFromText("/skills search crypto", ctx, deps))!;
    expect(search.status).toBe("completed");
    expect(deps.skills.discover).toHaveBeenCalledWith({ query: "crypto" });
  });

  it("shows a skill and reports a missing one", async () => {
    const show = (await executeCommandFromText("/skills show crypto-onchain-research", ctx, makeDeps()))!;
    expect(show.status).toBe("completed");
    const missing = (await executeCommandFromText("/skills show missing", ctx, makeDeps()))!;
    expect(missing.status).toBe("failed");
    expect(missing.error?.code).toBe("SKILL_NOT_FOUND");
  });

  it("runs a skill via /skills run", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/skills run crypto-onchain-research", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.meta?.skillId).toBe("crypto-onchain-research");
    expect(deps.skills.execute).toHaveBeenCalledWith(
      expect.objectContaining({ skillId: "crypto-onchain-research" }),
      { operator: false },
    );
  });

  it("reports a failed skill execution honestly", async () => {
    const deps = makeDeps({
      execute: vi.fn(async () => execution({ status: "failed", output: null, error: { code: "TOOL_ERROR", message: "boom" } })),
    });
    const res = (await executeCommandFromText("/skills run foo", ctx, deps))!;
    expect(res.status).toBe("failed");
    expect(res.error?.code).toBe("TOOL_ERROR");
  });

  it("denies an operator command for a non-operator and allows it for an operator", async () => {
    const deniedDeps = makeDeps();
    const denied = (await executeCommandFromText("/skill-enable crypto-onchain-research", ctx, deniedDeps))!;
    expect(denied.status).toBe("denied");
    expect(deniedDeps.skills.enable).not.toHaveBeenCalled();

    const okDeps = makeDeps();
    const ok = (await executeCommandFromText("/skill-enable crypto-onchain-research", opCtx, okDeps))!;
    expect(ok.status).toBe("completed");
    expect(okDeps.skills.enable).toHaveBeenCalledWith("crypto-onchain-research", true, undefined);
  });

  it("requires a source for /skill-create rather than guessing", async () => {
    const res = (await executeCommandFromText("/skill-create my-skill", opCtx, makeDeps()))!;
    expect(res.status).toBe("invalid");
  });

  it("creates a draft from a task", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/skill-create my-skill --from-task task_1", opCtx, deps))!;
    expect(res.status).toBe("completed");
    expect(deps.skills.learnFromRun).toHaveBeenCalledWith("task_1", true, "my-skill");
  });

  it("runs a skill evaluation", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/skill-test crypto-onchain-research", opCtx, deps))!;
    expect(res.status).toBe("completed");
    expect(deps.skills.evaluate).toHaveBeenCalledWith("crypto-onchain-research", undefined, false);
  });

  it("produces a structured audit event", async () => {
    const res = (await executeCommandFromText("/skills", ctx, makeDeps()))!;
    expect(res.audit.commandId).toBe("skills.list");
    expect(res.audit.status).toBe("completed");
    expect(res.audit.handlerTarget).toBe("skills.catalog");
  });
  it("creates a draft from a workflow", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/skill-create --from-workflow crypto-research", opCtx, deps))!;
    expect(res.status).toBe("completed");
    expect(deps.skills.learnFromSource).toHaveBeenCalledWith(
      expect.objectContaining({ sourceKind: "repeated_workflow", sourceRunId: "crypto-research" }),
    );
  });

  it("lists tools, usage, market, portfolios, memory, and MCP servers", async () => {
    const deps = makeDeps();
    expect((await executeCommandFromText("/tools", ctx, deps))!.status).toBe("completed");
    expect(deps.runtime.health).toHaveBeenCalled();
    expect((await executeCommandFromText("/usage", ctx, deps))!.status).toBe("completed");
    expect(deps.usage.summary).toHaveBeenCalledWith(30);
    expect((await executeCommandFromText("/market", ctx, deps))!.status).toBe("completed");
    expect((await executeCommandFromText("/portfolio", ctx, deps))!.status).toBe("completed");
    expect((await executeCommandFromText("/memory", ctx, deps))!.status).toBe("completed");
    expect((await executeCommandFromText("/mcp", ctx, deps))!.status).toBe("completed");
  });

  it("reports a runtime-down /status honestly instead of failing", async () => {
    const deps = makeDeps();
    (deps.runtime.health as unknown as { mockResolvedValueOnce: (v: unknown) => void })
      .mockResolvedValueOnce({ ok: false });
    const res = (await executeCommandFromText("/status", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("Runtime unavailable");
  });
});

describe("isRoutedCommand", () => {
  it("routes handler commands but not the chat profile or agent commands", () => {
    expect(isRoutedCommand(resolveCommand("skills")!)).toBe(true);
    expect(isRoutedCommand(resolveCommand("eclipsesdk")!)).toBe(false);
    expect(isRoutedCommand(resolveCommand("skill")!)).toBe(false);
    expect(isRoutedCommand(null)).toBe(false);
  });
});

import { describe, it, expect, vi } from "vitest";

import {
  executeCommand,
  executeCommandFromText,
  isRoutedCommand,
  type CommandAuditEvent,
  type CommandDeps,
} from "./command-router";
import { bindArgs, tokenizeArgs } from "./command-parser";
import { resolveCommand } from "./command-registry";
import { handlers } from "./command-handlers";
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
        if (path === "/api/terminal/execute") {
          return {
            ok: true,
            status: 200,
            data: {
              success: true,
              result: {
                status: "completed",
                stdout: "ok\n",
                stderr: "",
                exitCode: 0,
                cwd: "/workspace",
                runtime: "local",
                durationMs: 12,
              },
            },
          };
        }
        if (path === "/api/code/tasks") return { ok: true, status: 200, data: { task: { id: "task_1", status: "created" } } };
        if (path === "/api/alerts") {
          return { ok: true, status: 200, data: { alerts: [{ name: "AAPL move", symbols: ["AAPL"], status: "active", lastFiredAt: null, active: true }], running: 1 } };
        }
        if (path.startsWith("/api/news")) {
          return { ok: true, status: 200, data: { news: [{ headline: "Chip demand rises", source: "Wire", ticker: "NVDA", sentiment: "bullish", timestamp: "2026-11-09T12:00:00Z" }], source: "jdds" } };
        }
        if (path.startsWith("/api/theses")) {
          return { ok: true, status: 200, data: { theses: [{ symbol: "AAPL", title: "Services margin", status: "active", reviewDate: "2026-12-01", updatedAt: "2026-11-01T00:00:00Z" }] } };
        }
        if (path === "/api/journal/trades") {
          return { ok: true, status: 200, data: { trades: [
            { symbol: "AAPL", direction: "long", entry: 100, exit: 110, quantity: 2, pnl: 20, entryTime: "2026-11-01T00:00:00Z" },
            { symbol: "BTC", direction: "long", entry: 60000, exit: null, quantity: 1, pnl: null, entryTime: "2026-11-02T00:00:00Z" },
          ] } };
        }
        if (path === "/api/jobs") {
          return { ok: true, status: 200, data: { jobs: [{ name: "Morning brief", kind: "objective", enabled: true, cron: "0 8 * * *", lastRunAt: "2026-11-09T08:00:00Z", consecutiveFailures: 0 }] } };
        }
        if (path.startsWith("/api/artifacts")) {
          return { ok: true, status: 200, data: { artifacts: [{ name: "Report", category: "report", mimeType: "text/markdown", sizeBytes: 2048, updatedAt: "2026-11-09T10:00:00Z" }], total: 1, hasMore: false } };
        }
        if (path.startsWith("/api/sessions")) {
          return { ok: true, status: 200, data: { sessions: [{ id: "sess_1", title: "Chip research", status: "active", updatedAt: "2026-11-09T10:00:00Z" }], total: 1, hasMore: false } };
        }
        if (path.startsWith("/api/git")) {
          if (path.includes("action=diff")) return { ok: true, status: 200, data: { diff: "diff --git a/x b/x\n+hello" } };
          if (path.includes("action=log")) return { ok: true, status: 200, data: { commits: [{ shortHash: "abc1234", subject: "Add thing", author: "me", date: "2026-11-09T00:00:00Z" }] } };
          return { ok: true, status: 200, data: { status: { branch: "main", upstream: "origin/main", ahead: 1, behind: 0, clean: false, staged: [{ path: "a.ts", status: "M" }], unstaged: [], untracked: ["b.ts"], summary: { staged: 1, unstaged: 0, untracked: 1 } } } };
        }
        if (path === "/api/harness/runs") {
          return { ok: true, status: 200, data: { runs: [
            { id: "run_1", agentId: "eclipse-agent", status: "running", model: "gpt-5", createdAt: "2026-11-09T10:00:00Z" },
            { id: "run_2", agentId: "eclipse-agent", status: "completed", model: "gpt-5", createdAt: "2026-11-09T09:00:00Z" },
          ] } };
        }
        if (path.startsWith("/api/harness/runs/") && path.endsWith("/cancel")) {
          return { ok: true, status: 200, data: { success: true, cancelled: true, message: "Cancellation requested" } };
        }
        if (path.startsWith("/api/eclipse-memory/memories")) {
          return { ok: true, status: 200, data: { memories: [{ content: "Prefers concentration checks", memoryType: "semantic", scope: "general", status: "active" }], total: 1 } };
        }
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
      compact: vi.fn(async (history: Array<{ role: string; content: string }>, keepTurns: number) => ({
        ok: true,
        block: `<compacted-conversation>\nSUMMARY\nTurns compacted: ${Math.max(0, history.length - keepTurns)}\n</compacted-conversation>`,
        droppedTurns: Math.max(0, history.length - keepTurns),
        keptTurns: keepTurns,
        chars: 100,
      })),
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
    audit: {
      append: vi.fn(async () => {}),
      read: vi.fn(async () => []),
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

  it("requires a single-use confirmation before running a high-risk command", async () => {
    const deps = makeDeps();
    const first = (await executeCommandFromText("/terminal --shell cmd --cwd src dir /s", opCtx, deps))!;
    expect(first.status).toBe("pending");
    expect(first.output).toContain("Confirmation required");
    expect(deps.frontDoor.request).not.toHaveBeenCalled();

    const token = /--confirm ([0-9a-f-]{36})/.exec(first.output)?.[1];
    expect(token).toBeTruthy();

    const confirmed = (await executeCommandFromText(
      `/terminal --shell cmd --cwd src dir /s --confirm ${token}`,
      opCtx,
      deps,
    ))!;
    expect(confirmed.status).toBe("completed");
    expect(confirmed.output).toContain("ok");
    expect(confirmed.output).toContain("cmd");
    expect(confirmed.output).toContain("Exit code");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      "/api/terminal/execute",
      expect.objectContaining({ body: { command: "dir /s", shell: "cmd", cwd: "src" } }),
    );
  });

  it("rejects a replayed confirmation token", async () => {
    const deps = makeDeps();
    const first = (await executeCommandFromText("/terminal echo hi", opCtx, deps))!;
    const token = /--confirm ([0-9a-f-]{36})/.exec(first.output)?.[1];
    const ok = (await executeCommandFromText(`/terminal echo hi --confirm ${token}`, opCtx, deps))!;
    expect(ok.status).toBe("completed");
    const replay = (await executeCommandFromText(`/terminal echo hi --confirm ${token}`, opCtx, deps))!;
    expect(replay.status).toBe("pending");
  });

  it("denies /terminal for a non-operator", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/terminal ls", ctx, deps))!;
    expect(res.status).toBe("denied");
    expect(deps.frontDoor.request).not.toHaveBeenCalled();
  });

  it("creates a code task after confirmation", async () => {
    const deps = makeDeps();
    const first = (await executeCommandFromText("/code add a loading state", opCtx, deps))!;
    expect(first.status).toBe("pending");
    const token = /--confirm ([0-9a-f-]{36})/.exec(first.output)?.[1];
    const res = (await executeCommandFromText(`/code add a loading state --confirm ${token}`, opCtx, deps))!;
    expect(res.status).toBe("completed");
    expect(deps.frontDoor.request).toHaveBeenCalledWith("/api/code/tasks", expect.objectContaining({ method: "POST" }));
  });

  it("lists alert watches", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/alerts", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("AAPL move");
    expect(res.output).toContain("monitor");
  });

  it("queries news by ticker", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/news AAPL", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("Chip demand rises");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      expect.stringContaining("ticker=AAPL"),
      expect.anything(),
    );
  });

  it("lists theses filtered by symbol", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/theses AAPL", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("Services margin");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      "/api/theses?symbol=AAPL",
      expect.anything(),
    );
  });

  it("filters journal trades to open positions", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/journal open", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("BTC");
    expect(res.output).not.toContain("AAPL");
  });

  it("lists jobs, artifacts and sessions", async () => {
    const deps = makeDeps();
    const jobs = (await executeCommandFromText("/jobs", ctx, deps))!;
    expect(jobs.output).toContain("Morning brief");
    const artifacts = (await executeCommandFromText("/artifacts", ctx, deps))!;
    expect(artifacts.output).toContain("Report");
    const sessions = (await executeCommandFromText("/sessions", ctx, deps))!;
    expect(sessions.output).toContain("Chip research");
  });

  it("reads git status and diff", async () => {
    const deps = makeDeps();
    const status = (await executeCommandFromText("/git", ctx, deps))!;
    expect(status.output).toContain("main");
    expect(status.output).toContain("a.ts");
    const diff = (await executeCommandFromText("/git diff", ctx, deps))!;
    expect(diff.output).toContain("+hello");
  });

  it("lists active runs and cancels one", async () => {
    const deps = makeDeps();
    const list = (await executeCommandFromText("/stop", opCtx, deps))!;
    expect(list.output).toContain("run_1");
    expect(list.output).not.toContain("run_2");
    const cancelled = (await executeCommandFromText("/stop run_1", opCtx, deps))!;
    expect(cancelled.output).toContain("Cancellation requested");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      "/api/harness/runs/run_1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("returns a typed Canvas UI intent from /canvas", async () => {
    const res = (await executeCommandFromText("/canvas", ctx, makeDeps()))!;
    expect(res.status).toBe("completed");
    expect(res.ui).toEqual({ type: "openCanvas" });
  });

  it("returns a typed navigation intent from /open and rejects an unknown tab", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/open alerts", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.ui).toEqual({ type: "navigate", tab: "alerts" });
    const bad = (await executeCommandFromText("/open nowhere", ctx, deps))!;
    expect(bad.status).toBe("invalid");
  });

  it("searches memory with /memory <query>", async () => {
    const deps = makeDeps();
    const res = (await executeCommandFromText("/memory concentration", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("Prefers concentration checks");
    expect(deps.frontDoor.request).toHaveBeenCalledWith(
      expect.stringContaining("/api/eclipse-memory/memories?q=concentration"),
      expect.anything(),
    );
  });

  it("executes /help from the registry only", async () => {
    const res = (await executeCommandFromText("/help", ctx, makeDeps()))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("eclipse-response");
    expect(res.output).toContain("skills");
    expect(res.output).toContain("alerts");
    expect(res.output).toContain("theses");
  });

  it("describes one command with /help <command>", async () => {
    const res = (await executeCommandFromText("/help quote", ctx, makeDeps()))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("markets.quote");
    expect(res.output).toContain("symbols");
    expect(res.output).toContain("/quote AAPL");
  });

  it("suggests the closest command for an unknown help topic", async () => {
    const res = (await executeCommandFromText("/help quotte", ctx, makeDeps()))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("Did you mean");
    expect(res.output).toContain("/quote");
  });

  it("appends a redacted audit event", async () => {
    const deps = makeDeps();
    await executeCommandFromText("/status", ctx, deps);
    expect(deps.audit.append).toHaveBeenCalledWith(
      expect.objectContaining({ command: "status", status: "completed", risk: "none" }),
    );
  });

  it("shows the durable command audit with /history", async () => {
    const deps = makeDeps();
    const events: CommandAuditEvent[] = [{
      commandId: "runtime.terminal",
      command: "terminal",
      actor: "user",
      operator: true,
      status: "completed",
      handlerTarget: "runtime.terminal",
      at: "2026-11-09T10:00:00.000Z",
      durationMs: 12,
      risk: "high",
      approval: "operator",
    }];
    vi.mocked(deps.audit.read).mockResolvedValueOnce(events);
    const res = (await executeCommandFromText("/history 10", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("/terminal");
    expect(deps.audit.read).toHaveBeenCalledWith(10);
  });

  it("summarizes command usage with /usage --commands", async () => {
    const deps = makeDeps();
    const events: CommandAuditEvent[] = [
      { commandId: "runtime.status", command: "status", actor: "user", operator: false, status: "completed", handlerTarget: "runtime.status", at: "2026-11-09T10:00:00.000Z", durationMs: 5, risk: "none", approval: "none" },
      { commandId: "runtime.terminal", command: "terminal", actor: "user", operator: true, status: "failed", handlerTarget: "runtime.terminal", at: "2026-11-09T10:01:00.000Z", durationMs: 40, risk: "high", approval: "operator" },
    ];
    vi.mocked(deps.audit.read).mockResolvedValueOnce(events);
    const res = (await executeCommandFromText("/usage --commands", ctx, deps))!;
    expect(res.status).toBe("completed");
    expect(res.output).toContain("/terminal");
    expect(res.output).toContain("Command usage");
    expect(deps.audit.read).toHaveBeenCalledWith(500);
  });

  it("rate limits a command and recovers after the window", async () => {
    handlers["test.rate"] = async () => ({ status: "completed" as const });
    try {
      const spec = {
        ...resolveCommand("status")!,
        id: "test.rate",
        name: "rate",
        rateLimit: { limit: 2, windowMs: 60_000 },
        handler: { type: "native" as const, target: "test.rate" },
      };
      const args = bindArgs(spec, tokenizeArgs(""));
      const deps = makeDeps();
      const invoke = () =>
        executeCommand(
          { spec, name: "rate", rest: "", unknown: false, raw: "/rate" },
          args,
          ctx,
          deps,
        );
      expect((await invoke()).status).toBe("completed");
      expect((await invoke()).status).toBe("completed");
      const limited = await invoke();
      expect(limited.status).toBe("denied");
      expect(limited.error?.code).toBe("RATE_LIMITED");

      (deps as unknown as { now: () => number }).now = () => 62_000;
      expect((await invoke()).status).toBe("completed");
    } finally {
      delete handlers["test.rate"];
    }
  });

  it("enforces a command's declared timeout", async () => {
    handlers["test.slow"] = async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
      return { status: "completed" as const };
    };
    try {
      const spec = {
        ...resolveCommand("status")!,
        id: "test.slow",
        name: "slow",
        timeoutMs: 5,
        handler: { type: "native" as const, target: "test.slow" },
      };
      const res = await executeCommand(
        { spec, name: "slow", rest: "", unknown: false, raw: "/slow" },
        bindArgs(spec, tokenizeArgs("")),
        ctx,
        makeDeps(),
      );
      expect(res.status).toBe("failed");
      expect(res.error?.code).toBe("COMMAND_TIMEOUT");
    } finally {
      delete handlers["test.slow"];
    }
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

  it("compacts the conversation and returns the real block", async () => {
    const deps = makeDeps();
    const history = [
      { role: "user" as const, content: "q1" },
      { role: "assistant" as const, content: "a1" },
      { role: "user" as const, content: "q2" },
      { role: "assistant" as const, content: "a2" },
    ];
    const res = (await executeCommandFromText("/compact --keep 2", { operator: false, history }, deps))!;
    expect(res.status).toBe("completed");
    expect(res.compaction).toBeDefined();
    expect(res.compaction?.droppedTurns).toBe(2);
    expect(res.compaction?.keptTurns).toBe(2);
    expect(deps.runtime.compact).toHaveBeenCalledWith(history, 2);
    expect(res.output).toContain("Conversation compacted");
  });

  it("refuses /compact honestly when there is no history", async () => {
    const res = (await executeCommandFromText("/compact", ctx, makeDeps()))!;
    expect(res.status).toBe("invalid");
    expect(res.error?.code).toBe("NO_HISTORY");
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

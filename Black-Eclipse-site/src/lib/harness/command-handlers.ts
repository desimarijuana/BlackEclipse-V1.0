// ─── Command handlers ────────────────────────────────────────────────────────
// The dispatch table and per-command renderers. Handlers call EXISTING systems
// (clients, same-origin front-door APIs); they own no agent loop or storage.
// Types are imported from ./command-router (type-only, erased — no runtime cycle).

import {
  allCommands,
  commandArgHint,
  isCommandAvailable,
  type CommandCategory,
  type CommandSpec,
} from "./command-registry";
import type { BoundArgs } from "./command-parser";
import { callout, dataTable, heading, keyValue, markdown } from "./command-render";
import type { ResponseBlock } from "@/lib/response/contract";
import type { LearnDraftResult, SkillDetail, SkillExecutionResult, SkillSummary } from "./skills-types";
import type { CommandContext, CommandDeps, CommandResult, CommandRunStatus } from "./command-router";

export interface HandlerOutput {
  status: CommandRunStatus;
  blocks?: ResponseBlock[];
  markdownText?: string;
  error?: { code: string; message: string };
  meta?: CommandResult["meta"];
}

type Handler = (
  ctx: CommandContext,
  spec: CommandSpec,
  args: BoundArgs,
  deps: CommandDeps,
) => Promise<HandlerOutput>;

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function fail(code: string, message: string): HandlerOutput {
  return { status: "failed", error: { code, message } };
}

function invalid(code: string, message: string): HandlerOutput {
  return { status: "invalid", error: { code, message } };
}

// ── Handlers ─────────────────────────────────────────────────────────────────

export const handlers: Record<string, Handler> = {
  "native.canvas": async (_ctx, _spec, args, _deps) => {
    const mode = str(args.positionals.mode) || "document";
    const allowed: Record<string, string> = {
      document: "document",
      code: "code",
      report: "visual",
      visual: "visual",
    };
    const kind = allowed[mode];
    if (!kind) {
      return invalid("CANVAS_MODE", `unknown canvas mode '${mode}'; expected document, code, report or visual`);
    }
    const href = `/?tab=canvas${kind === "document" ? "" : `&kind=${kind}`}`;
    const blocks: ResponseBlock[] = [
      heading("Eclipse Canvas", 2),
      markdown(
        "Canvas is a persistent, editable workspace for documents, code and visual reports. " +
          "Create an artifact, edit it directly, then ask Eclipse for reviewable, revision-guarded changes.",
      ),
      markdown(`[Open Canvas →](${href})`),
    ];
    return { status: "completed", blocks };
  },

  "native.help": async (_ctx, _spec, _args, _deps) => {
    const blocks: ResponseBlock[] = [
      heading("Eclipse commands", 2),
      markdown("Type `/` to autocomplete. Commands with a handler run immediately; unavailable commands return an explicit error."),
    ];
    const byCategory = new Map<CommandCategory, CommandSpec[]>();
    for (const spec of allCommands()) {
      const list = byCategory.get(spec.category) ?? [];
      list.push(spec);
      byCategory.set(spec.category, list);
    }
    for (const [category, specs] of [...byCategory.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const rows = specs
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((s) => ({
          command: `/${s.name}`,
          args: commandArgHint(s),
          status: isCommandAvailable(s) ? "available" : s.status,
          summary: s.summary,
        }));
      blocks.push(
        dataTable(category, [
          { key: "command", label: "Command" },
          { key: "args", label: "Arguments" },
          { key: "status", label: "Status" },
          { key: "summary", label: "Summary" },
        ], rows),
      );
    }
    return { status: "completed", blocks };
  },

  "runtime.status": async (_ctx, _spec, _args, deps) => {
    const health = await deps.runtime.health();
    const blocks: ResponseBlock[] = [heading("Runtime status", 2)];
    if (!health.ok) {
      blocks.push(callout("warning", "Runtime unavailable", "The Python agent runtime is not reachable. Agent runs and skill execution cannot proceed."));
      return { status: "completed", blocks };
    }
    blocks.push(keyValue("Health", [
      { label: "Runtime", value: "ok" },
      { label: "Tools", value: health.tools?.length ?? 0 },
      { label: "Providers", value: health.providers?.length ?? 0 },
    ]));
    if (health.providers?.length) {
      blocks.push(markdown(`Providers: ${health.providers.join(", ")}`));
    }
    return { status: "completed", blocks };
  },

  "native.tasks.list": async (_ctx, _spec, args, deps) => {
    const planId = str(args.positionals.planId) || undefined;
    const status = typeof args.flags.status === "string" ? args.flags.status : undefined;
    const { plans } = await deps.tasks.listPlans();
    const { tasks } = await deps.tasks.listTasks({ planId, status });
    const blocks: ResponseBlock[] = [heading("Tasks & plans", 2)];
    if (!plans.length && !tasks.length) {
      blocks.push(markdown("No plans or tasks are recorded."));
      return { status: "completed", blocks };
    }
    if (plans.length) {
      blocks.push(dataTable("Plans", [
        { key: "id", label: "Plan" },
        { key: "name", label: "Name" },
        { key: "status", label: "Status" },
        { key: "progress", label: "Progress" },
      ], plans.map((p) => ({
        id: String(p.id ?? ""),
        name: String(p.name ?? ""),
        status: String(p.status ?? ""),
        progress: typeof p.progress === "number" ? `${Math.round(p.progress * 100)}%` : String(p.progress ?? ""),
      }))));
    }
    if (tasks.length) {
      blocks.push(dataTable("Tasks", [
        { key: "id", label: "Task" },
        { key: "title", label: "Title" },
        { key: "status", label: "Status" },
        { key: "priority", label: "Priority" },
      ], tasks.map((t) => ({
        id: String(t.id ?? ""),
        title: String(t.title ?? ""),
        status: String(t.status ?? ""),
        priority: String(t.priority ?? ""),
      }))));
    }
    return { status: "completed", blocks };
  },

  "native.workflows.list": async (_ctx, _spec, _args, deps) => {
    const workflows = await deps.workflows.list();
    const blocks: ResponseBlock[] = [heading("Workflows", 2)];
    if (!workflows.length) {
      blocks.push(markdown("No workflows are saved. (The workflow engine may be disabled — set `HARNESS_WORKFLOWS_ENABLED=1`.)"));
      return { status: "completed", blocks };
    }
    blocks.push(dataTable("Saved workflows", [
      { key: "id", label: "Workflow" },
      { key: "version", label: "Version" },
      { key: "steps", label: "Steps" },
    ], workflows.map((w) => ({
      id: String(w.id ?? ""),
      version: String(w.version ?? ""),
      steps: Array.isArray(w.steps) ? w.steps.length : String(w.steps ?? ""),
    }))));
    return { status: "completed", blocks };
  },

  "runtime.models": async (_ctx, _spec, _args, deps) => {
    const providers = await deps.runtime.models();
    const blocks: ResponseBlock[] = [heading("Model providers", 2)];
    if (!providers.length) {
      blocks.push(callout("warning", "No providers", "The runtime reported no configured model providers. Add a key in Settings › AI."));
      return { status: "completed", blocks };
    }
    blocks.push(dataTable("Providers", [
      { key: "id", label: "Provider" },
      { key: "label", label: "Label" },
      { key: "models", label: "Models" },
      { key: "available", label: "Key set" },
    ], providers.map((p) => ({
      id: String(p.id ?? ""),
      label: String(p.label ?? p.name ?? ""),
      models: Array.isArray(p.models) ? p.models.length : "",
      available: p.available === true ? "yes" : p.keyless === true ? "keyless" : "no",
    }))));
    return { status: "completed", blocks };
  },

  "runtime.agents": async (_ctx, _spec, _args, deps) => {
    const { agents, defaultAgentId } = await deps.runtime.agents();
    const blocks: ResponseBlock[] = [heading("Agents", 2)];
    if (!agents.length) {
      blocks.push(markdown("The runtime reported no agents."));
      return { status: "completed", blocks };
    }
    blocks.push(dataTable("Agent presets", [
      { key: "id", label: "Agent" },
      { key: "name", label: "Name" },
      { key: "default", label: "Default" },
    ], agents.map((a) => ({
      id: String(a.id ?? ""),
      name: String(a.name ?? ""),
      default: String(a.id ?? "") === defaultAgentId ? "yes" : "",
    }))));
    return { status: "completed", blocks };
  },

  "runtime.tools": async (_ctx, _spec, _args, deps) => {
    const health = await deps.runtime.health();
    const blocks: ResponseBlock[] = [heading("Tools", 2)];
    if (!health.ok) {
      blocks.push(callout("warning", "Runtime unavailable", "The Python agent runtime is not reachable, so the tool catalog cannot be read."));
      return { status: "completed", blocks };
    }
    const tools = health.tools ?? [];
    blocks.push(markdown(`${tools.length} tool(s) are registered on the runtime's single tool registry.`));
    if (tools.length) {
      blocks.push(dataTable("Registered tools", [{ key: "tool", label: "Tool" }], tools.map((t) => ({ tool: t }))));
    }
    return { status: "completed", blocks };
  },

  "admin.usage": async (_ctx, _spec, _args, deps) => {
    const summary = await deps.usage.summary(30);
    const totals = summary.totals;
    const blocks: ResponseBlock[] = [
      heading("Usage (last 30 days)", 2),
      keyValue("Totals", [
        { label: "Runs", value: totals?.runs ?? 0 },
        { label: "Completed", value: totals?.completed ?? 0 },
        { label: "Failed", value: totals?.failed ?? 0 },
        { label: "Prompt tokens", value: totals?.promptTokens ?? 0 },
        { label: "Completion tokens", value: totals?.completionTokens ?? 0 },
        { label: "Total tokens", value: totals?.totalTokens ?? 0 },
        { label: "Tool calls", value: totals?.toolCalls ?? 0 },
        { label: "Tool errors", value: totals?.toolErrors ?? 0 },
      ]),
    ];
    if (Array.isArray(summary.byModel) && summary.byModel.length) {
      blocks.push(dataTable("By model", [
        { key: "model", label: "Model" },
        { key: "runs", label: "Runs" },
        { key: "tokens", label: "Tokens" },
      ], summary.byModel.map((m) => ({
        model: String((m as { model?: unknown }).model ?? ""),
        runs: (m as { runs?: unknown }).runs ?? 0,
        tokens: (m as { totalTokens?: unknown }).totalTokens ?? 0,
      }))));
    }
    blocks.push(callout("note", "Estimated", "Token usage is reported from run records; no billed-cost figure is invented here."));
    return { status: "completed", blocks };
  },

  "markets.market": async (_ctx, _spec, _args, deps) => {
    const [providers, health] = await Promise.all([deps.market.providers(), deps.market.health()]);
    const rows = providers.providers ?? [];
    const blocks: ResponseBlock[] = [
      heading("Market data gateway", 2),
      keyValue("Status", [
        { label: "Available", value: health.available ? "yes" : "no" },
        { label: "Providers", value: providers.providerCount ?? rows.length },
        { label: "Implemented", value: providers.implementedCount ?? rows.filter((r) => r.implemented).length },
      ]),
    ];
    if (health.cache) {
      blocks.push(keyValue("Cache", [
        { label: "Entries", value: health.cache.entries },
        { label: "Hits", value: health.cache.hits },
        { label: "Misses", value: health.cache.misses },
      ]));
    }
    if (rows.length) {
      blocks.push(dataTable("Providers", [
        { key: "id", label: "Provider" },
        { key: "label", label: "Label" },
        { key: "configured", label: "Configured" },
        { key: "implemented", label: "Implemented" },
      ], rows.map((r) => ({
        id: r.id,
        label: r.label,
        configured: r.configured === true ? "yes" : r.configured === false ? "no" : "unknown",
        implemented: r.implemented ? "yes" : "no",
      }))));
    }
    if (!health.available && health.reason) {
      blocks.push(callout("warning", "Not available", health.reason));
    }
    return { status: "completed", blocks };
  },

  "portfolio.portfolio": async (_ctx, _spec, _args, deps) => {
    const portfolios = await deps.portfolio.list();
    const blocks: ResponseBlock[] = [heading("Portfolios", 2)];
    if (!portfolios.length) {
      blocks.push(markdown("No portfolios are recorded. (Portfolio data is real holdings only — never fabricated.)"));
      return { status: "completed", blocks };
    }
    blocks.push(dataTable("Portfolios", [
      { key: "id", label: "Portfolio" },
      { key: "name", label: "Name" },
      { key: "baseCurrency", label: "Base" },
      { key: "costBasisMethod", label: "Cost basis" },
      { key: "status", label: "Status" },
    ], portfolios.map((p) => ({
      id: p.id,
      name: p.name,
      baseCurrency: p.baseCurrency,
      costBasisMethod: p.costBasisMethod,
      status: p.status,
    }))));
    return { status: "completed", blocks };
  },

  "memory.memory": async (_ctx, _spec, _args, deps) => {
    const [overview, memories] = await Promise.all([
      deps.memory.overview(),
      deps.memory.list({ limit: 25 }),
    ]);
    const blocks: ResponseBlock[] = [heading("Memory", 2)];
    const scalars = Object.entries(overview as unknown as Record<string, unknown>)
      .filter(([, v]) => typeof v === "number" || typeof v === "string")
      .slice(0, 12)
      .map(([k, v]) => ({ label: k, value: typeof v === "number" ? v : String(v) }));
    if (scalars.length) blocks.push(keyValue("Overview", scalars));
    if (memories.length) {
      blocks.push(dataTable("Recent memories", [
        { key: "id", label: "Id" },
        { key: "memoryType", label: "Type" },
        { key: "scope", label: "Scope" },
        { key: "status", label: "Status" },
        { key: "subject", label: "Subject" },
      ], memories.map((m) => ({
        id: m.id,
        memoryType: m.memoryType,
        scope: String(m.scope ?? ""),
        status: String(m.status ?? ""),
        subject: m.subject ?? "",
      }))));
    } else {
      blocks.push(markdown("No memories recorded."));
    }
    return { status: "completed", blocks };
  },

  "admin.mcp": async (_ctx, _spec, _args, deps) => {
    const body = await deps.mcp.list();
    const servers = body.servers ?? [];
    const blocks: ResponseBlock[] = [heading("MCP servers", 2)];
    if (!servers.length) {
      blocks.push(markdown("No MCP servers are configured."));
      return { status: "completed", blocks };
    }
    blocks.push(dataTable("Servers", [
      { key: "id", label: "Server" },
      { key: "name", label: "Name" },
      { key: "transport", label: "Transport" },
      { key: "enabled", label: "Enabled" },
      { key: "untrusted", label: "Untrusted" },
    ], servers.map((s) => ({
      id: s.id,
      name: s.name ?? "",
      transport: s.transport,
      enabled: s.enabled ? "yes" : "no",
      untrusted: s.untrusted ? "yes" : "no",
    }))));
    return { status: "completed", blocks };
  },

  "markets.quote": async (_ctx, _spec, args, deps) => {
    const symbols = (Array.isArray(args.positionals.symbols) ? (args.positionals.symbols as string[]) : [])
      .map((s) => s.trim())
      .filter(Boolean)
      .join(",");
    if (!symbols) return invalid("MISSING_ARG", "Usage: `/quote <symbol> [symbol…]` (e.g. `/quote AAPL BTC`).");
    const { ok, status, data } = await deps.frontDoor.request(
      `/api/quote?symbols=${encodeURIComponent(symbols)}`,
      { timeoutMs: 30_000 },
    );
    if (!ok) return fail("QUOTE_FAILED", frontDoorError(data, status));
    const quotes = Array.isArray((data as { quotes?: unknown }).quotes)
      ? (data as { quotes: Array<Record<string, unknown>> }).quotes
      : [];
    const blocks: ResponseBlock[] = [heading("Quotes", 2)];
    if (!quotes.length) {
      blocks.push(markdown("No symbols were resolved."));
      return { status: "completed", blocks };
    }
    blocks.push(dataTable("Quotes", [
      { key: "symbol", label: "Symbol" },
      { key: "name", label: "Name" },
      { key: "price", label: "Price" },
      { key: "change", label: "Change" },
      { key: "currency", label: "Ccy" },
      { key: "freshness", label: "Freshness" },
    ], quotes.map((q) => {
      const found = q.found !== false;
      return {
        symbol: String(q.symbol ?? ""),
        name: String(q.name ?? ""),
        price: found ? Number(q.price ?? 0) : "unavailable",
        change: found ? `${Number(q.changePercent ?? 0).toFixed(2)}%` : "",
        currency: String(q.currency ?? ""),
        freshness: found ? String(q.freshness ?? "") : "unavailable",
      };
    })));
    return { status: "completed", blocks };
  },

  "research.run": async (_ctx, spec, args, deps) => {
    const question = (Array.isArray(args.positionals.question) ? (args.positionals.question as string[]) : [])
      .join(" ")
      .trim();
    if (!question) return invalid("MISSING_ARG", `Usage: \`/${spec.name} <question>\`.`);
    const deep = spec.name === "deep-research";
    const depth = typeof args.flags.depth === "string" ? args.flags.depth : deep ? "deep" : "standard";
    const { ok, status, data } = await deps.frontDoor.request("/api/research/run", {
      method: "POST",
      body: { question, depth, ...(deep ? { crossValidationRequired: true, minSources: 4 } : {}) },
      timeoutMs: 900_000,
    });
    if (!ok) return fail("RESEARCH_FAILED", frontDoorError(data, status));
    const result = (data as { result?: unknown }).result ?? data;
    return { status: "completed", blocks: researchBlocks(deep ? "Deep research" : "Research", result) };
  },

  "research.web": async (_ctx, _spec, args, deps) => {
    const target = (Array.isArray(args.positionals.target) ? (args.positionals.target as string[]) : [])
      .join(" ")
      .trim();
    if (!target) return invalid("MISSING_ARG", "Usage: `/web <url or query>`.");
    const { ok, status, data } = await deps.frontDoor.request("/api/research/run", {
      method: "POST",
      body: { question: `Research and summarize: ${target}`, depth: "standard", sourceTypes: ["web"], maxSources: 5, maxTimeSeconds: 60 },
      timeoutMs: 120_000,
    });
    if (!ok) return fail("WEB_FAILED", frontDoorError(data, status));
    return { status: "completed", blocks: researchBlocks("Web research", (data as { result?: unknown }).result ?? data) };
  },

  "research.read": async (_ctx, _spec, args, deps) => {
    const target = (Array.isArray(args.positionals.target) ? (args.positionals.target as string[]) : [])
      .join(" ")
      .trim();
    if (!target) return invalid("MISSING_ARG", "Usage: `/read <url or document>`.");
    const { ok, status, data } = await deps.frontDoor.request("/api/research/run", {
      method: "POST",
      body: { question: `Extract and summarize the content at: ${target}`, depth: "standard", sourceTypes: ["web"], maxSources: 3, maxQueries: 3, maxTimeSeconds: 60 },
      timeoutMs: 120_000,
    });
    if (!ok) return fail("READ_FAILED", frontDoorError(data, status));
    return { status: "completed", blocks: researchBlocks("Document summary", (data as { result?: unknown }).result ?? data) };
  },

  "quant.backtest": async (_ctx, _spec, args, deps) => {
    const strategyId = str(args.positionals.strategyId).trim();
    if (!strategyId) {
      const { ok, status, data } = await deps.frontDoor.request("/api/backtest/strategies", { timeoutMs: 60_000 });
      if (!ok) return fail("BACKTEST_FAILED", frontDoorError(data, status));
      const strategies = Array.isArray((data as { strategies?: unknown }).strategies)
        ? (data as { strategies: Array<Record<string, unknown>> }).strategies
        : [];
      const blocks: ResponseBlock[] = [heading("Backtest strategies", 2)];
      if (!strategies.length) {
        blocks.push(markdown("No saved strategies. Create one in the Backtest screen, then run `/backtest <strategyId>`."));
      } else {
        blocks.push(markdown("Run one with `/backtest <strategyId>`."));
        blocks.push(dataTable("Saved strategies", [
          { key: "id", label: "Strategy" },
          { key: "name", label: "Name" },
          { key: "version", label: "Version" },
        ], strategies.slice(0, 50).map((s) => ({
          id: String(s.id ?? s.strategyId ?? ""),
          name: String(s.name ?? s.title ?? ""),
          version: String(s.version ?? ""),
        }))));
      }
      return { status: "completed", blocks };
    }
    const { ok, status, data } = await deps.frontDoor.request("/api/backtest/backtest", {
      method: "POST",
      body: { strategyId },
      timeoutMs: 300_000,
    });
    if (!ok) return fail("BACKTEST_FAILED", frontDoorError(data, status));
    const result = (data as { result?: unknown }).result ?? (data as { metrics?: unknown }).metrics ?? data;
    return { status: "completed", blocks: metricBlocks(`Backtest: ${strategyId}`, result) };
  },

  "runtime.terminal": async (ctx, _spec, args, deps) => {
    const command = (Array.isArray(args.positionals.command) ? (args.positionals.command as string[]) : [])
      .join(" ")
      .trim();
    if (!command) return invalid("MISSING_ARG", "Usage: `/terminal <command>`.");
    const { ok, status, data } = await deps.frontDoor.request("/api/terminal/execute", {
      method: "POST",
      body: { command },
      timeoutMs: 900_000,
    });
    if (!ok) return fail("TERMINAL_FAILED", frontDoorError(data, status));
    const d = (data ?? {}) as Record<string, unknown>;
    const stdout = String(d.stdout ?? d.output ?? "");
    const stderr = String(d.stderr ?? "");
    const exitCode = d.exitCode ?? d.exit_code ?? d.code;
    const blocks: ResponseBlock[] = [heading("Terminal", 2)];
    if (stdout) blocks.push(markdown("```\n" + stdout.slice(0, 18_000) + "\n```"));
    if (stderr) blocks.push(callout("warning", "stderr", "```\n" + stderr.slice(0, 4_000) + "\n```"));
    if (!stdout && !stderr) blocks.push(markdown("The command produced no output."));
    if (exitCode !== undefined) {
      blocks.push(keyValue("Result", [
        { label: "Exit code", value: typeof exitCode === "number" ? exitCode : String(exitCode) },
        { label: "Actor", value: ctx.operator ? "operator" : "user" },
      ]));
    }
    return { status: "completed", blocks };
  },

  "code.task": async (_ctx, _spec, args, deps) => {
    const query = (Array.isArray(args.positionals.task) ? (args.positionals.task as string[]) : [])
      .join(" ")
      .trim();
    if (!query) return invalid("MISSING_ARG", "Usage: `/code <task description>`.");
    const autonomy = typeof args.flags.autonomy === "string" ? args.flags.autonomy : "plan_only";
    const { ok, status, data } = await deps.frontDoor.request("/api/code/tasks", {
      method: "POST",
      body: { query, autonomy },
      timeoutMs: 300_000,
    });
    if (!ok) return fail("CODE_FAILED", frontDoorError(data, status));
    const task = (data as { task?: Record<string, unknown> }).task ?? {};
    return {
      status: "completed",
      blocks: [
        heading("Code task", 2),
        keyValue("Task", [
          { label: "Id", value: String(task.id ?? "—") },
          { label: "Status", value: String(task.status ?? "created") },
        ]),
        callout("note", "Runs in the background", "Track this task in the Code screen. It edits a disposable workspace unless it was created from a selected folder."),
      ],
    };
  },

  "skills.catalog": async (ctx, _spec, args, deps) => {
    const action = str(args.positionals.action) || "list";
    const subject = Array.isArray(args.positionals.subject) ? (args.positionals.subject as string[]) : [];
    switch (action) {
      case "list": {
        const status = typeof args.flags.status === "string" ? args.flags.status : undefined;
        const skills = await deps.skills.list(status);
        return { status: "completed", blocks: skillListBlocks("Installed skills", skills) };
      }
      case "search": {
        const query = subject.join(" ").trim();
        if (!query) return invalid("MISSING_ARG", "Usage: `/skills search <keyword>`.");
        const skills = await deps.skills.discover({ query });
        return { status: "completed", blocks: skillListBlocks(`Skills matching “${query}”`, skills) };
      }
      case "category": {
        const category = subject[0];
        if (!category) return invalid("MISSING_ARG", "Usage: `/skills category <category>`.");
        const skills = await deps.skills.discover({ category });
        return { status: "completed", blocks: skillListBlocks(`Skills in “${category}”`, skills) };
      }
      case "show": {
        const id = subject[0];
        if (!id) return invalid("MISSING_ARG", "Usage: `/skills show <skill-id>`.");
        const detail = await deps.skills.get(id);
        if (!detail) return fail("SKILL_NOT_FOUND", `No skill named \`${id}\`.`);
        return { status: "completed", blocks: skillDetailBlocks(detail) };
      }
      case "run": {
        const id = subject[0];
        if (!id) return invalid("MISSING_ARG", "Usage: `/skills run <skill-id>`.");
        const result = await deps.skills.execute({ skillId: id, executionMode: "interactive" }, { operator: ctx.operator });
        return renderSkillExecution(result);
      }
      case "test": {
        const id = subject[0];
        if (!id) return invalid("MISSING_ARG", "Usage: `/skills test <skill-id>`.");
        return runSkillTest(id, args, deps);
      }
      case "validate": {
        const id = subject[0];
        if (!id) return invalid("MISSING_ARG", "Usage: `/skills validate <skill-id>`.");
        const preflight = await deps.skills.preflight(id);
        return { status: "completed", blocks: skillPreflightBlocks(id, preflight) };
      }
      default:
        return invalid("INVALID_ENUM", `Unknown action \`${action}\`. Use list, search, category, show, run, test, or validate.`);
    }
  },

  "skill.explain": async (_ctx, _spec, args, deps) => {
    const skillId = str(args.positionals.skillId);
    if (!skillId) return invalid("MISSING_ARG", "Usage: `/skill-explain <skill-id>`.");
    const detail = await deps.skills.get(skillId);
    if (!detail) return fail("SKILL_NOT_FOUND", `No skill named \`${skillId}\`.`);
    return { status: "completed", blocks: skillDetailBlocks(detail) };
  },

  "skill.test": async (_ctx, _spec, args, deps) => {
    const skillId = str(args.positionals.skillId);
    if (!skillId) return invalid("MISSING_ARG", "Usage: `/skill-test <skill-id>`.");
    return runSkillTest(skillId, args, deps);
  },

  "skill.enable": async (ctx, _spec, args, deps) => {
    const skillId = str(args.positionals.skillId);
    if (!skillId) return invalid("MISSING_ARG", "Usage: `/skill-enable <skill-id>`.");
    await deps.skills.enable(skillId, ctx.operator, typeof args.flags.version === "string" ? args.flags.version : undefined);
    return { status: "completed", markdownText: `**Enabled** \`${skillId}\`. It is now eligible for discovery and execution.` };
  },

  "skill.disable": async (ctx, _spec, args, deps) => {
    const skillId = str(args.positionals.skillId);
    if (!skillId) return invalid("MISSING_ARG", "Usage: `/skill-disable <skill-id>`.");
    await deps.skills.disable(skillId, ctx.operator, typeof args.flags.version === "string" ? args.flags.version : undefined);
    return { status: "completed", markdownText: `**Disabled** \`${skillId}\`. New executions are blocked; running ones follow the cancellation policy.` };
  },

  "skill.create": async (ctx, _spec, args, deps) => {
    const nameArg = str(args.positionals.name).trim();
    const fromTask = typeof args.flags["from-task"] === "string" ? args.flags["from-task"] : "";
    const fromWorkflow = typeof args.flags["from-workflow"] === "string" ? args.flags["from-workflow"] : "";
    const objective = typeof args.flags.objective === "string" ? args.flags.objective : "";
    const category = typeof args.flags.category === "string" ? args.flags.category : undefined;

    if (fromTask) {
      const res = await deps.skills.learnFromRun(fromTask, ctx.operator, nameArg || undefined);
      if (!res.ok || !res.created?.length) {
        return fail("NO_CANDIDATE", `No reusable skill candidate was produced from \`${fromTask}\`.`);
      }
      return {
        status: "completed",
        markdownText: `**Draft proposed.** Candidate(s) created from \`${fromTask}\`:\n\n${res.created
          .map((c) => `- \`${c.id}\` — ${c.title}`)
          .join("\n")}\n\nDrafts are inert until reviewed and their evaluation passes.`,
      };
    }
    if (fromWorkflow) {
      return renderDraft(await deps.skills.learnFromSource({
        sourceKind: "repeated_workflow",
        title: nameArg || `Skill from workflow ${fromWorkflow}`,
        objective: objective || `Reusable procedure learned from workflow ${fromWorkflow}.`,
        sourceRunId: fromWorkflow,
        ...(category ? { category } : {}),
      }));
    }
    if (objective) {
      return renderDraft(await deps.skills.learnFromSource({
        sourceKind: "document",
        title: nameArg || objective.slice(0, 60),
        objective,
        content: objective,
        ...(category ? { category } : {}),
      }));
    }
    return invalid(
      "MISSING_ARG",
      "`/skill-create` needs a source: pass `--from-task <id>`, `--from-workflow <id>`, or `--objective \"…\"`. Refusing to guess.",
    );
  },
};

export function frontDoorError(data: unknown, status: number): string {
  const d = (data ?? {}) as { error?: unknown; detail?: unknown };
  const msg = typeof d.error === "string" ? d.error : typeof d.detail === "string" ? d.detail : undefined;
  return msg ?? `request failed (HTTP ${status})`;
}

function researchBlocks(title: string, result: unknown): ResponseBlock[] {
  const r = (result ?? {}) as Record<string, unknown>;
  const blocks: ResponseBlock[] = [heading(title, 2)];
  const answer = typeof r.answer === "string" ? r.answer : "";
  if (answer) blocks.push(markdown(answer.slice(0, 18_000)));
  else blocks.push(markdown("The research engine returned no synthesized answer."));
  const sources = Array.isArray(r.sources) ? (r.sources as Array<Record<string, unknown>>) : [];
  const citations = Array.isArray(r.citations) ? (r.citations as Array<Record<string, unknown>>) : [];
  const list = citations.length ? citations : sources;
  if (list.length) {
    blocks.push(dataTable("Sources", [
      { key: "title", label: "Source" },
      { key: "url", label: "URL" },
    ], list.slice(0, 50).map((s) => ({
      title: String(s.title ?? s.name ?? s.url ?? ""),
      url: String(s.url ?? s.href ?? ""),
    }))));
  }
  const status = r.status as Record<string, unknown> | undefined;
  if (status && typeof status.state === "string") {
    const claims = Array.isArray(r.claims) ? (r.claims as unknown[]).length : 0;
    blocks.push(callout("note", `Status: ${status.state}`, `${list.length} source(s), ${claims} claim(s).`));
  }
  return blocks;
}

function metricBlocks(title: string, value: unknown): ResponseBlock[] {
  const blocks: ResponseBlock[] = [heading(title, 2)];
  const scalars = flattenScalars(value);
  if (scalars.length) {
    blocks.push(keyValue("Metrics", scalars));
  } else {
    blocks.push(markdown("```json\n" + JSON.stringify(value).slice(0, 6_000) + "\n```"));
  }
  return blocks;
}

function flattenScalars(value: unknown): Array<{ label: string; value: string | number }> {
  const out: Array<{ label: string; value: string | number }> = [];
  if (value === null || typeof value !== "object") return out;
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (typeof v === "number") out.push({ label: k, value: v });
    else if (typeof v === "string" && v.length <= 60) out.push({ label: k, value: v });
    else if (v && typeof v === "object" && (k === "metrics" || k === "result")) {
      for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) {
        if (typeof v2 === "number") out.push({ label: k2, value: v2 });
        else if (typeof v2 === "string" && v2.length <= 60) out.push({ label: k2, value: v2 });
      }
    }
  }
  return out.slice(0, 24);
}

function renderDraft(draft: LearnDraftResult): HandlerOutput {
  if (!draft.ok || !draft.draft) {
    return fail("DRAFT_FAILED", draft.error ?? "The learning engine did not produce a draft.");
  }
  return {
    status: "completed",
    markdownText:
      `**Draft created:** \`${draft.draft.id}\` (v${draft.draft.version}). ` +
      `Status: ${draft.draft.status}, evaluation: ${draft.draft.evaluationStatus}. ` +
      "It is not enabled until it passes evaluation and is approved.",
  };
}

function skillListBlocks(title: string, skills: SkillSummary[]): ResponseBlock[] {
  const blocks: ResponseBlock[] = [heading(title, 2)];
  if (!skills.length) {
    blocks.push(markdown("No skills matched."));
    return blocks;
  }
  blocks.push(dataTable(`${skills.length} skill(s)`, [
    { key: "id", label: "Skill" },
    { key: "category", label: "Category" },
    { key: "status", label: "Status" },
    { key: "evaluationStatus", label: "Evaluation" },
    { key: "riskLevel", label: "Risk" },
    { key: "description", label: "Description" },
  ], skills.map((s) => ({
    id: s.id,
    category: s.category,
    status: s.status,
    evaluationStatus: s.evaluationStatus,
    riskLevel: s.riskLevel,
    description: s.description,
  }))));
  return blocks;
}

function skillDetailBlocks(detail: SkillDetail): ResponseBlock[] {
  const blocks: ResponseBlock[] = [
    heading(`${detail.name} \`${detail.id}\``, 2),
    markdown(detail.description),
    keyValue("Details", [
      { label: "Version", value: detail.version },
      { label: "Status", value: detail.status },
      { label: "Evaluation", value: detail.evaluationStatus },
      { label: "Category", value: detail.category },
      { label: "Risk", value: detail.riskLevel },
      { label: "Origin", value: detail.origin ?? "unknown" },
      { label: "Author", value: detail.author || "—" },
      { label: "Provenance", value: detail.provenance ?? "unknown" },
    ]),
    keyValue("Requirements", [
      { label: "Tools", value: detail.requiredTools.join(", ") || "none" },
      { label: "Permissions", value: detail.permissions.join(", ") || "none" },
      { label: "Dependencies", value: detail.requiredSkills.map((d) => d.skillId).join(", ") || "none" },
    ]),
    keyValue("Limits", [
      { label: "Max steps", value: detail.limits.maxSteps },
      { label: "Timeout (ms)", value: detail.limits.timeoutMs },
      { label: "Max tool calls", value: detail.limits.maxToolCalls },
    ]),
  ];
  if (detail.inputSchema && Object.keys(detail.inputSchema).length) {
    blocks.push(markdown(`**Input schema**\n\n\`\`\`json\n${JSON.stringify(detail.inputSchema).slice(0, 2000)}\n\`\`\``));
  }
  if (!detail.validation.ok) {
    blocks.push(callout("warning", "Validation", detail.validation.errors.join("; ") || "Validation reported problems."));
  }
  return blocks;
}

function skillPreflightBlocks(
  id: string,
  preflight: { ok: boolean; reasons: string[]; validation: unknown; dependencyGraph: unknown },
): ResponseBlock[] {
  const blocks: ResponseBlock[] = [heading(`Preflight: \`${id}\``, 2)];
  blocks.push(preflight.ok
    ? callout("success", "Ready", "Dependencies, tools, and permissions resolve.")
    : callout("warning", "Blocked", preflight.reasons.join("; ") || "Preflight reported problems."));
  return blocks;
}

function skillEvaluationBlocks(
  id: string,
  result: { status: string; dimensions: Array<{ name: string; status: string; detail: string }>; error?: string },
): ResponseBlock[] {
  const blocks: ResponseBlock[] = [heading(`Evaluation: \`${id}\``, 2)];
  blocks.push(result.status === "passed"
    ? callout("success", "Passed", "Every mandatory dimension passed.")
    : callout("warning", `Status: ${result.status}`, result.error ?? "The evaluation did not fully pass. A skill is not validated merely because files exist."));
  if (result.dimensions?.length) {
    blocks.push(dataTable("Dimensions", [
      { key: "name", label: "Dimension" },
      { key: "status", label: "Status" },
      { key: "detail", label: "Detail" },
    ], result.dimensions.map((d) => ({ name: d.name, status: d.status, detail: d.detail }))));
  }
  return blocks;
}

async function runSkillTest(id: string, args: BoundArgs, deps: CommandDeps): Promise<HandlerOutput> {
  const regression = args.flags.regression === true;
  const result = await deps.skills.evaluate(id, undefined, regression);
  return { status: "completed", blocks: skillEvaluationBlocks(id, result) };
}

function renderSkillExecution(result: SkillExecutionResult): HandlerOutput {
  const blocks: ResponseBlock[] = [heading(`Skill \`${result.skillId}\`${result.version ? ` v${result.version}` : ""}`, 2)];
  const ok = !result.error;
  blocks.push(ok
    ? callout("success", "Completed", result.outputValidated ? "Output validated against the declared schema." : "Completed, but the output was not schema-validated.")
    : callout("danger", `Failed: ${result.error?.code ?? "error"}`, result.error?.message ?? "The skill did not complete."));
  if (result.output) {
    blocks.push(markdown(result.output));
  }
  if (result.warnings?.length) {
    blocks.push(callout("warning", "Warnings", result.warnings.join("\n\n")));
  }
  if (result.missingData?.length) {
    blocks.push(callout("warning", "Missing data", result.missingData.join("\n\n")));
  }
  if (result.limitations?.length) {
    blocks.push(callout("note", "Limitations", result.limitations.join("\n\n")));
  }
  const metrics = result.metrics ?? {};
  if (Object.keys(metrics).length) {
    blocks.push(keyValue("Execution", Object.entries(metrics).slice(0, 12).map(([k, v]) => ({
      label: k,
      value: typeof v === "number" || typeof v === "string" ? v : JSON.stringify(v),
    }))));
  }
  return {
    status: ok ? "completed" : "failed",
    blocks,
    meta: {
      skillId: result.skillId,
      skillVersion: result.version ?? undefined,
      runId: result.runId ?? undefined,
      executionId: result.runId ?? undefined,
      outputValidated: result.outputValidated,
      warnings: result.warnings,
    },
    ...(result.error ? { error: { code: result.error.code, message: result.error.message } } : {}),
  };
}


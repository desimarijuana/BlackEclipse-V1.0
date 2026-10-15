// ─── Shared command execution router ─────────────────────────────────────────
// Every slash command runs through ONE sequence:
//   Parse → Resolve → Validate → Authorize → Execute → Render → Audit.
// The router owns no agent loop, task queue, or skill database — it dispatches to
// the existing systems (skills-client, tasks-client, workflows-client, the Python
// runtime) and renders their real output. Handlers are injected (`CommandDeps`) so
// the router is fully unit-testable without a live runtime.

import {
  allCommands,
  commandArgHint,
  isCommandAvailable,
  listCommands,
  type CommandCategory,
  type CommandSpec,
} from "./command-registry";
import { parseAndBind, type BoundArgs, type CommandInvocation } from "./command-parser";
import { callout, dataTable, fenceEnvelope, heading, keyValue, markdown } from "./command-render";
import type { ResponseBlock } from "@/lib/response/contract";
import { redactSecrets } from "./errors";
import {
  disableSkill,
  discoverSkills,
  enableSkill,
  evaluateSkill,
  executeSkill,
  getSkill,
  getSkillPreflight,
  learnFromRun,
  learnFromSource,
  listSkills,
  validateSkillInput,
} from "./skills-client";
import type {
  LearnDraftResult,
  LearnRequest,
  SkillDetail,
  SkillExecutionRequest,
  SkillExecutionResult,
  SkillSummary,
} from "./skills-types";
import { tasksClient } from "./tasks-client";
import { listWorkflows } from "./workflows-client";
import {
  getUsageSummaryFromRuntime,
  listAgentsFromRuntime,
  listModelProviders,
  runtimeHealth,
} from "./python-client";
import { fetchMarketHealth, fetchMarketProviders } from "./market-client";
import { listPortfolios } from "./portfolio-client";
import { listMemories, memoryOverview } from "./eclipse-memory-client";
import { listMCPServers } from "./mcp-client";

export type CommandRunStatus =
  | "completed"
  | "failed"
  | "unsupported"
  | "unavailable"
  | "invalid"
  | "denied"
  | "unknown";

export interface CommandAuditEvent {
  commandId: string;
  command: string;
  actor: "user" | "agent";
  operator: boolean;
  status: CommandRunStatus;
  handlerTarget: string;
  at: string;
  durationMs: number;
  skillId?: string;
  runId?: string;
  errorCode?: string;
}

export interface CommandResult {
  ok: boolean;
  command: string;
  commandId: string;
  status: CommandRunStatus;
  /** Markdown and/or an `eclipse-response` fence, ready for the chat renderer. */
  output: string;
  error?: { code: string; message: string };
  meta?: {
    skillId?: string;
    skillVersion?: string;
    runId?: string;
    executionId?: string;
    outputValidated?: boolean;
    warnings?: string[];
    durationMs?: number;
  };
  audit: CommandAuditEvent;
}

export interface CommandContext {
  /** Whether the caller passed the operator gate (transport/token). */
  operator: boolean;
  actor?: "user" | "agent";
}

export interface CommandDeps {
  skills: {
    list(status?: string): Promise<SkillSummary[]>;
    discover(p: { query?: string; category?: string; status?: string }): Promise<SkillSummary[]>;
    get(id: string): Promise<SkillDetail | null>;
    preflight(id: string): Promise<{ ok: boolean; reasons: string[]; validation: unknown; dependencyGraph: unknown }>;
    validateInput(id: string, input: Record<string, unknown>): Promise<{ valid: boolean; issues: string[] }>;
    execute(req: SkillExecutionRequest, opts?: { operator?: boolean }): Promise<SkillExecutionResult>;
    evaluate(
      id: string,
      version?: string,
      regression?: boolean,
    ): Promise<{ status: string; dimensions: Array<{ name: string; status: string; detail: string }>; error?: string }>;
    enable(id: string, operator: boolean, version?: string): Promise<unknown>;
    disable(id: string, operator: boolean, version?: string): Promise<unknown>;
    learnFromSource(req: LearnRequest): Promise<LearnDraftResult>;
    learnFromRun(runId: string, operator: boolean, intent?: string): Promise<{ ok: boolean; created: Array<{ id: string; title: string }> }>;
  };
  tasks: {
    listPlans(): Promise<{ plans: Array<Record<string, unknown>> }>;
    listTasks(p: { planId?: string; status?: string }): Promise<{ tasks: Array<Record<string, unknown>> }>;
  };
  workflows: { list(): Promise<Array<Record<string, unknown>>> };
  runtime: {
    health(): Promise<{ ok: boolean; tools?: string[]; providers?: string[] }>;
    models(): Promise<Array<Record<string, unknown>>>;
    agents(): Promise<{ agents: Array<Record<string, unknown>>; defaultAgentId: string }>;
  };
  market: {
    providers(): Promise<Awaited<ReturnType<typeof fetchMarketProviders>>>;
    health(): Promise<Awaited<ReturnType<typeof fetchMarketHealth>>>;
  };
  portfolio: { list(): Promise<Awaited<ReturnType<typeof listPortfolios>>> };
  memory: {
    overview(): Promise<Awaited<ReturnType<typeof memoryOverview>>>;
    list(filters: { memoryType?: string; status?: string; limit?: number }): Promise<Awaited<ReturnType<typeof listMemories>>>;
  };
  mcp: { list(): Promise<Awaited<ReturnType<typeof listMCPServers>>> };
  usage: { summary(days: number): Promise<Awaited<ReturnType<typeof getUsageSummaryFromRuntime>>> };
  now(): number;
}

export function defaultCommandDeps(): CommandDeps {
  return {
    skills: {
      list: async (status) => (await listSkills(status)).skills,
      discover: (p) => discoverSkills(p),
      get: (id) => getSkill(id),
      preflight: (id) => getSkillPreflight(id),
      validateInput: (id, input) => validateSkillInput(id, input),
      execute: (req, opts) => executeSkill(req, opts),
      evaluate: (id, version, regression) => evaluateSkill(id, version, regression),
      enable: (id, operator, version) => enableSkill(id, operator, version),
      disable: (id, operator, version) => disableSkill(id, operator, version),
      learnFromSource: (req) => learnFromSource(req),
      learnFromRun: (runId, operator, intent) => learnFromRun(runId, operator, intent),
    },
    tasks: {
      listPlans: () =>
        tasksClient.listPlans() as unknown as Promise<{ plans: Array<Record<string, unknown>> }>,
      listTasks: (p) =>
        tasksClient.listTasks(
          p as unknown as Parameters<typeof tasksClient.listTasks>[0],
        ) as unknown as Promise<{ tasks: Array<Record<string, unknown>> }>,
    },
    workflows: { list: () => listWorkflows() as unknown as Promise<Array<Record<string, unknown>>> },
    runtime: {
      health: () => runtimeHealth(),
      models: () => listModelProviders(),
      agents: () => listAgentsFromRuntime(),
    },
    market: {
      providers: () => fetchMarketProviders(),
      health: () => fetchMarketHealth(),
    },
    portfolio: { list: () => listPortfolios() },
    memory: {
      overview: () => memoryOverview(),
      list: (filters) => listMemories(filters),
    },
    mcp: { list: () => listMCPServers() },
    usage: { summary: (days) => getUsageSummaryFromRuntime(days) },
    now: () => Date.now(),
  };
}

interface HandlerOutput {
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

function fail(code: string, message: string): HandlerOutput {
  return { status: "failed", error: { code, message } };
}

function invalid(code: string, message: string): HandlerOutput {
  return { status: "invalid", error: { code, message } };
}

function errorMarkdown(result: CommandResult): string {
  const title = result.status === "invalid" ? "Invalid command" :
    result.status === "denied" ? "Not authorized" :
    result.status === "unavailable" ? "Command unavailable" :
    result.status === "unsupported" ? "Unsupported capability" :
    result.status === "unknown" ? "Unknown command" : "Command failed";
  const detail = result.error?.message ?? "The command could not be completed.";
  return `**${title}.** ${detail}`;
}

// ── Handlers ─────────────────────────────────────────────────────────────────

const handlers: Record<string, Handler> = {
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

// ── Execution ────────────────────────────────────────────────────────────────

function buildResult(
  spec: CommandSpec | null,
  name: string,
  ctx: CommandContext,
  handlerTarget: string,
  startedAt: number,
  deps: CommandDeps,
  output: HandlerOutput,
): CommandResult {
  const command = spec?.name ?? name;
  const commandId = spec?.id ?? `unknown.${name}`;
  const result: CommandResult = {
    ok: output.status === "completed",
    command,
    commandId,
    status: output.status,
    output: "",
    error: output.error,
    meta: output.meta,
    audit: {
      commandId,
      command,
      actor: ctx.actor ?? "user",
      operator: ctx.operator,
      status: output.status,
      handlerTarget,
      at: new Date(startedAt).toISOString(),
      durationMs: Math.max(0, deps.now() - startedAt),
      ...(output.meta?.skillId ? { skillId: output.meta.skillId } : {}),
      ...(output.meta?.runId ? { runId: output.meta.runId } : {}),
      ...(output.error ? { errorCode: output.error.code } : {}),
    },
  };

  let outputText = "";
  if (output.markdownText) outputText = output.markdownText;
  if (output.blocks?.length) {
    const fence = fenceEnvelope(output.blocks);
    outputText = outputText ? `${outputText}\n\n${fence}` : fence;
  }
  if (!outputText) outputText = errorMarkdown(result);
  result.output = outputText;
  return result;
}

/** Execute a resolved invocation. Never throws. */
export async function executeCommand(
  invocation: CommandInvocation,
  args: BoundArgs,
  ctx: CommandContext,
  deps: CommandDeps = defaultCommandDeps(),
): Promise<CommandResult> {
  const startedAt = deps.now();
  const { spec, name } = invocation;
  const actor = ctx.actor ?? "user";

  // Resolve.
  if (!spec) {
    return buildResult(null, name, { ...ctx, actor }, "unknown", startedAt, deps, {
      status: "unknown",
      error: { code: "UNKNOWN_COMMAND", message: `No command \`/${name}\`. Type \`/help\` to see the catalog.` },
    });
  }

  // Validate.
  if (args.errors.length) {
    const message = `${args.errors.map((e) => e.message).join(" ")} Usage: \`/${spec.name} ${commandArgHint(spec)}\`.`.trim();
    return buildResult(spec, name, { ...ctx, actor }, spec.handler.target, startedAt, deps, {
      status: "invalid",
      error: { code: args.errors[0].code, message },
    });
  }

  // Availability.
  if (!isCommandAvailable(spec)) {
    return buildResult(spec, name, { ...ctx, actor }, spec.handler.target, startedAt, deps, {
      status: "unavailable",
      error: {
        code: "COMMAND_UNAVAILABLE",
        message: `\`/${spec.name}\` is registered but not available yet. ${spec.unavailabilityReason ?? ""}`.trim(),
      },
    });
  }

  // Authorization.
  if (spec.permissions.approval === "operator" && !ctx.operator) {
    return buildResult(spec, name, { ...ctx, actor }, spec.handler.target, startedAt, deps, {
      status: "denied",
      error: { code: "NOT_AUTHORIZED", message: `\`/${spec.name}\` requires an authorized operator.` },
    });
  }

  // Execute.
  const handler = handlers[spec.handler.target];
  if (!handler) {
    return buildResult(spec, name, { ...ctx, actor }, spec.handler.target, startedAt, deps, {
      status: "unsupported",
      error: {
        code: "HANDLER_NOT_IMPLEMENTED",
        message: `\`/${spec.name}\` has no handler for \`${spec.handler.target}\`.`,
      },
    });
  }

  let output: HandlerOutput;
  try {
    output = await handler({ ...ctx, actor }, spec, args, deps);
  } catch (err) {
    output = fail("EXECUTION_ERROR", redactSecrets(err instanceof Error ? err.message : String(err)));
  }

  const result = buildResult(spec, name, { ...ctx, actor }, spec.handler.target, startedAt, deps, output);
  try {
    // Structured audit (no secrets; command ids and statuses only).
    console.info("[command]", JSON.stringify(result.audit));
  } catch {
    /* audit logging must never break execution */
  }
  return result;
}

/**
 * Parse + execute a raw chat message. Returns null when the text is not a slash
 * command (ordinary prose — the caller falls through to the normal agent path).
 * A leading `/token` that resolves to no command yields an `unknown` result.
 */
export async function executeCommandFromText(
  text: string,
  ctx: CommandContext,
  deps: CommandDeps = defaultCommandDeps(),
): Promise<CommandResult | null> {
  const parsed = parseAndBind(text);
  if (!parsed) return null;
  return executeCommand(parsed.invocation, parsed.args, ctx, deps);
}

/** Whether a resolved spec should be intercepted by the router (vs. the agent/profile path). */
export function isRoutedCommand(spec: CommandSpec | null): boolean {
  return Boolean(spec && spec.handler.type !== "profile" && spec.handler.type !== "agent");
}

export { listCommands };

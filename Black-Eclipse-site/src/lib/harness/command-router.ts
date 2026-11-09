// ─── Shared command execution router ─────────────────────────────────────────
// Every slash command runs through ONE sequence:
//   Parse → Resolve → Validate → Authorize → Execute → Render → Audit.
// The router owns no agent loop, task queue, or skill database — it dispatches to
// the existing systems (skills-client, tasks-client, workflows-client, the Python
// runtime) and renders their real output. Handlers are injected (`CommandDeps`) so
// the router is fully unit-testable without a live runtime.

import {
  commandArgHint,
  isCommandAvailable,
  listCommands,
  type CommandSpec,
} from "./command-registry";
import { parseAndBind, type BoundArgs, type CommandInvocation } from "./command-parser";
import { fenceEnvelope } from "./command-render";
import { fail, frontDoorError, handlers, type HandlerOutput } from "./command-handlers";
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
  compactHistoryInRuntime,
  getUsageSummaryFromRuntime,
  listAgentsFromRuntime,
  listModelProviders,
  runtimeHealth,
  type RuntimeHistoryCompaction,
} from "./python-client";
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

/** The result of a real conversation compaction (`/compact`). */
export interface CompactionPayload {
  /** The fenced `<compacted-conversation>` block that replaces the older turns. */
  block: string;
  droppedTurns: number;
  keptTurns: number;
}

export interface CommandResult {
  ok: boolean;
  command: string;
  commandId: string;
  status: CommandRunStatus;
  /** Markdown and/or an `eclipse-response` fence, ready for the chat renderer. */
  output: string;
  error?: { code: string; message: string };
  /** A real compaction produced by `/compact`; persisted by the chat route. */
  compaction?: CompactionPayload;
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
  /** The requesting app origin, for same-origin front-door calls (e.g. `/api/quote`). */
  origin?: string;
  /**
   * The conversation BEFORE the new user message. Present only on chat
   * surfaces; `/compact` needs it, and its absence is reported honestly.
   */
  history?: Array<{ role: "user" | "assistant"; content: string }>;
  /** The conversation id, so a successful compaction can be persisted. */
  chatId?: string;
}

export interface FrontDoorResult {
  ok: boolean;
  status: number;
  data: unknown;
}

export interface CommandDeps {
  /** Calls the app's own front-door JSON APIs (loopback) — never a second server. */
  frontDoor: {
    request(
      path: string,
      init?: { method?: string; body?: unknown; timeoutMs?: number },
    ): Promise<FrontDoorResult>;
  };
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
    compact(
      history: Array<{ role: "user" | "assistant"; content: string }>,
      keepTurns: number,
    ): Promise<RuntimeHistoryCompaction>;
  };
  market: {
    providers(): Promise<{
      status?: string;
      providerCount?: number;
      implementedCount?: number;
      providers?: Array<{ id: string; label: string; configured?: boolean | null; implemented?: boolean }>;
      available?: boolean;
    }>;
    health(): Promise<{ available: boolean; cache?: { entries: number; hits: number; misses: number }; reason?: string }>;
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

/** Base URL for same-origin front-door calls: always loopback, so `guardMutation`
 *  on the target route authorizes by local host regardless of how the user
 *  reached the app (localhost, 127.0.0.1, or a LAN IP). */
function loopbackBase(origin?: string): string {
  try {
    if (origin) {
      const u = new URL(origin);
      const port = u.port || (u.protocol === "https:" ? "443" : "80");
      return `${u.protocol}//127.0.0.1:${port}`;
    }
  } catch {
    /* fall through */
  }
  return `http://127.0.0.1:${process.env.PORT ?? "3000"}`;
}

export function defaultCommandDeps(origin?: string): CommandDeps {
  const frontDoor = {
    async request(
      path: string,
      init: { method?: string; body?: unknown; timeoutMs?: number } = {},
    ): Promise<FrontDoorResult> {
      const res = await fetch(`${loopbackBase(origin)}${path}`, {
        method: init.method ?? "GET",
        headers: { "Content-Type": "application/json" },
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
        signal: AbortSignal.timeout(init.timeoutMs ?? 60_000),
      });
      const data = await res.json().catch(() => ({}));
      return { ok: res.ok, status: res.status, data };
    },
  };
  return {
    frontDoor,
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
      compact: (history, keepTurns) => compactHistoryInRuntime(history, keepTurns),
    },
    market: {
      providers: async () => {
        const { ok, status, data } = await frontDoor.request("/api/harness/market/providers", { timeoutMs: 30_000 });
        if (!ok) throw new Error(frontDoorError(data, status));
        return data as Awaited<ReturnType<CommandDeps["market"]["providers"]>>;
      },
      health: async () => {
        const { ok, status, data } = await frontDoor.request("/api/harness/market/health", { timeoutMs: 30_000 });
        if (!ok) throw new Error(frontDoorError(data, status));
        return data as Awaited<ReturnType<CommandDeps["market"]["health"]>>;
      },
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

function errorMarkdown(result: CommandResult): string {
  const title = result.status === "invalid" ? "Invalid command" :
    result.status === "denied" ? "Not authorized" :
    result.status === "unavailable" ? "Command unavailable" :
    result.status === "unsupported" ? "Unsupported capability" :
    result.status === "unknown" ? "Unknown command" : "Command failed";
  const detail = result.error?.message ?? "The command could not be completed.";
  return `**${title}.** ${detail}`;
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
    compaction: output.compaction,
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
  deps: CommandDeps = defaultCommandDeps(ctx.origin),
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
  deps: CommandDeps = defaultCommandDeps(ctx.origin),
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

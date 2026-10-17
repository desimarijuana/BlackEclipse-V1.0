// ─── Canonical slash-command registry ────────────────────────────────────────
// ONE registry consumed by the chat composer palette, the help command, and the
// shared execution router. A command describes itself declaratively (schema,
// handler, permissions, lifecycle) so the palette and the router agree on what
// exists — no command is ever advertised as functional without a handler.
//
// This module owns NO execution and NO agentic logic. It is pure data + pure
// queries (resolve / search / conflict detection) so it can be imported by both
// the client (autocomplete) and the server (routing) without side effects.

import type { TranslationKey } from "@/lib/i18n/types";

export type CommandCategory =
  | "runtime"
  | "skills"
  | "research"
  | "markets"
  | "quant"
  | "portfolio"
  | "web"
  | "dev"
  | "visual"
  | "memory"
  | "admin";

/** Lifecycle. Only `available` commands are shown as runnable. */
export type CommandStatus = "available" | "unavailable" | "deprecated" | "experimental";

export type CommandHandlerType =
  | "native"
  | "skill"
  | "skills"
  | "task"
  | "workflow"
  | "runtime"
  | "profile"
  /** Runs as a normal agent turn after the query is rewritten (e.g. `/skill`). */
  | "agent"
  | "unsupported";

export type CommandExecutionMode = "sync" | "async";
export type CommandRisk = "none" | "low" | "medium" | "high" | "critical";
export type CommandApproval = "none" | "operator" | "user";
export type CommandOutputType = "markdown" | "response" | "table" | "json";

export interface CommandArgSpec {
  /** Argument name (used as the bound key). */
  name: string;
  description: string;
  required?: boolean;
  type?: "string" | "number" | "boolean" | "enum";
  /** Allowed values for `type: "enum"`. */
  values?: readonly string[];
  default?: string | number | boolean;
  /** The arg takes the remaining positionals (an array). */
  variadic?: boolean;
  /** Id of a completion provider (client-side hint only). */
  completion?: string;
}

export interface CommandFlagSpec {
  name: string;
  description: string;
  type?: "boolean" | "string" | "number";
  values?: readonly string[];
  default?: string | number | boolean;
  /** A single-dash alias, e.g. `-d` for `--depth`. */
  alias?: string;
}

export interface CommandPermissionSpec {
  /** Capability names required for a USER invocation (advisory; enforced in Python). */
  user?: readonly string[];
  /** Capability names required for an AUTONOMOUS agent invocation. */
  agent?: readonly string[];
  approval?: CommandApproval;
}

export interface CommandHandlerSpec {
  type: CommandHandlerType;
  /** Dispatch target the router resolves, e.g. `skills.list`, `skill.execute`. */
  target: string;
}

export interface CommandOutputSpec {
  type: CommandOutputType;
  summary: string;
}

export interface CommandDeprecation {
  since: string;
  alternative?: string;
  note: string;
}

/** The forced autonomy profile for a chat profile command (e.g. `/eclipsesdk`). */
export interface ChatCommandProfile {
  autonomy: "plan_only" | "edit_verify";
  analysisEnabled: boolean;
}

export interface CommandSpec {
  /** Stable id, namespaced (`skills.list`). Never changes; used by saved workflows. */
  id: string;
  /** Canonical name, no leading slash, lowercase. */
  name: string;
  aliases: readonly string[];
  summary: string;
  description: string;
  category: CommandCategory;
  tags: readonly string[];
  /** Command version (semver). */
  version: string;
  status: CommandStatus;
  args: readonly CommandArgSpec[];
  flags: readonly CommandFlagSpec[];
  /** Unknown `--key value` flags are accepted and passed through (e.g. skill inputs). */
  passThroughFlags?: boolean;
  handler: CommandHandlerSpec;
  permissions: CommandPermissionSpec;
  risk: CommandRisk;
  executionMode: CommandExecutionMode;
  timeoutMs?: number;
  retries?: number;
  idempotent?: boolean;
  output: CommandOutputSpec;
  examples: readonly string[];
  deprecation?: CommandDeprecation | null;
  /** Present only for chat profile commands; forces a run profile. */
  profile?: ChatCommandProfile;
  /** Optional i18n key for the one-line palette summary. */
  summaryKey?: TranslationKey;
  /** Why an `unavailable` command cannot run yet (shown to the user, never hidden). */
  unavailabilityReason?: string;
}

const V = "1.0.0";

// ─── Implemented commands ────────────────────────────────────────────────────

const HELP: CommandSpec = {
  id: "runtime.help",
  name: "help",
  aliases: ["?", "commands"],
  summary: "List the available slash commands.",
  description:
    "Show the canonical command catalog grouped by category, with each command's arguments and availability.",
  category: "runtime",
  tags: ["core", "discovery"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "native", target: "native.help" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  idempotent: true,
  output: { type: "response", summary: "A grouped command catalog." },
  examples: ["/help"],
};

const STATUS: CommandSpec = {
  id: "runtime.status",
  name: "status",
  aliases: ["health"],
  summary: "Report runtime health and what is loaded.",
  description:
    "Report whether the Python agent runtime is reachable and, when it is, the tool and provider counts it advertises.",
  category: "runtime",
  tags: ["core", "health"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "runtime", target: "runtime.status" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  timeoutMs: 10_000,
  idempotent: true,
  output: { type: "response", summary: "A health card." },
  examples: ["/status"],
};

const TASKS: CommandSpec = {
  id: "runtime.tasks",
  name: "tasks",
  aliases: ["plans"],
  summary: "List durable tasks and plans.",
  description:
    "List the durable plans and tasks owned by the Python task/plan system, optionally filtered to one plan.",
  category: "runtime",
  tags: ["core", "tasks"],
  version: V,
  status: "available",
  args: [{ name: "planId", description: "Only show tasks for this plan id.", required: false }],
  flags: [
    { name: "status", description: "Filter by task status.", type: "string" },
  ],
  handler: { type: "native", target: "native.tasks.list" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 45_000,
  idempotent: true,
  output: { type: "response", summary: "A table of plans and tasks." },
  examples: ["/tasks", "/tasks plan_123", "/tasks --status RUNNING"],
};

const WORKFLOWS: CommandSpec = {
  id: "runtime.workflows",
  name: "workflows",
  aliases: ["workflow"],
  summary: "List saved workflows.",
  description: "List the workflow definitions stored by the Python workflow engine.",
  category: "runtime",
  tags: ["core", "workflows"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "native", target: "native.workflows.list" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 45_000,
  idempotent: true,
  output: { type: "response", summary: "A table of workflows." },
  examples: ["/workflows"],
};

const MODELS: CommandSpec = {
  id: "admin.models",
  name: "models",
  aliases: ["providers"],
  summary: "List configured model providers.",
  description: "List the model providers the runtime reports as configured, with their declared models.",
  category: "admin",
  tags: ["models", "providers"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "runtime", target: "runtime.models" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  timeoutMs: 15_000,
  idempotent: true,
  output: { type: "response", summary: "A table of providers." },
  examples: ["/models"],
};

const AGENTS: CommandSpec = {
  id: "runtime.agents",
  name: "agents",
  aliases: [],
  summary: "List agent presets.",
  description: "List the agent presets the runtime exposes and mark the default agent.",
  category: "runtime",
  tags: ["agents"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "runtime", target: "runtime.agents" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  timeoutMs: 15_000,
  idempotent: true,
  output: { type: "response", summary: "A list of agent presets." },
  examples: ["/agents"],
};

// ── Skill family (Phase 4) — the authoritative skill subsystem ───────────────

const SKILLS: CommandSpec = {
  id: "skills.list",
  name: "skills",
  aliases: [],
  summary: "List, search, inspect, test, and run skills.",
  description:
    "The skill catalog interface. `list` shows installed skills; `search` filters by keyword; " +
    "`category` filters by category; `show` inspects one skill; `run` executes one; `test` runs its " +
    "evaluation suite; `validate` checks its preflight (dependencies, tools, permissions).",
  category: "skills",
  tags: ["skills", "discovery"],
  version: V,
  status: "available",
  args: [
    {
      name: "action",
      description: "What to do.",
      type: "enum",
      values: ["list", "search", "category", "show", "run", "test", "validate"],
      default: "list",
    },
    {
      name: "subject",
      description: "The search keyword, category, or skill id the action applies to.",
      variadic: true,
    },
  ],
  flags: [
    { name: "status", description: "Filter by lifecycle status.", type: "string" },
  ],
  handler: { type: "skills", target: "skills.catalog" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 240_000,
  idempotent: true,
  output: { type: "response", summary: "A skill table, a single skill's detail, or an execution result." },
  examples: [
    "/skills",
    "/skills search crypto",
    "/skills category research",
    "/skills show crypto-onchain-research",
    "/skills run crypto-onchain-research",
    "/skills test crypto-onchain-research",
    "/skills validate crypto-onchain-research",
  ],
};

const SKILL: CommandSpec = {
  id: "skill.author",
  name: "skill",
  aliases: [],
  summary: "Create a new reusable Eclipse skill.",
  description:
    "Tell Eclipse to author a new reusable skill from your description. The chatbot generates the " +
    "procedure and metadata, saves it in the Skills library (so it appears on the Skills page where you " +
    "can view, edit, enable, or run it), and creation is approval-gated. This is a normal chat turn: " +
    "describe what the skill should do. To RUN an existing skill, use `/skills run <id>`.",
  category: "skills",
  tags: ["skills", "authoring"],
  version: V,
  status: "available",
  args: [
    { name: "name", description: "A short name for the new skill.", required: false },
    { name: "description", description: "What the skill should do.", variadic: true },
  ],
  flags: [
    { name: "category", description: "Skill category.", type: "string", values: ["research", "quality", "finance", "system"] },
  ],
  handler: { type: "agent", target: "agent.skill.author" },
  permissions: { approval: "user" },
  risk: "medium",
  executionMode: "async",
  output: { type: "markdown", summary: "The chatbot authors the skill and confirms the created id." },
  examples: [
    "/skill crypto-onchain-research Research tokenomics and on-chain activity for a token",
    "/skill risk-review Review a portfolio for concentration risk and flag the worst offenders",
  ],
};

const SKILL_EXPLAIN: CommandSpec = {
  id: "skill.explain",
  name: "skill-explain",
  aliases: ["skill-show"],
  summary: "Explain what a skill does.",
  description:
    "Explain a skill's purpose, inputs and outputs, required tools, permissions, dependencies, limits, and validation status.",
  category: "skills",
  tags: ["skills", "docs"],
  version: V,
  status: "available",
  args: [{ name: "skillId", description: "The skill id to explain.", required: true, completion: "skills" }],
  flags: [],
  handler: { type: "skill", target: "skill.explain" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A skill detail card." },
  examples: ["/skill-explain crypto-onchain-research"],
};

const SKILL_TEST: CommandSpec = {
  id: "skill.test",
  name: "skill-test",
  aliases: [],
  summary: "Run a skill's evaluation suite.",
  description:
    "Run the deterministic evaluation suite for a skill and report each dimension's status. A skill is never " +
    "reported validated merely because its files exist.",
  category: "skills",
  tags: ["skills", "evaluation"],
  version: V,
  status: "available",
  args: [{ name: "skillId", description: "The skill id to evaluate.", required: true, completion: "skills" }],
  flags: [
    { name: "suite", description: "Which suite to run.", type: "string" },
    { name: "regression", description: "Also run the regression suite.", type: "boolean" },
  ],
  handler: { type: "skill", target: "skill.test" },
  permissions: { approval: "operator" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 120_000,
  idempotent: false,
  output: { type: "response", summary: "Per-dimension evaluation results." },
  examples: ["/skill-test crypto-onchain-research", "/skill-test crypto-onchain-research --regression"],
};

const SKILL_ENABLE: CommandSpec = {
  id: "skill.enable",
  name: "skill-enable",
  aliases: [],
  summary: "Enable a skill.",
  description: "Enable a skill so it becomes executable and discoverable by the planner. Operator-gated.",
  category: "skills",
  tags: ["skills", "lifecycle"],
  version: V,
  status: "available",
  args: [{ name: "skillId", description: "The skill id to enable.", required: true, completion: "skills" }],
  flags: [{ name: "version", description: "Pin a specific version.", type: "string" }],
  handler: { type: "skill", target: "skill.enable" },
  permissions: { approval: "operator" },
  risk: "medium",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "markdown", summary: "A confirmation." },
  examples: ["/skill-enable crypto-onchain-research"],
};

const SKILL_DISABLE: CommandSpec = {
  id: "skill.disable",
  name: "skill-disable",
  aliases: [],
  summary: "Disable a skill.",
  description:
    "Disable a skill so it no longer accepts NEW executions. Already-running executions follow the task " +
    "lifecycle and cancellation policy.",
  category: "skills",
  tags: ["skills", "lifecycle"],
  version: V,
  status: "available",
  args: [{ name: "skillId", description: "The skill id to disable.", required: true, completion: "skills" }],
  flags: [{ name: "version", description: "Pin a specific version.", type: "string" }],
  handler: { type: "skill", target: "skill.disable" },
  permissions: { approval: "operator" },
  risk: "medium",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "markdown", summary: "A confirmation." },
  examples: ["/skill-disable crypto-onchain-research"],
};

const SKILL_CREATE: CommandSpec = {
  id: "skill.create",
  name: "skill-create",
  aliases: [],
  summary: "Create a new skill from a task or objective.",
  description:
    "Create an inert skill draft through the existing learning engine: from a completed task `--from-task`, " +
    "from a saved workflow `--from-workflow`, or from an objective/instructions `--objective`. A draft is never " +
    "auto-enabled or trusted.",
  category: "skills",
  tags: ["skills", "learning"],
  version: V,
  status: "available",
  args: [{ name: "name", description: "A short name for the new skill (optional when a source id is given).", required: false }],
  flags: [
    { name: "from-task", description: "Learn from a completed task/run id.", type: "string" },
    { name: "from-workflow", description: "Learn from a saved workflow id.", type: "string" },
    { name: "objective", description: "What the skill should achieve.", type: "string" },
    { name: "category", description: "Skill category.", type: "string", values: ["research", "quality", "finance", "system"] },
  ],
  handler: { type: "skill", target: "skill.create" },
  permissions: { approval: "operator" },
  risk: "medium",
  executionMode: "sync",
  timeoutMs: 120_000,
  idempotent: false,
  output: { type: "response", summary: "The created draft's id, version, and status." },
  examples: [
    "/skill-create crypto-onchain-research",
    "/skill-create --from-task task_123",
    "/skill-create --from-workflow crypto-research",
    "/skill-create risk-review --objective 'Review a portfolio for concentration risk'",
  ],
};

const ANATOMY: CommandSpec = {
  id: "visual.anatomy",
  name: "anatomy",
  aliases: ["visualize", "mechanism"],
  summary: "Explain a concept as an interactive isometric figure.",
  description:
    "Turn a \"how does X work\" question into an interactive isometric mechanism figure — a working model with " +
    "labelled parts, connections and step-through stages, rendered inline in chat as an `anatomy` block. The agent " +
    "authors the declarative scene; it never writes SVG or code.",
  category: "visual",
  tags: ["visual", "explanation", "anatomy", "mechanism", "diagram"],
  version: V,
  status: "available",
  args: [{ name: "subject", description: "The concept, system or mechanism to illustrate.", variadic: true }],
  flags: [
    { name: "audience", description: "Who the explanation is for.", type: "string", values: ["beginner", "intermediate", "expert"] },
    { name: "animated", description: "Break the mechanism into step-through stages.", type: "boolean" },
  ],
  handler: { type: "agent", target: "agent.anatomy" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  output: { type: "response", summary: "An interactive anatomy figure plus a short explanation." },
  examples: [
    "/anatomy how a cache works",
    "/anatomy the BlackEclipse data path --animated",
    "/anatomy how a transformer attends --audience expert",
  ],
};

const ECLIPSESDK: CommandSpec = {
  id: "code.eclipsesdk",
  name: "eclipsesdk",
  aliases: ["esdk"],
  summaryKey: "code.command.eclipsesdk",
  summary: "Build or change something inside Eclipse.",
  description:
    "Force the chat code profile (`edit_verify`: read + write + execute, no external action) and the analysis " +
    "sandbox so a self-edit request is served by the code capability instead of the finance surface.",
  category: "dev",
  tags: ["code", "self-edit"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "profile", target: "profile.eclipsesdk" },
  permissions: { approval: "none" },
  risk: "medium",
  executionMode: "sync",
  output: { type: "markdown", summary: "A normal agent turn under the code profile." },
  examples: ["/eclipsesdk create a page for my watchlist"],
  profile: { autonomy: "edit_verify", analysisEnabled: true },
};

const TOOLS: CommandSpec = {
  id: "admin.tools",
  name: "tools",
  aliases: [],
  summary: "List the runtime's registered tools.",
  description: "List the tools registered on the runtime's single tool registry and how many there are.",
  category: "admin",
  tags: ["tools", "discovery"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "runtime", target: "runtime.tools" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  timeoutMs: 15_000,
  idempotent: true,
  output: { type: "response", summary: "A table of registered tools." },
  examples: ["/tools"],
};

const USAGE: CommandSpec = {
  id: "admin.usage",
  name: "usage",
  aliases: ["cost"],
  summary: "Show token usage for the last 30 days.",
  description:
    "Summarize run/token/tool usage from real run records. Estimated, never presented as billed cost.",
  category: "admin",
  tags: ["usage", "cost"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "runtime", target: "admin.usage" },
  permissions: { approval: "none" },
  risk: "none",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A usage summary." },
  examples: ["/usage"],
};

const MARKET: CommandSpec = {
  id: "markets.market",
  name: "market",
  aliases: [],
  summary: "Show market-data gateway status.",
  description: "Show the market data gateway's providers, their configuration/implementation state, and cache health.",
  category: "markets",
  tags: ["markets", "jdds"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "native", target: "markets.market" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A provider/health table." },
  examples: ["/market"],
};

const PORTFOLIO: CommandSpec = {
  id: "portfolio.portfolio",
  name: "portfolio",
  aliases: ["portfolios"],
  summary: "List portfolios.",
  description: "List the real portfolios recorded by the Portfolio Accounting Engine (never fabricated or hypothetical).",
  category: "portfolio",
  tags: ["portfolio"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "native", target: "portfolio.portfolio" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A table of portfolios." },
  examples: ["/portfolio"],
};

const MEMORY: CommandSpec = {
  id: "memory.memory",
  name: "memory",
  aliases: [],
  summary: "Show Eclipse memory overview and recent memories.",
  description: "Show the Eclipse memory overview and the most recent memory records from the dedicated memory database.",
  category: "memory",
  tags: ["memory"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "native", target: "memory.memory" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A memory overview and recent records." },
  examples: ["/memory"],
};

const MCP: CommandSpec = {
  id: "admin.mcp",
  name: "mcp",
  aliases: [],
  summary: "List configured MCP servers.",
  description: "List the configured Model Context Protocol servers and their trust/enabled state (env values are never exposed).",
  category: "admin",
  tags: ["mcp", "tools"],
  version: V,
  status: "available",
  args: [],
  flags: [],
  handler: { type: "native", target: "admin.mcp" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A table of MCP servers." },
  examples: ["/mcp"],
};

// ─── Research, markets, quant, dev commands ──────────────────────────────────

const QUOTE: CommandSpec = {
  id: "markets.quote",
  name: "quote",
  aliases: ["quotes"],
  summary: "Get quotes for one or more symbols.",
  description:
    "Resolve symbols across all markets in JDdS and return the live/delayed/stale price with its real freshness. A symbol that does not resolve is reported as unavailable, never invented.",
  category: "markets",
  tags: ["markets", "quote", "jdds"],
  version: V,
  status: "available",
  args: [{ name: "symbols", description: "One or more symbols (e.g. AAPL BTC OGDC).", variadic: true }],
  flags: [],
  handler: { type: "native", target: "markets.quote" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 30_000,
  idempotent: true,
  output: { type: "response", summary: "A quote table with freshness." },
  examples: ["/quote AAPL", "/quote AAPL BTC OGDC"],
};

const RESEARCH: CommandSpec = {
  id: "research.run",
  name: "research",
  aliases: [],
  summary: "Answer a question with cited web research.",
  description:
    "Run the evidence-driven web research engine and return its synthesized answer with sources. Citations are required by default.",
  category: "research",
  tags: ["research", "web", "evidence"],
  version: V,
  status: "available",
  args: [{ name: "question", description: "What to research.", variadic: true }],
  flags: [{ name: "depth", description: "Research depth.", type: "string", values: ["quick", "standard", "deep"] }],
  handler: { type: "native", target: "research.run" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 900_000,
  output: { type: "response", summary: "An answer with cited sources." },
  examples: ['/research "NVIDIA competitive position"', "/research impact of rate cuts on banks --depth deep"],
};

const DEEP_RESEARCH: CommandSpec = {
  id: "research.deep",
  name: "deep-research",
  aliases: ["deep"],
  summary: "Run multi-pass, cross-validated research.",
  description:
    "Run the web research engine at DEPTH with cross-validation required, so conflicting sources are surfaced rather than smoothed over.",
  category: "research",
  tags: ["research", "web", "deep"],
  version: V,
  status: "available",
  args: [{ name: "question", description: "What to research in depth.", variadic: true }],
  flags: [],
  handler: { type: "native", target: "research.run" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 900_000,
  output: { type: "response", summary: "An answer with cross-validated sources." },
  examples: ['/deep-research "Is the semiconductor cycle turning?"'],
};

const WEB: CommandSpec = {
  id: "research.web",
  name: "web",
  aliases: ["browse"],
  summary: "Research and summarize a URL or query.",
  description: "Run a bounded web research pass over a URL or query and summarize the findings with sources.",
  category: "web",
  tags: ["web", "research"],
  version: V,
  status: "available",
  args: [{ name: "target", description: "A URL or a query.", variadic: true }],
  flags: [],
  handler: { type: "native", target: "research.web" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 120_000,
  output: { type: "response", summary: "A summary with sources." },
  examples: ["/web https://example.com/article", "/web latest AI chip announcements"],
};

const READ: CommandSpec = {
  id: "research.read",
  name: "read",
  aliases: ["summarize"],
  summary: "Extract and summarize a document.",
  description: "Fetch a URL/document and extract its content into a summary with the source it came from.",
  category: "web",
  tags: ["documents", "extract"],
  version: V,
  status: "available",
  args: [{ name: "target", description: "A URL or document reference.", variadic: true }],
  flags: [],
  handler: { type: "native", target: "research.read" },
  permissions: { approval: "none" },
  risk: "low",
  executionMode: "sync",
  timeoutMs: 120_000,
  output: { type: "response", summary: "A document summary with its source." },
  examples: ["/read https://example.com/report.pdf"],
};

const BACKTEST: CommandSpec = {
  id: "quant.backtest",
  name: "backtest",
  aliases: [],
  summary: "List strategies or backtest one by id.",
  description:
    "With no argument, list the saved strategies. With a strategy id, run the quant engine's backtest and report its metrics. Never invents a result when no strategy matches.",
  category: "quant",
  tags: ["quant", "backtest"],
  version: V,
  status: "available",
  args: [{ name: "strategyId", description: "A saved strategy id to backtest (optional).", required: false }],
  flags: [],
  handler: { type: "native", target: "quant.backtest" },
  permissions: { approval: "none" },
  risk: "medium",
  executionMode: "sync",
  timeoutMs: 300_000,
  output: { type: "response", summary: "A strategy list, or backtest metrics." },
  examples: ["/backtest", "/backtest momentum_v1"],
};

const CODE: CommandSpec = {
  id: "code.task",
  name: "code",
  aliases: [],
  summary: "Start a coding task.",
  description:
    "Create a code task for the coding agent (autonomy defaults to plan_only; pass `--autonomy edit_verify` to edit) in a disposable workspace; track it in the Code screen. Operator-gated.",
  category: "dev",
  tags: ["dev", "code"],
  version: V,
  status: "available",
  args: [{ name: "task", description: "What to build or change.", variadic: true }],
  flags: [{ name: "autonomy", description: "Autonomy profile.", type: "string", values: ["plan_only", "edit_verify"] }],
  handler: { type: "native", target: "code.task" },
  permissions: { approval: "operator" },
  risk: "high",
  executionMode: "async",
  timeoutMs: 300_000,
  output: { type: "response", summary: "The created task id and status." },
  examples: ["/code add a loading state to the watchlist widget"],
};

const TERMINAL: CommandSpec = {
  id: "runtime.terminal",
  name: "terminal",
  aliases: ["run", "sh"],
  summary: "Run a shell command.",
  description:
    "Execute a shell command through the terminal subsystem (operator-gated, effect-gated) and show its output. Never run untrusted content as a command.",
  category: "dev",
  tags: ["dev", "terminal", "shell"],
  version: V,
  status: "available",
  args: [{ name: "command", description: "The command to run.", variadic: true }],
  flags: [],
  handler: { type: "native", target: "runtime.terminal" },
  permissions: { approval: "operator" },
  risk: "high",
  executionMode: "sync",
  timeoutMs: 900_000,
  output: { type: "response", summary: "stdout/stderr and the exit code." },
  examples: ["/terminal ls -la", "/run git status"],
};

export const COMMAND_REGISTRY: readonly CommandSpec[] = [
  HELP,
  STATUS,
  SKILLS,
  SKILL,
  SKILL_EXPLAIN,
  SKILL_TEST,
  SKILL_ENABLE,
  SKILL_DISABLE,
  SKILL_CREATE,
  TASKS,
  WORKFLOWS,
  AGENTS,
  MODELS,
  TOOLS,
  USAGE,
  MARKET,
  QUOTE,
  PORTFOLIO,
  MEMORY,
  MCP,
  RESEARCH,
  DEEP_RESEARCH,
  WEB,
  READ,
  BACKTEST,
  CODE,
  TERMINAL,
  ANATOMY,
  ECLIPSESDK,
];

// ─── Pure queries ────────────────────────────────────────────────────────────

function normalizeToken(name: string): string {
  return (name ?? "").replace(/^\//, "").toLowerCase();
}

/** True when a command has a real handler and may be offered as runnable. */
export function isCommandAvailable(spec: CommandSpec): boolean {
  return spec.status === "available" && spec.handler.type !== "unsupported";
}

/** Resolve a command by canonical name or alias (case-insensitive, leading slash optional). */
export function resolveCommand(name: string): CommandSpec | undefined {
  const token = normalizeToken(name);
  return COMMAND_REGISTRY.find((c) => c.name === token || c.aliases.includes(token));
}

export function allCommands(): readonly CommandSpec[] {
  return COMMAND_REGISTRY;
}

export interface CommandListFilter {
  category?: CommandCategory;
  status?: CommandStatus;
  /** When true, include unavailable commands (default: true). */
  includeUnavailable?: boolean;
}

export function listCommands(filter: CommandListFilter = {}): CommandSpec[] {
  return COMMAND_REGISTRY.filter((c) => {
    if (filter.category && c.category !== filter.category) return false;
    if (filter.status && c.status !== filter.status) return false;
    if (filter.includeUnavailable === false && !isCommandAvailable(c)) return false;
    return true;
  });
}

function isSubsequence(needle: string, haystack: string): boolean {
  let i = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) i += 1;
    if (i === needle.length) return true;
  }
  return needle.length === 0;
}

/** Score a command against a query. Higher is better; 0 = no match. */
function scoreCommand(spec: CommandSpec, query: string): number {
  if (!query) return 1;
  const name = spec.name.toLowerCase();
  if (name === query) return 1000;
  if (spec.aliases.some((a) => a.toLowerCase() === query)) return 900;
  if (name.startsWith(query)) return 700 - name.length;
  if (spec.aliases.some((a) => a.toLowerCase().startsWith(query))) return 600;
  if (name.includes(query)) return 400 - name.length;
  if (spec.aliases.some((a) => a.toLowerCase().includes(query))) return 300;
  if (spec.tags.some((t) => t.toLowerCase().includes(query))) return 250;
  if (spec.summary.toLowerCase().includes(query)) return 150;
  if (isSubsequence(query, name)) return 100;
  return 0;
}

/**
 * Search commands by prefix, alias, tag, or fuzzy name match. Deterministic
 * (stable ordering) so autocomplete does not reorder between keystrokes.
 */
export function searchCommands(query: string, filter: CommandListFilter = {}): CommandSpec[] {
  const q = (query ?? "").trim().toLowerCase();
  const pool = listCommands(filter);
  if (!q) {
    return pool.slice().sort((a, b) => a.name.localeCompare(b.name));
  }
  return pool
    .map((spec) => ({ spec, score: scoreCommand(spec, q) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => (b.score - a.score) || a.spec.name.localeCompare(b.spec.name))
    .map((x) => x.spec);
}

export interface RegistryConflict {
  token: string;
  ids: string[];
}

/**
 * Detect duplicate names/aliases across the registry. Duplicates are also
 * refused at resolve time (first-wins), but this makes them visible to tests/CI.
 */
export function detectRegistryConflicts(): RegistryConflict[] {
  const claims = new Map<string, string[]>();
  const claim = (token: string, id: string) => {
    const list = claims.get(token) ?? [];
    list.push(id);
    claims.set(token, list);
  };
  for (const spec of COMMAND_REGISTRY) {
    claim(spec.name, spec.id);
    for (const alias of spec.aliases) claim(alias, spec.id);
  }
  return [...claims.entries()]
    .filter(([, ids]) => new Set(ids).size > 1)
    .map(([token, ids]) => ({ token, ids: [...new Set(ids)] }));
}

/** A compact one-line argument hint for the palette, e.g. `<action> [subject]`. */
export function commandArgHint(spec: CommandSpec): string {
  const parts: string[] = [];
  for (const arg of spec.args) {
    const inner = arg.variadic ? `${arg.name}…` : arg.name;
    parts.push(arg.required ? `<${inner}>` : `[${inner}]`);
  }
  for (const flag of spec.flags) {
    parts.push(flag.type === "boolean" ? `[--${flag.name}]` : `[--${flag.name} <${flag.type ?? "string"}>]`);
  }
  if (spec.passThroughFlags) parts.push("[--<key> <value>]…");
  return parts.join(" ");
}

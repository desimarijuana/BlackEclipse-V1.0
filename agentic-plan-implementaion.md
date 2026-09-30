# BlackEclipse — The Financial Agentic Harness

> Reference copy of the original agentic harness implementation plan. This is
> a planning document, not a statement of the current implementation. For the
> current architecture and code map, see `Black-Eclipse-site/docs/harness/`
> and `Black-Eclipse-site/docs/NAVIGATION.md`.

Bismillah. Let's build something serious.
You don't want to add a chatbot to BlackEclipse. You want to build a financial AI operating system—a harness that can research, reason, use tools, write code, create specialized agents, remember what it learns, execute repeatable workflows, and help investors make better-informed decisions.
The difference is enormous.
A normal finance application:
User asks a question → AI responds → User does the work.

A financial harness:
User defines a goal → Harness plans the work → Selects skills and agents → Uses financial data and tools → Researches and verifies → Produces artifacts → Remembers relevant findings → Evaluates results → Improves future execution.

That is the direction we should take with BlackEclipse.
Your existing Eclipse application already has important foundations: market discovery, portfolios, trading journal, chatbot, data orchestration through JDdS, and a financial terminal interface. The next step is to make those capabilities usable by autonomous and semi-autonomous agents through a unified harness.
I'll lay this out as an architecture and implementation blueprint, including MCP, skills, agent workflows, memory, code generation, research, security, evaluation, and the path to a genuinely competitive open-source system.
One important distinction: nobody can honestly guarantee that an application will be the best in the world. We can, however, design Eclipse around ambitious technical goals, measurable benchmarks, excellent financial workflows, and an architecture that can keep improving.

1. First, define what we are actually building
The vision

Open source
Agentic
Finance-first

BlackEclipse Financial Harness
An AI-native financial orchestration layer for research, analysis, automation, and investor workflows.

The harness should be capable of the following:
Capability	What Eclipse should do
Research	Investigate companies, markets, sectors, macroeconomics, news, and investment themes
Reasoning	Break complex financial questions into structured tasks and hypotheses
MCP	Connect external tools, financial data sources, code environments, and services
Skills	Package reusable instructions, procedures, tool permissions, and domain expertise
Agents	Create specialized research, coding, risk, portfolio, and data agents
Workflows	Turn skills and agents into repeatable, sequential, parallel, or event-driven processes
Memory	Remember preferences, research findings, decisions, and reusable knowledge with provenance
Code generation	Build tools, data pipelines, indicators, backtests, and integrations in a controlled environment
Evaluation	Test factuality, data quality, financial calculations, tool execution, and research completeness
Investor UX	Present results through terminal views, reports, charts, tables, and actionable next steps
The central principle:
Eclipse should not merely answer financial questions. It should be able to perform the work required to investigate and solve them.


2. The architecture: one harness, many capabilities
Before writing agents, we need to design the core system correctly.
A common mistake is to create ten agents, connect them to an LLM, and call it an agentic platform. That creates a collection of prompts—not a reliable harness.
We need a clear separation between the orchestration layer, execution layer, financial domain services, and user interface.
High-level architecture
BlackEclipse
Financial operating environment

User Interface / Command Center
Chat · Research workspace · Agent builder · Workflow builder · Terminal · Reports


Harness Runtime
Planner · Router · Scheduler · Context manager · Approval gates · Run state


Agent & Skill System
Skills · Agent profiles · Skill composition · Workflow definitions


Tool Runtime
MCP · Internal tools · Sandboxes · Permissions · Tool registry




Financial Intelligence Layer
JDdS · Market data · Fundamental data · News · Macro · Portfolio · Research artifacts


Persistence & Governance
PostgreSQL / SQLite where appropriate · Object storage · Memory · Audit logs · Evaluations


This is a logical architecture, not a requirement that everything become a separate microservice. For the first release, a modular monolith is likely more practical.

3. The most important design decision: the Harness Kernel
Everything depends on the kernel.
The kernel is the runtime that coordinates an agent's work. It must not be tied to one specific model provider or one hardcoded research flow.
Think of it as the equivalent of an operating system's process manager, but for AI tasks.
3.1 What the kernel manages
The kernel should own:
1. Run creation — Start an agent or workflow run.
2. Task planning — Determine what work needs to be done.
3. Execution — Run model calls, skills, tools, and sub-agents.
4. Context management — Provide the right information at each step.
5. State — Track progress, outputs, failures, and resumability.
6. Permissions — Decide which tools and actions are allowed.
7. Approvals — Pause for user authorization where required.
8. Cancellation — Stop a run and its active work.
9. Retries — Retry transient failures without blindly duplicating side effects.
10. Observability — Record events, latency, token usage, errors, and provenance.
11. Evaluation — Check whether the result meets the task's requirements.
12. Artifact creation — Save reports, code, datasets, and structured outputs.
What the kernel should not do
Avoid putting all business logic in a giant agent.ts file.
The kernel should not directly implement every financial calculation, scrape every website, or contain every research instruction. Those belong in modular services, tools, and skills.
The kernel orchestrates. Domain services execute specialized work.

4. The execution model: how a request moves through Eclipse
Let's use a realistic user request:
"Research whether semiconductor companies are benefiting from AI infrastructure spending. Compare three companies, examine valuation, growth, risks, and produce a report."

A strong harness should process this through an explicit run lifecycle.
Research Run

1. Intake
   Interpret the user's goal, scope, geography, time period, and desired output.
2. Plan
   Create tasks: identify companies, retrieve financial data, gather industry evidence, analyze valuation, identify risks, and synthesize.
3. Resolve skills
   Select relevant skills such as company research, fundamental analysis, source verification, and report generation.
4. Execute tools
   Retrieve market data, financial statements, filings, news, and macroeconomic information.
5. Validate
   Check timestamps, units, currencies, missing data, source reliability, and calculation consistency.
6. Analyze
   Use the appropriate financial analysis tools and model reasoning, with source-linked evidence.
7. Synthesize
   Create a report with methodology, assumptions, evidence, uncertainty, and risks.
8. Evaluate and save
   Run quality checks, store the research artifact, and preserve relevant findings with provenance.

The UI should display the run as it progresses, rather than showing only a spinner until a final answer appears.
Users should be able to see:
- Current task.
- Completed tasks.
- Tool calls.
- Sources found.
- Errors and retries.
- Pending approval requests.
- Generated artifacts.
- Cost and execution time, when available.
- The final report and evidence trail.
This makes the system inspectable and much easier to debug.

5. MCP: the tool ecosystem of Eclipse
MCP (Model Context Protocol) should be a major integration standard in Eclipse, not the entire architecture.
MCP provides a standardized way for AI applications to discover and interact with tools and other contextual resources. The harness still needs its own execution policy, permissions, financial data layer, and lifecycle management.
We should support MCP both as a client and, where useful, as a server.
5.1 MCP client
Eclipse should be able to connect to external MCP servers.
Examples:
- Financial data MCP server.
- Web research MCP server.
- Filesystem MCP server.
- Git repository MCP server.
- Database MCP server.
- Python execution MCP server.
- Documentation and knowledge MCP server.
- User-installed third-party MCP servers.
MCP is a user-directed extension surface. A user may connect financial MCP servers and use them for any finance workflow they choose; Eclipse must not impose its own financial-task allowlist or require external MCP data to pass through JDdS or Eclipse's native research verifier. Eclipse still makes the source and execution boundary visible: externally supplied results are attributed to their MCP server and tool, and are not described as Eclipse-verified unless a separate Eclipse verification flow actually verifies them.

Every connection still needs capability discovery, user-controlled tool selection, credential isolation, input/output validation, resource bounds, and execution boundaries. These protections govern how a server is connected and called; they do not limit the user's financial use case. Tool effects must be declared and visible. Read-only tools can be enabled directly; tools that write data, move assets, send messages, or otherwise cause external effects require an explicit user-controlled permission/approval path before invocation. A server's own description or result cannot grant itself permission.
5.2 Eclipse MCP servers
We should expose Eclipse capabilities as MCP tools when that makes sense.
Potential servers:

Market Intelligence MCP
Market quotes, historical data, corporate fundamentals, technical indicators, and data-quality metadata.




Research MCP
Search research artifacts, source documents, evidence records, and prior analysis.




Portfolio MCP
Read holdings, analyze exposure, calculate metrics, and create draft portfolio reports. Write operations require explicit permission.




Development MCP
Repository inspection, test execution, code generation tasks, and controlled project operations.



These servers can be used by Eclipse's own agents and, optionally, by compatible external AI clients.
5.3 Internal tools versus MCP tools
Not every internal function needs to become an MCP server.
Use internal tools for:
- Low-latency application operations.
- Direct access to JDdS.
- Database transactions.
- Internal orchestration state.
- Trusted financial calculations.
- UI-specific actions.
Use MCP for:
- External interoperability.
- User-installed servers.
- Standardized tool discovery.
- Separately deployed tool services.
- Sharing Eclipse capabilities with other MCP-compatible clients.
Build one internal tool contract and, where appropriate, expose it through MCP adapters. That avoids implementing the same logic twice.

**Financial data boundary.** JDdS is one configured source, not the authority or mandatory path for every financial question. Its contents may be stale, incomplete, or constrained by the APIs configured by the user. The harness should select and, where useful, compare available JDdS, built-in provider, web/official-source, and user-enabled MCP evidence based on the request, observed freshness, coverage, and provenance. User-connected MCP tools may also be used directly for any financial workflow the user chooses; they need not be forced through the native retrieval or research gate. Preserve source identity and timestamps, surface conflicts and stale/missing coverage, and never describe external data as independently verified by Eclipse unless an explicit verification path actually checked it. A user may choose a source or direct MCP workflow; source selection should be visible and controllable.





MCP implementation requirements
As of September 2026, the MCP specification has evolved beyond the earlier tool-only model. The July 28, 2026 specification includes protocol versioning, tools, resources, prompts, authorization, and newer interaction patterns. Design your adapter against the version you intend to support, and keep compatibility explicit rather than assuming all servers implement the same capabilities. 

Model Context Protocol Blog
+2




Our MCP layer should include:
- Server registration and connection management.
- Transport support appropriate to the server.
- Capability discovery.
- Tool schema normalization.
- Authentication and credential isolation.
- Permission mapping.
- Timeouts, cancellation, and retry policy.
- Tool output validation.
- Audit logging.
- User approval for sensitive operations.
- Version compatibility and graceful degradation.
- User-managed enabled/disabled state and per-tool selection.
- Per-server process, network, concurrency, time, and response-size bounds.
- Source attribution for every MCP result and visible run-level tool trace.
Never allow an arbitrary MCP server to inherit all of Eclipse's credentials or unrestricted filesystem access. Do not silently narrow finance use cases or rewrite external data into native JDdS evidence. Preserve the user's selected MCP result with attribution; native Eclipse verification is an optional, explicit subsequent step.
The official MCP tool guidance also emphasizes human control, visible tool invocation, and confirmation for operations that require it. 

GitHub
+1





6. Skills: the most important extensibility layer
This is where your question becomes interesting.
Can skills be turned into agent workflows and used in Eclipse?

Yes. Absolutely. And we should design the system so skills can be used in three ways: as instructions, as executable capabilities, and as workflow building blocks.
But we must distinguish these concepts.
6.1 Skill vs tool vs agent vs workflow
Component	Meaning	Example
Tool	A callable capability	get_financial_statements
Skill	Reusable domain procedure and instructions	fundamental_company_analysis
Agent	A configured reasoning worker	Fundamental Research Agent
Workflow	A structured sequence or graph of tasks	Earnings Research Pipeline
Bot	A persistent or interactive agent identity	Market Research Bot
Harness	Runtime that coordinates all of them	BlackEclipse Kernel
A skill should not automatically become a fully independent agent. A skill can be used by an agent, invoked as a step in a workflow, or composed with other skills.
Example
Skill:
Analyze a company's financial health using revenue growth, margins, leverage, cash flow, and accounting-quality checks.

Tool:
Retrieve the company's financial statements.

Agent:
A fundamental analyst that knows how to select, execute, and interpret the skill.

Workflow:
Research Company → Validate Data → Analyze Financial Health → Compare Peers → Generate Report.

That is the composition model we want.

7. The BlackEclipse Skill System
We should take inspiration from portable, progressive-disclosure skill systems, including Hermes's approach to skills and its use of reusable skill packages. Hermes documentation describes skills as modular procedural knowledge that can be loaded when relevant rather than putting every instruction into every prompt. 

Hermes Agent
+1




But we should extend that model for finance.
7.1 Skill structure
Each skill should be a versioned package with metadata, instructions, optional executable components, and evaluation criteria.
Example:
skills/
├── research/
│   ├── company-research/
│   │   ├── SKILL.md
│   │   ├── examples/
│   │   ├── templates/
│   │   └── tests/
│   │
│   ├── earnings-analysis/
│   │   ├── SKILL.md
│   │   └── tests/
│   │
│   └── source-verification/
│       ├── SKILL.md
│       └── tests/
│
├── financial-analysis/
│   ├── fundamental-analysis/
│   ├── valuation/
│   ├── financial-health/
│   ├── technical-analysis/
│   ├── portfolio-analysis/
│   └── risk-analysis/
│
├── engineering/
│   ├── data-pipeline/
│   ├── backtesting/
│   ├── mcp-server-creation/
│   └── code-review/
│
└── system/
    ├── skill-authoring/
    ├── skill-evaluation/
    ├── memory-curation/
    └── research-planning/

These are example organization categories, not a requirement that every skill be a separate repository.
7.2 Example SKILL.md
---
name: fundamental-company-analysis
version: 1.0.0
description: Analyze a public company using verified financial
statements, profitability, growth, cash flow, and leverage.
domain: finance
type: analytical
risk_level: informational
requires:
  - financial_statements
  - market_data
  - calculator
outputs:
  - structured_analysis
  - evidence_table
  - report
---

# Fundamental Company Analysis

## Objective

Evaluate the financial condition and operating performance
of a company using available, verified data.

## Procedure

1. Identify the company and reporting currency.
2. Confirm the analysis period.
3. Retrieve financial statements.
4. Check the statement periods and units.
5. Calculate relevant financial ratios.
6. Compare trends across reporting periods.
7. Identify missing or inconsistent information.
8. Cite the source of each material claim.
9. Separate observations from interpretations.
10. Produce a structured report.

## Required checks

- Revenue growth
- Gross margin
- Operating margin
- Net margin
- Free cash flow
- Debt and liquidity
- Share dilution
- Data freshness
- Currency and unit consistency

## Failure conditions

- Missing critical data
- Unverified figures
- Inconsistent reporting periods
- Unsupported causal claims
- Conflicting financial information

## Output format

Return structured data and a human-readable report.

The skill should be discoverable, inspectable, versioned, and testable.
Don't treat Markdown as magic. A skill's instructions must be combined with tool schemas, runtime policies, input data, and output validation.

8. Can skills become workflows? Yes — here's how
This should be a first-class feature, not an afterthought.
8.1 The skill-to-workflow pipeline
Skill → Workflow
1. Create skill
Instructions, inputs, tools, outputs


2. Define execution contract
Input schema · Output schema · Permissions · Validation


3. Wrap as a workflow node
Skill reference · Agent configuration · Runtime settings


4. Compose
Sequential · Parallel · Conditional · Loop · Human approval


5. Validate and publish
Test cases · Version · Permissions · Run history


Example: one skill, three uses
Use 1 — Direct agent invocation
"Analyze Nvidia's fundamentals."

The fundamental research agent selects the skill and executes it.
Use 2 — Workflow node
Daily company monitoring workflow.

The skill is a node that analyzes newly available financial information.
Use 3 — Custom user agent
User creates a "Value Researcher" agent.

The agent is configured with valuation, financial health, and source-verification skills.
The same skill can be reused without copying its entire implementation.
8.2 Workflow definition
For the first implementation, use a declarative workflow graph.
type WorkflowNode =
  | {
      id: string;
      type: "skill";
      skillId: string;
      inputMapping: Record<string, unknown>;
    }
  | {
      id: string;
      type: "agent";
      agentId: string;
      inputMapping: Record<string, unknown>;
    }
  | {
      id: string;
      type: "tool";
      toolId: string;
      inputMapping: Record<string, unknown>;
    }
  | {
      id: string;
      type: "condition";
      expression: string;
    }
  | {
      id: string;
      type: "approval";
      approvalPolicy: string;
    };

This is an illustrative contract, not a complete production schema.
The workflow engine should also support:
- Typed inputs and outputs.
- Node dependencies.
- Data passing between nodes.
- Retry configuration.
- Timeouts.
- Parallel branches.
- Conditional routing.
- Human approval.
- Cancellation.
- Run history.
- Versioned workflow definitions.
Do not start by building a huge visual drag-and-drop editor. First make workflow execution reliable using a declarative format. Then build the visual editor on top of the same format.
That prevents the UI from becoming the system's source of truth.

9. Skill creation: Eclipse should create its own skills
This is one of the areas where we can make the product substantially more capable.
You want Eclipse to learn from repeated work and turn successful solutions into reusable skills.
We should support three skill creation methods.
9.1 Manual skill authoring
The user says:
"Create a skill for analyzing Pakistan Stock Exchange companies using local financial data."

Eclipse generates a draft skill.
The user reviews:
- Description.
- Procedure.
- Required tools.
- Input and output schema.
- Financial assumptions.
- Safety and permissions.
- Evaluation examples.
Then the skill is saved.
9.2 Skill creation from a successful task
Example:
1. User asks Eclipse to research an industry.
2. Agent uses multiple tools.
3. The workflow succeeds.
4. The user asks: "Turn this into a reusable skill."
5. Eclipse extracts the reusable procedure.
6. The system removes irrelevant task-specific details.
7. It generates a draft skill with test cases.
8. User approves or edits it.
9. Skill is versioned and published to the user's workspace.
Important: A successful run is not automatically proof that the procedure is correct. Skill generation must separate the procedure from its specific findings and validate the resulting instructions.
9.3 Skill improvement
When an agent fails repeatedly:
- Capture the failure.
- Identify the cause.
- Propose a change.
- Generate a regression test.
- Evaluate the updated skill.
- Require approval for production publication, depending on policy.
This is a controlled learning loop, not unrestricted self-modification.

10. Skill registry and discovery
You need a central skill registry.
It should support:
Feature	Purpose
Search	Find skills by name, domain, description, and capability
Versioning	Keep historical versions
Dependencies	Track required tools and other skills
Compatibility	Identify supported inputs and environments
Permissions	Define allowed operations
Provenance	Record author, source, and changes
Testing	Store skill evaluation cases
Publishing	Draft → reviewed → published → archived
Sharing	Export and import portable skills
Trust	Mark skill origin and review status
Skill selection
Do not inject every skill into every prompt.
Use progressive disclosure:
1. Load a compact skill index.
2. Identify likely relevant skills.
3. Retrieve the full content for selected skills.
4. Check compatibility and permissions.
5. Execute the skill.
This saves context and improves routing.

11. Agent architecture: specialized agents, not random personas
We should not create agents simply because a name sounds impressive.
Every agent should have a defined purpose, tool access, input contract, output contract, and evaluation criteria.
11.1 Initial agent catalog

Research Agent
Finds, compares, and synthesizes evidence from financial and macroeconomic sources.
Skills: research planning, web research, source verification, report writing.




Fundamental Analyst
Analyzes financial statements, operating performance, valuation inputs, and company risks.
Skills: financial health, accounting checks, valuation, peer comparison.




Quant Research Agent
Builds and tests systematic research hypotheses, indicators, and backtests.
Skills: feature engineering, backtesting, statistical validation, robustness testing.




Engineering Agent
Creates code, data pipelines, tools, tests, and integrations inside controlled environments.
Skills: code generation, repository analysis, testing, debugging, MCP development.




Risk Agent
Evaluates portfolio exposures, risk metrics, assumptions, and scenario analysis.
Skills: drawdown, volatility, concentration, stress testing, risk reporting.



Later, we can add:
- Macro and economic research agent.
- Earnings and filings agent.
- Data quality agent.
- Portfolio construction assistant.
- Strategy review agent.
- News monitoring agent.
- Research critic.
- Workflow designer.
- Skill curator.
- Agent evaluator.
11.2 The orchestrator
The orchestrator is responsible for deciding:
- Which agent should handle the task.
- Whether to execute serially or in parallel.
- Which skills are needed.
- When to ask the user for clarification.
- When to request approval.
- When to stop and report uncertainty.
Don't make the orchestrator the only place where reasoning happens. Agents should have clear scopes and reusable contracts.

12. Bots: persistent agents users can build
You mentioned bots, and I think this should be a major feature.
A bot is a persistent agent configuration that can operate interactively or on a schedule.
Example:
"Create a bot that monitors US technology companies, summarizes relevant earnings announcements, and prepares a weekly research report."

The bot should contain:
type BotDefinition = {
  id: string;
  name: string;
  description: string;

  systemInstructions: string;
  skills: string[];
  allowedTools: string[];

  modelProfile: string;
  workflowId?: string;

  schedule?: {
    enabled: boolean;
    expression: string;
    timezone: string;
  };

  permissions: {
    readData: boolean;
    writeArtifacts: boolean;
    externalCommunication: boolean;
    executeCode: boolean;
  };

  outputPreferences: {
    format: "chat" | "report" | "table" | "dashboard";
  };
};

The schema should be expanded with ownership, versioning, secrets references, quotas, and approval policies before production.
Bots should support
- Manual chat.
- Scheduled runs.
- Event-driven triggers.
- Watchlists.
- Saved research topics.
- Persistent memory.
- Custom skills.
- Custom tool permissions.
- Multiple output channels.
- Run history.
- Pause and resume.
- User approval.
Do not give every bot unrestricted autonomy. A research bot may be allowed to fetch data and generate reports but not place trades, send messages, or alter a user's portfolio without explicit authorization.

13. Research engine: this is where Eclipse can differentiate
Research is not just web search + LLM summary.
For financial research, we need an evidence-oriented pipeline.
13.1 Research capabilities
Eclipse should support:
- Web search and source retrieval.
- Financial statement retrieval.
- Regulatory filings.
- Earnings transcripts.
- Corporate announcements.
- Macro indicators.
- News monitoring.
- Historical market data.
- Industry and peer research.
- Company timelines.
- Cross-source comparison.
- Structured report generation.
- Source and claim tracking.
- Research updates over time.
We should distinguish between data retrieval, evidence extraction, analysis, and synthesis.
13.2 The research pipeline
Evidence-First Research
Research question


Scope & plan
Time period · geography · instruments · required evidence


Retrieve sources
Filings · market data · news · macro · company information


Extract claims & data
Figures · dates · quotes · source links · confidence metadata


Validate
Units · periods · source conflicts · missing evidence


Analyze
Calculations · comparisons · scenarios · competing explanations


Report
Findings · assumptions · limitations · citations · evidence table


13.3 Research artifact model
Don't save only the final text.
Save the research as structured artifacts:
Research Project
├── Research Question
├── Scope
├── Plan
├── Source Records
├── Extracted Evidence
├── Calculations
├── Analysis
├── Assumptions
├── Conflicts
├── Conclusions
├── Limitations
└── Final Report

This is essential for:
- Reproducibility.
- Updating reports.
- Comparing research over time.
- Auditing source claims.
- Training evaluation datasets.
- Avoiding repeated research.
13.4 Financial research-specific quality controls
The system should check:
- Whether numbers refer to the same reporting period.
- Whether values are in thousands, millions, or billions.
- Whether currencies differ.
- Whether GAAP and non-GAAP figures are mixed.
- Whether adjusted metrics are labeled.
- Whether stock splits and corporate actions affect historical comparisons.
- Whether market data is delayed.
- Whether a reported number is actual, estimated, or forecast.
- Whether a source is primary or secondary.
- Whether an inference is presented as a documented fact.
Financial research should preserve uncertainty rather than inventing confidence.

14. Memory: the system should remember, but not indiscriminately
Memory is one of the biggest parts of a harness.
A common mistake is storing every conversation in a vector database and calling that memory.
That is not enough.
We need multiple memory types with different lifecycles, access rules, and update policies.
14.1 Recommended memory architecture
Memory Layers
Working Memory
Current task context, intermediate results, active plan, tool outputs.

Session Memory
Conversation history, run events, decisions, and session summaries.

User Memory
Explicit preferences, approved profile information, recurring workflow choices.

Agent Memory
Reusable lessons about tools, environment behavior, and procedural knowledge.

Research Knowledge
Research artifacts, evidence, historical findings, and source-linked knowledge.

Workflow Memory
Execution outcomes, failed runs, successful patterns, and improvement candidates.


Hermes's documented architecture separates persistent sessions, memory, and skills, with retrieval and progressive context loading. That separation is a useful pattern to adapt rather than treating all stored information as one undifferentiated memory store. 

GitHub
+1




14.2 Memory data model
type MemoryRecord = {
  id: string;
  ownerId: string;

  kind:
    | "user_preference"
    | "agent_fact"
    | "research_finding"
    | "workflow_lesson"
    | "project_context";

  content: string;
  structuredData?: Record<string, unknown>;

  sourceType:
    | "user"
    | "agent"
    | "research"
    | "workflow";

  sourceId?: string;

  confidence?: number;
  createdAt: string;
  updatedAt: string;

  expiresAt?: string;
  sensitivity: "normal" | "sensitive";
  status: "active" | "archived" | "deleted";
};

Treat confidence as metadata about the record's reliability or verification state—not as a guarantee that the information is true.
14.3 Memory retrieval
A strong retrieval system should combine:
- Keyword search.
- Full-text search.
- Semantic retrieval.
- Structured filters.
- Recency.
- Provenance.
- Access control.
- Relevance ranking.
For financial research, structured filters and provenance are as important as semantic similarity.
Example:
"What did we discover about the semiconductor sector during our previous research?"

The system should retrieve relevant artifacts, dates, sources, and prior conclusions—not simply similar sentences.
14.4 Memory write policy
Not everything should be remembered.
Automatically eligible
- Stable, useful project conventions.
- Reusable tool troubleshooting knowledge.
- User-approved preferences.
- Important research artifacts with source metadata.
- Reusable workflow lessons.
Require approval or stricter handling
- Sensitive financial information.
- Personal account information.
- Trading decisions.
- Private credentials.
- Unverified research claims.
- Temporary hypotheses.
- Potentially harmful or misleading instructions.
Never use memory as proof
Memory can help find prior information. It should not override fresh data, source verification, or explicit user corrections.

15. Code generation: Eclipse should be able to build its own tools
This is where the engineering agent becomes extremely important.
Your goal is not merely to generate Python snippets in a chat window. You want an agent that can build actual financial software. The target is a bounded, reviewable coding agent that can complete a small repository task end to end while the user remains in control of consequential changes.
Examples:
- A new market data adapter.
- An MCP server.
- A financial ratio calculator.
- A backtesting strategy.
- A chart indicator.
- A portfolio analysis module.
- A data ingestion pipeline.
- A test suite.
- A research workflow.
- A new agent skill.
15.1 Code generation lifecycle
Controlled Engineering Loop
1. Understand the request and repository context.
2. Inspect relevant files and existing interfaces.
3. Generate a bounded implementation plan.
4. Modify code in a controlled workspace or branch.
5. Run formatting, type checks, linting, and tests.
6. Review the diff and validate behavior.
7. Present the changes, test results, and remaining risks.
8. Require approval before merging or deploying, according to policy.

15.2 Coding-agent capability contract
The Code Agent is a specialized harness agent, not a prompt-only mode. It uses the existing Python harness, run lifecycle, model providers, event stream, skill system, and front-door conventions. Its tools are explicit, typed, permissioned, bounded, auditable, and restricted to a task workspace. It must not inherit the finance agent's tools or access just because both agents share the harness.

The minimum end-to-end contract is:
- Receive a task, repository identity, base revision, user-selected scope, and execution policy.
- Inspect repository status before work; preserve pre-existing user changes and never treat them as agent-owned.
- Search and read files selectively; use repository metadata and architecture docs to retrieve relevant context rather than dumping the whole repository into the prompt.
- Produce a plan with target files, expected behavior, risks, and checks. Let the user review/adjust the plan for broad or ambiguous tasks; small, reversible tasks can proceed under the selected policy.
- Create an isolated worktree or equivalent disposable checkout at the selected base revision. Never edit the user's active checkout by default.
- Apply validated patches only within the task workspace. Reject traversal, symlink escapes, protected paths, oversized writes, and writes outside declared scope unless scope is explicitly expanded and recorded.
- Run only allowlisted commands in an OS/container sandbox with no inherited secrets, bounded CPU/memory/time/output, controlled dependency/network access, and no access to production databases, credentials, broker APIs, or live-order paths.
- Capture command, working directory, exit code, duration, bounded output, and tool identity in the run trace. A model statement is never proof that a command ran or passed.
- Inspect the final diff against the task base, identify generated/untracked files, secret-like content, unexpected database changes, and scope violations; report checks actually run and checks skipped with reasons.
- Keep all edits as a reviewable patch/worktree. Never commit, push, open a PR, deploy, or merge without an explicit user request and applicable approval.
- Support cancellation, restart/resume from durable checkpoints, and cleanup of task workspaces without deleting user data.

The agent should support explicit autonomy profiles:
1. **Plan only:** inspect and propose; do not write or execute.
2. **Edit and verify:** write inside the isolated task workspace and run policy-approved checks; return a diff for review.
3. **User-approved external action:** commit, publish, deploy, or other external side effect only after an explicit request/approval. This profile never implies permission to trade or mutate financial production data.

Every file and command tool must enforce policy in code, not rely on the model prompt. A proposed tool call is not authorization. The policy engine checks the run's user, repository, workspace root, allowed paths, command class, network policy, resource budget, and current approval state before execution. Denials are structured results and are visible in the trace.

15.3 Delivery phases and acceptance gates
Build this as a vertical slice in the roadmap's Phase 7. Do not unlock broad autonomous operation before earlier gates pass:

**7A — Read-only repository navigator.** Bind a run to one repository and base revision; expose status, file listing, bounded search, and text reads. Ignore or redact secrets/binary/vendor/generated data by policy. Acceptance: answers cite paths and line ranges; tests prove paths cannot escape the root and pre-existing dirty files are visible and untouched.

**7B — Isolated patch authoring.** Allocate a disposable worktree, apply bounded diffs, and stream progress. Acceptance: a fixture task edits the intended file, preserves unrelated dirty checkout changes, rejects traversal/symlink/protected-path writes, can be cancelled, and leaves a reviewable diff.

**7C — Sandboxed checks.** Add a command broker with an allowlist and OS/container isolation, bounded resources, no secret inheritance, network denied by default, and explicit dependency policy. Acceptance: benign checks pass; timeout, output flood, forbidden command, filesystem escape, network, and secret-access probes are blocked or contained and recorded.

**7D — Review and repair loop.** Compare changes with the base, run configured checks, return failures to the agent for a bounded repair attempt, then produce a summary with exact diff and verified command results. Acceptance: checks cannot be reported as passing unless the command broker recorded success; retry count and total budgets are enforced.

**7E — Product workflow and policy controls.** Add task creation/resume/cancel, autonomy profiles, approval events for protected paths or elevated commands, worktree lifecycle, artifact download/open, and audit UI. Acceptance: approval is bound to the exact action and workspace; changed action/payload requires new approval; restart resumes without duplicate side effects; cleanup cannot remove the user's checkout.

**7F — Evaluation and controlled expansion.** Maintain coding task fixtures, quality metrics, and adversarial safety cases. Measure task completion, diff correctness, regression rate, check reliability, cost, latency, and policy violations. Expand command/network/path capabilities only when evaluations demonstrate the need and isolation tests pass. MCP adapters, remote containers, commits, PRs, and deployment are later integrations, not prerequisites for safe local patching.

Phase 7 is complete only when all gates pass on supported platforms, failures are honestly surfaced, run traces and diffs are durable, and the user can inspect or discard the isolated result. “Model produced code” or “tests exist” alone does not satisfy the phase.

Code execution isolation
Code generation is not enough. The execution environment matters.
Use a sandbox abstraction supporting, depending on deployment:
- Local development environment.
- Containerized execution.
- Restricted filesystem.
- Network allowlists.
- Resource limits.
- Process timeouts.
- Dependency controls.
- Artifact collection.
- Test execution.
For a financial application, generated code must not be allowed to silently modify production databases, expose credentials, or place live orders.
The implementation must default to deny for network and writes outside the isolated worktree. Treat database files, settings vaults, key material, broker/trading interfaces, deployment credentials, and production configuration as protected resources. Code-agent permissions are separate from finance research permissions; no coding sandbox may silently gain access to market-data secrets or execution credentials.
Repository awareness
Eclipse should understand its own codebase through:
- Repository indexing.
- Symbol and dependency search.
- Type information.
- Relevant file retrieval.
- Git diffs.
- Build and test commands.
- Project conventions.
- Architecture documentation.
Do not instruct the agent to repeatedly read the entire repository. Use targeted retrieval and explicit scope.

16. The finance-specific tool catalog
This is the capability layer that makes Eclipse different from a general-purpose agent.
We should create a consistent internal tool contract and expose appropriate tools through MCP.
16.1 Market data
Tool	Purpose
market.get_quote	Current or latest available quote
market.get_historical_prices	OHLCV and adjusted historical data
market.get_asset_metadata	Instrument details
market.get_corporate_actions	Splits, dividends, and related events
market.get_market_status	Trading calendar and session state
market.get_universe	Supported instruments and markets
16.2 Fundamental data
Tool	Purpose
fundamentals.get_statements	Income statement, balance sheet, cash flow
fundamentals.get_ratios	Calculated or sourced ratios
fundamentals.get_estimates	Estimates with source and period metadata
fundamentals.get_filings	Filings and source documents
fundamentals.get_company_profile	Business and sector metadata
fundamentals.compare_companies	Standardized peer comparison
16.3 Research
Tool	Purpose
research.search_sources	Search approved sources
research.fetch_source	Retrieve source content
research.extract_evidence	Extract structured claims and figures
research.compare_sources	Compare conflicting or overlapping evidence
research.create_report	Produce a structured report
research.update_report	Refresh an existing research artifact
16.4 Quant and analytics
Tool	Purpose
quant.calculate_indicator	Technical indicator calculations
quant.run_backtest	Execute a defined backtest
quant.evaluate_strategy	Analyze performance and robustness
quant.calculate_risk	Volatility, drawdown, VaR, and related metrics
quant.run_scenario	Evaluate scenario assumptions
quant.export_dataset	Export validated research data
16.5 Portfolio
Tool	Purpose
portfolio.get_holdings	Read holdings
portfolio.analyze_exposure	Concentration and exposure
portfolio.calculate_performance	Performance metrics
portfolio.generate_review	Produce a portfolio review
portfolio.create_draft_allocation	Generate a draft allocation for user review
For any capability that can change real holdings, execute orders, or transmit sensitive information, use separate write permissions and approval controls.
16.6 Engineering
Tool	Purpose
code.inspect_repository	Read scoped repository context
code.create_patch	Generate controlled changes
code.run_tests	Run approved test commands
code.run_sandbox	Execute isolated code
code.create_mcp_server	Scaffold an MCP server
code.create_skill	Generate a skill package
code.evaluate_skill	Run skill tests

17. Tool calling: make it reliable, not just powerful
The LLM should not be able to call any tool with arbitrary arguments.
We need a tool execution contract.
17.1 Tool lifecycle
Model proposes tool call


Schema validation


Policy & permission check


Approval gate, if required


Execute with timeout and limits


Validate result & provenance


Record event & return output


17.2 Tool permissions
Use a capability-based permission system.
Example:
type ToolPermission = {
  toolId: string;

  allowed: boolean;
  requireApproval: boolean;

  maxExecutionSeconds?: number;
  maxCallsPerRun?: number;

  dataScopes?: string[];
  networkPolicy?: "none" | "allowlist" | "restricted";
};

The real policy system should also account for tenant/user identity, environment, data sensitivity, and side-effect risk.
Permission levels
Read
Retrieve data, search sources, inspect research.

Compute
Run calculations, analytics, and isolated code.

Write
Create or modify artifacts, code, or configurations.

External side effect
Send communications, modify live systems, or place financial orders.


Default to least privilege. Allow users to configure permissions but retain system-level restrictions that cannot be bypassed by an agent.

18. Multi-agent orchestration
We should support several execution patterns.
18.1 Sequential
One agent's output feeds the next.
Research → Validate → Analyze → Report

Good for dependent work.
18.2 Parallel
Multiple agents work on independent tasks.
                  ┌─ Fundamental Agent ─┐
Research Question ├─ Industry Agent ────┤ → Synthesis
                  └─ Risk Agent ────────┘

Good for research where independent evidence streams can be gathered concurrently.
18.3 Supervisor and specialists
A supervisor creates and coordinates subtasks.
                    Supervisor
                  /      |       \
             Research   Data     Risk
               Agent    Agent    Agent
                  \      |       /
                    Synthesis

The supervisor should have bounded authority. It should not be able to grant itself new permissions or silently expand the scope of the task.
18.4 Critic and revision
For important research:
Draft → Critic → Revision → Validation

The critic checks:
- Unsupported claims.
- Missing evidence.
- Incorrect calculations.
- Contradictory conclusions.
- Scope drift.
- Overconfident language.
A critic is not a guarantee of correctness, so pair it with deterministic validation and source checks.
18.5 Human-in-the-loop
Use approvals when the task needs judgment, permission, or external side effects.
Examples:
- Approve a generated trading strategy before backtesting.
- Approve a code change before merge.
- Approve a workflow before activation.
- Approve a portfolio allocation draft before saving it.
- Approve an external message before sending.

19. The self-improvement loop
This is how Eclipse becomes better over time without becoming uncontrolled.
A harness should improve through evidence-based iteration, not by allowing an LLM to rewrite its core arbitrarily.
19.1 Improvement cycle
Continuous Improvement
Execute task


Capture trajectory
Tool calls · outputs · errors · user feedback


Evaluate
Correctness · completeness · cost · reliability


Propose improvement
Skill revision · tool fix · prompt change · routing update


Run regression tests


Review and publish


What should improve automatically?
Potentially:
- Skill drafts.
- Documentation.
- Test cases.
- Retrieval queries.
- Non-sensitive routing hints.
- Research templates.
- Error handling suggestions.
What should require review?
- Production code.
- Security policies.
- Tool permissions.
- Financial calculation logic.
- Live trading integrations.
- Changes to core orchestration.
- Changes that affect user data access.
Self-improvement should be measurable. Keep old versions, compare evaluation results, and make rollback straightforward.









20. The financial data architecture: build on JDdS, don't bypass it
This is especially important for your existing Eclipse project.
You already have JDdS as the data layer/control plane between sources and users. The harness should consume JDdS through a stable, typed interface rather than letting each agent directly call arbitrary financial APIs.
20.1 Recommended data flow
External Sources
      │
      ▼
Source Adapters
      │
      ▼
Ingestion & Normalization
      │
      ▼
JDdS
(Data Quality + Source Selection + Modes)
      │
      ├── Market Data
      ├── Fundamentals
      ├── News
      ├── Macroeconomics
      ├── Corporate Events
      └── Portfolio Data
      │
      ▼
Harness Tool Interface
      │
      ▼
Agents / Skills / Workflows

The harness should not need to know whether a quote came from Binance, Yahoo Finance, Stooq, or another provider. It should receive a normalized result with metadata.
20.2 Data contract
Example:
type FinancialDataResult<T> = {
  data: T[];

  source: {
    provider: string;
    sourceUrl?: string;
    retrievedAt: string;
  };

  coverage: {
    start?: string;
    end?: string;
    timezone?: string;
  };

  quality: {
    status: "verified" | "partial" | "stale" | "unavailable";
    warnings: string[];
  };

  instrument: {
    symbol: string;
    market?: string;
    currency?: string;
  };
};

This is an initial conceptual contract. For production, separate quote, fundamental, and event schemas rather than forcing all financial data into one generic shape.
Why this matters
An agent should be able to say:
"The requested financial data is unavailable for this period, so I cannot complete the comparison."

It should not fabricate a result because the API returned an empty array or because a model inferred a plausible number.

21. Financial analysis must be deterministic wherever possible
LLMs are useful for interpreting data and constructing research plans. They should not be the source of truth for basic financial calculations.
Examples of deterministic services:
- CAGR.
- Gross margin.
- Operating margin.
- Net margin.
- Debt-to-equity.
- Current ratio.
- Free cash flow.
- Portfolio return.
- Maximum drawdown.
- Sharpe ratio.
- Position sizing.
- Trade risk.
- Transaction cost assumptions.
- Backtest performance statistics.
Use typed inputs, explicit formulas, test coverage, and clear assumptions.
Example
A user asks:
"Calculate the Sharpe ratio for my portfolio."

The agent should:
1. Retrieve the appropriate return series.
2. Identify the frequency and period.
3. Determine or ask for the risk-free rate assumption.
4. Call the deterministic calculation tool.
5. Validate the result.
6. Explain the methodology and limitations.
The model can help interpret the output, but the calculation itself should not depend on the model doing arithmetic in its response.

22. Backtesting: a research engine, not a prediction machine
This deserves its own design.
Your Eclipse already has trading journal and quant-related functionality. The harness should be able to create, execute, and analyze backtests using a controlled research engine.
Required components
Component	Responsibility
Data adapter	Retrieve historical market data
Data validator	Check gaps, timestamps, duplicates, and corporate actions
Strategy definition	Formal entry, exit, position sizing, and risk rules
Execution simulator	Model fills, fees, slippage, and execution assumptions
Backtest engine	Run the strategy
Metrics engine	Calculate performance and risk metrics
Robustness evaluator	Evaluate sensitivity and out-of-sample behavior
Report generator	Produce reproducible results
Important safeguards
- Prevent look-ahead bias.
- Avoid survivorship bias where applicable.
- Distinguish in-sample and out-of-sample data.
- Include realistic costs and slippage.
- Record strategy and dataset versions.
- Avoid treating backtest performance as proof of future returns.
The agent should generate a strategy specification and tests, not simply invent a strategy and announce that it works.

23. Research workspaces: make every major investigation persistent
The user should be able to create a research workspace.
Example:
AI Infrastructure Investment Research — 2026

Within the workspace:
- Research question.
- Companies and instruments.
- Saved sources.
- Financial datasets.
- Research notes.
- Agent runs.
- Workflow definitions.
- Evidence records.
- Generated reports.
- Watchlist.
- Follow-up questions.
- Update history.
A workspace should let the user continue the same investigation days or months later.
Example interaction
Day 1
"Research the AI infrastructure industry."

Eclipse creates a research workspace and produces an initial report.
Day 7
"Update this research with recent earnings and changes in company guidance."

Eclipse retrieves new information, identifies changes, and updates the report.
Day 30
"What has changed since our previous report?"

Eclipse compares the new evidence with the prior research snapshot.
This is much more useful than repeatedly starting isolated chat conversations.

24. Model architecture: do not lock Eclipse to one provider
Your existing application supports multiple model providers. The harness should retain that flexibility.
24.1 Model router
Create a provider-independent interface.
interface ModelProvider {
  generate(request: ModelRequest): Promise<ModelResponse>;
  stream(request: ModelRequest): AsyncIterable<ModelEvent>;
  supports(capability: ModelCapability): boolean;
}

The interface needs to accommodate structured outputs, tool calls, streaming, usage metadata, cancellation, and provider-specific capabilities.
24.2 Different models for different tasks
We should not automatically use the largest model for every operation.
Task	Model strategy
Simple classification	Fast, low-cost model
Tool selection	Reliable tool-capable model
Complex research planning	Strong reasoning model
Source synthesis	Model with adequate context and structured output support
Code generation	Model optimized for coding
Data extraction	Structured-output-capable model
Skill evaluation	Independent or differently configured evaluator
Local/private workflows	Local model where quality and resource constraints permit
This should be policy-driven, configurable, and benchmarked rather than based on model branding.
Model fallback
Implement:
- Provider fallback.
- Timeout handling.
- Retry limits.
- Structured-output validation.
- Token and budget limits.
- Error classification.
- Circuit breakers for unhealthy providers.
The fallback system should not silently switch to a model that lacks the capabilities required for a task.

25. Context engineering
This is an area where a lot of agent applications become inefficient.
You need to control what the model sees, when it sees it, and how much of it is retained.
Context layers
System Policy
    +
Agent Configuration
    +
Task Instructions
    +
Relevant Skills
    +
Tool Schemas
    +
Retrieved Memory
    +
Research Evidence
    +
Current Execution State
    +
User Request

Don't dump all of these into one enormous prompt every time.
Use:
- Progressive skill loading.
- Relevant memory retrieval.
- Summarized session state.
- Structured tool outputs.
- Context compaction.
- Source excerpts rather than entire documents when appropriate.
- Separate planning and execution contexts where beneficial.
Context budgets
Every run should have limits for:
- Input tokens.
- Tool output size.
- Retrieved documents.
- Number of tool calls.
- Execution time.
- Cost.
A tool that returns 50,000 lines of raw data is not a good interface for an LLM. Return structured summaries, pagination, filters, and links to full artifacts.

26. Security and governance: this must be designed early
The more capable Eclipse becomes, the more dangerous unrestricted execution becomes.
This is not a reason to avoid autonomy. It is a reason to make autonomy explicit and controlled.
26.1 Threat model
We need to protect against:
- Prompt injection from web pages and documents.
- Malicious or compromised MCP servers.
- Tool argument manipulation.
- Credential exposure.
- Unauthorized data access.
- Generated code with harmful behavior.
- Cross-user data leakage.
- Accidental destructive operations.
- Excessive resource consumption.
- Incorrect financial outputs.
- Hidden external side effects.
26.2 Security architecture
Defense in Depth
Identity & tenant isolation


Capability-based tool permissions


Input and output validation


Sandbox / network controls


Approval & audit


Monitoring & incident response


Finance-specific safety boundaries
We should explicitly distinguish:
- Informational research.
- Simulation and paper trading.
- Portfolio analysis.
- Draft portfolio changes.
- Live account operations.
Live trading, fund transfers, or other consequential financial actions must not be enabled merely because an agent has access to a tool. They require separate authorization, broker-specific integration, risk controls, and user confirmation appropriate to the operation.

27. Evaluation: how do we know Eclipse is getting better?
This is where we can separate a serious engineering platform from a flashy demo.
We need an evaluation system from the beginning.
27.1 Evaluation categories
Category	Example measurement
Research accuracy	Supported claims and correct source interpretation
Data quality	Correct periods, units, currencies, and freshness
Calculation accuracy	Expected outputs for known datasets
Tool reliability	Success rate, timeout handling, schema errors
Workflow reliability	Successful completion under defined conditions
Code quality	Tests, type safety, linting, regression behavior
Efficiency	Latency, tool count, token usage, cost
Safety	Blocked unauthorized actions and isolation tests
User experience	Clarity, usefulness, and correction rates
Do not collapse all of this into one arbitrary score.
27.2 Benchmark datasets
Create a curated test suite containing:
- Financial ratio questions with known answers.
- Historical market data tasks.
- Source verification tasks.
- Financial statement interpretation.
- Research questions with reference evidence.
- Portfolio risk calculations.
- Backtest integrity tests.
- Tool argument validation.
- Prompt injection scenarios.
- Code-generation tasks with expected tests.
Use dated datasets where the question depends on historical availability. Otherwise, the evaluation can accidentally reward the system for using information that wasn't available at the time.
27.3 Trajectory evaluation
Record execution traces:
Run
├── User Request
├── Plan
├── Tool Calls
├── Tool Results
├── Agent Outputs
├── Errors
├── Retries
├── Approvals
├── Final Artifact
└── Evaluation Results

This allows you to identify where the system fails:
- Wrong tool selected.
- Missing source.
- Bad data normalization.
- Faulty calculation.
- Poor synthesis.
- Excessive looping.
- Unnecessary tool calls.
- Inadequate error handling.
The goal is not merely to produce a good final answer. It is to make the entire execution process reliable.

28. Observability and debugging
You have previously wanted OpenCode prompts that avoid endless re-reading and looping. The same principle applies to the harness.
The system should make loops visible and enforce limits.
What to track
- Run ID.
- Parent and child tasks.
- Agent and skill versions.
- Model provider.
- Tool calls and arguments, subject to sensitive-data redaction.
- Tool results and errors.
- Token usage.
- Latency.
- Retries.
- State transitions.
- Approval events.
- Artifact references.
Run control
Implement:
- Pause.
- Resume.
- Cancel.
- Retry failed node.
- Restart from checkpoint.
- View trace.
- Inspect output.
- Compare runs.
Loop prevention
Set explicit limits:
- Maximum steps per run.
- Maximum retries per node.
- Maximum repeated tool calls.
- Maximum execution time.
- Maximum token budget.
- Maximum recursion depth.
- Maximum parallel tasks.
If the agent gets stuck, it should report the blocker rather than continue indefinitely.

29. Storage and persistence
Your existing stack includes PostgreSQL for the main application and SQLite in parts of the Trading Journal. We should use each storage technology intentionally rather than forcing everything into one database.
Suggested storage architecture
Data	Storage
Users, agents, workflows, permissions	PostgreSQL
Research metadata and structured artifacts	PostgreSQL
High-volume event records	PostgreSQL or dedicated event storage, based on scale
Large documents and generated files	Object storage / filesystem abstraction
Local execution state	SQLite where appropriate
Search indexes	PostgreSQL search capabilities or dedicated index
Financial datasets	JDdS-managed storage appropriate to the source and workload
Secrets	Dedicated secret-management mechanism, not ordinary application tables
For the first implementation, avoid unnecessary distributed infrastructure.
A well-designed modular application with PostgreSQL, object storage, and a controlled execution environment is sufficient to build a powerful initial harness.

30. Proposed TypeScript domain boundaries
Since Eclipse is built with Next.js, React, TypeScript, and Prisma, I would keep the harness implementation close to your existing architecture initially.
A conceptual layout:
src/
├── lib/
│   ├── harness/
│   │   ├── runtime/
│   │   │   ├── run-manager.ts
│   │   │   ├── execution-loop.ts
│   │   │   ├── state-machine.ts
│   │   │   └── cancellation.ts
│   │   │
│   │   ├── agents/
│   │   ├── skills/
│   │   ├── workflows/
│   │   ├── tools/
│   │   ├── mcp/
│   │   ├── memory/
│   │   ├── context/
│   │   ├── approvals/
│   │   ├── evaluation/
│   │   └── observability/
│   │
│   ├── finance/
│   │   ├── data/
│   │   ├── fundamentals/
│   │   ├── portfolio/
│   │   ├── quant/
│   │   └── research/
│   │
│   └── jdds/
│
├── app/
│   ├── api/
│   │   ├── harness/
│   │   ├── agents/
│   │   ├── workflows/
│   │   ├── skills/
│   │   └── research/
│   │
│   └── ...
│
├── components/
│   ├── harness/
│   │   ├── run-viewer/
│   │   ├── workflow-builder/
│   │   ├── skill-editor/
│   │   ├── agent-builder/
│   │   └── approval-dialog/
│   └── ...
│
└── workers/
    ├── research-worker.ts
    ├── workflow-worker.ts
    └── code-worker.ts

This is a proposed organization. We should first inspect your actual repository structure before creating folders or moving existing code.
Important architecture choice
Don't run long, autonomous workflows directly inside a normal Next.js request handler.
Use a durable execution mechanism or worker-based approach for long-running jobs. The API layer should create or control runs, while workers execute tasks and report events.
The first version can use a simpler queue/worker implementation, but the execution model should be designed for resumability.

31. What should we build first?
This is the practical part.
We should not attempt to build the entire vision in one massive implementation. That creates too many moving parts and makes debugging painful.
The correct approach is to establish a vertical slice: a small but complete path through the architecture.
Phase 0 — Architecture and repository assessment
Foundation
Objective: Understand the existing Eclipse codebase and establish boundaries.
Tasks:
- Inspect existing chat and provider abstraction.
- Inspect JDdS interfaces.
- Identify current financial data tools.
- Inspect existing settings and authentication.
- Review database models.
- Identify background processing options.
- Determine where the harness runtime should live.
- Document architecture decisions.
Deliverables:
- Architecture decision record.
- Module boundary plan.
- Initial tool contract.
- Run state model.
- Security baseline.
- Implementation backlog.
Do not rewrite the existing application.
Phase 1 — Core harness loop
MVP runtime
Build:
- Run creation.
- Model provider adapter.
- Tool registry.
- Tool calling.
- Structured event stream.
- State management.
- Basic cancellation.
- Basic retry handling.
- Run history.
- Error handling.
First demonstration:
User asks a financial question → Agent uses a financial tool → Agent returns a verified structured answer.

No visual workflow editor yet.
Phase 2 — Skills
Reusable intelligence
Build:
- Skill manifest.
- Skill loader.
- Skill registry.
- Progressive disclosure.
- Skill permissions.
- Versioning.
- Draft/publish states.
- Skill execution contract.
- Basic skill tests.
Create initial skills:
1. Research planning.
2. Source verification.
3. Fundamental analysis.
4. Financial data quality.
5. Report generation.
Phase 3 — Research engine
Core financial value
Build:
- Research workspace.
- Source records.
- Evidence extraction.
- Financial data integration through JDdS.
- Structured research artifacts.
- Source-linked reports.
- Research update workflow.
- Research evaluation cases.

#### Implemented evidence-grounded research phase

BlackEclipse has since implemented an evidence-grounded answering phase in
`Black-Eclipse-site/python/harness/research/`. This is the current concrete
research vertical slice and extends the Phase 3 research-engine direction above.
The project tracks it as Harness Phase 4, with bounded web escalation tracked as
Phase 5; those implementation phase numbers are separate from this plan's
roadmap numbering.

The live supported flow is a narrow, unambiguous, single-company, two-period
financial comparison:

1. Parse the request into a typed research mandate with explicit metric and
   period requirements.
2. Retrieve evidence through the existing financial retrieval layer and JDdS
   bridge. Apply point-in-time cutoffs and retain source, identity, unit,
   currency, period, and availability metadata.
3. Classify each requested fact as covered, qualified, unavailable, stale,
   conflicting, or otherwise unresolved. Missing required metadata stays
   visible; it is never inferred as verified.
4. Build structured claims from the evidence and validate claim references,
   fields, periods, coverage, and conflicts deterministically. Financial
   calculations use deterministic calculation functions with recorded inputs
   and assumptions.
5. Synthesize through a bounded, tool-less model step that sees only the
   mandate, evidence packet, and coverage report. Unsupported claims are
   rejected or returned as an honest partial answer.
6. Persist a research receipt with the mandate, evidence, coverage, claims,
   citations, gaps, and run metadata. The chat UI exposes evidence and can load
   the durable receipt.

When structured data is empty, stale, missing a requested period, or lacks
required metadata, Phase 5 escalates only the unsatisfied facts through a bounded
source hierarchy: structured data → primary-source web → reputable secondary
web. One research budget caps search, fetch, page, time, and token use. Web text
is untrusted, and numeric facts must be anchored to a verbatim span from a page
fetched during the run and pass deterministic checks for value, metric, period,
currency, and basis. If evidence remains insufficient, the answer reports the
gap and attempted sources.

The implementation also includes stable content-derived evidence and
calculation identifiers, a versioned semantic-support evaluation set, and
source-grounded restatement-chain handling. Restatement coverage remains
unavailable until providers supply reliable revision metadata; missing
consolidation basis can yield a qualified result. Current implementation details,
evaluation results, and known limits are maintained in
`Black-Eclipse-site/docs/harness/phase-4-progress.md` and
`Black-Eclipse-site/docs/harness/architecture.md`.

Phase 4 — Memory
Persistence
Build:
- Session storage.
- Memory records.
- Retrieval.
- Provenance.
- User-approved memory.
- Research knowledge.
- Memory update policies.
- Memory inspection and deletion.
Phase 5 — MCP
Interoperability
Build:
- MCP client.
- Server registry.
- Capability discovery.
- Tool schema normalization.
- User-facing permission/effect metadata and per-tool controls.
- Connection management.
- Per-server and per-tool user selection, enabled state, and connection diagnostics.
- Run-event, audit, provenance, timeout, cancellation, and bounded-output integration.
- Approval flow for tools with external or irreversible effects.
- Internal Eclipse MCP server exposing selected existing capabilities without duplicating domain logic.
Start with one read-only vertical slice to validate transport and registry integration, then support the full user-selected tool surface through declared effect metadata and explicit permissions. Do not impose finance-domain restrictions on MCP calls. JDdS is one source among configured sources; native source selection should consider freshness, coverage, provenance, and conflicts, while direct MCP workflows remain available by user choice. Add stdio and remote Streamable HTTP transports; keep MCP protocol/version compatibility explicit. Implement tools first, then resources/prompts/subscriptions as capability slices with their own lifecycle, context and security handling.

**Phase 5 delivery plan and gates**

**5A — Contract and threat model. — IMPLEMENTED (2026-09-24).** Define server configuration, owner/scope, transport, auth reference, protocol negotiation, capability catalog, tool identity, effect classes (`read`, `write`, `external_action`, `unknown`), status/error model, and budgets. Distinguish host execution controls from domain policy: the former are mandatory; the latter cannot silently prohibit user-selected finance workflows. Acceptance: architecture/ADR defines trust, data-flow, cancellation, redaction, prompt-injection boundary, and backward-compatible runtime integration. *Delivered in `python/harness/mcp/config.py` (typed `MCPServerConfig` + effect classes + budgets + redaction) and `naming.py` (tool identity, effect classification); documented in `docs/harness/architecture.md` (MCP boundary) and `docs/harness/decisions.md` ADR-H38.*

**5B — Local stdio client and fixture server. — IMPLEMENTED (2026-09-24).** Launch a configured command/argv without a shell; pass only explicitly scoped environment; handshake, list tools, normalize schemas, call a selected tool, and shut down cleanly. Acceptance: fake-server tests cover startup, malformed protocol, schema, duplicate names, timeout, cancellation, output bounds, and child termination; no server tools activate just because discovered. *Delivered in `python/harness/mcp/client.py` (MCP SDK stdio, bounded startup/catalog/call, cancellation, clean tree shutdown) + `naming.py` schema validation; fixtures `python/tests/mcp_fixtures/` and tests in `python/tests/test_mcp.py`.*

**5C — Tool registry adapter and run lifecycle. — IMPLEMENTED (2026-09-24).** Convert selected MCP tools to namespaced `ToolDefinition`s in the existing registry. Re-check server enabled state, per-tool selection, agent allowlist, and user permission on every call; validate inputs and outputs; propagate run/tool deadlines and cancellation; emit redacted `mcp.server.*` and `mcp.tool.*` events plus normal tool records. Acceptance: persisted and live traces identify server/tool, action class, duration, outcome, and safe diagnostics without secrets or oversized payloads. *Delivered in `python/harness/mcp/manager.py` (registry adapter, per-call rechecks, bounded/redacted output, `mcp.tool.*` events) with only selected read-only tools activated.*

**5D — Remote Streamable HTTP and authentication. — IMPLEMENTED (2026-09-30; was PARTIAL).** Add HTTPS remote connections, request headers from a secret reference, OAuth authorization lifecycle where supported, credential refresh/clear, auth diagnostics, redirect/DNS protections, and optional enterprise TLS configuration. Acceptance: secrets never enter project config, prompts, model schemas, logs, or receipts; auth/session state is scoped by user and server; server origin and redirect policy are revalidated. *Delivered: `transport: "http"` and `"sse"` via the MCP SDK clients sharing the stdio lifecycle; vault-backed header/query auth (`auth.secretRef`); OAuth 2.1 device flow (`oauth.py`, `oauth_flow.py`) with tokens in the encrypted vault (`mcp_oauth_token_*` over the bridge) and an operator-gated login/logout; `oauth_rejected`/`oauth_refresh_failed`/`oauth_not_logged_in`/`oauth_expired` diagnostics; SSRF guard + `redirect_guard.py` re-validating every hop; TLS/mTLS (`ssl_verify` true|false|CA-path, `client_cert`/`client_key`); transport selector, auth fields and OAuth sign-in in Settings. **Dated note (2026-09-30):** the interactive authorization-code browser leg remains a documented manual https step because the SDK refuses plain-http OAuth URLs (RFC 8252) — see `docs/harness/mcp-ui-parity-progress.md` §Limitations.*

**5E — Catalog selection and settings UX. — IMPLEMENTED (2026-09-24).** Provide add/test/enable/disable/remove, discovered capability review, per-tool include/exclude selection, permission/effect display, and connection/auth diagnostics. Newly discovered tools default to disabled until selected; catalog changes trigger review and a versioned diff. Acceptance: users can understand exactly what is enabled and why a call is denied; no MCP endpoint is enabled implicitly. *Delivered via `/mcp/*` runtime routes, `/api/harness/mcp/*` proxies, and Settings › MCP Servers (`src/components/screens/mcp-settings.tsx`); a per-server `catalogDigest` versions the discovered catalog and confirmation gates annotation-sourced tools. Remote HTTP/OAuth diagnostics remain part of 5D.*

**5F — Financial source independence and freshness. — IMPLEMENTED (2026-09-30; was NOT STARTED).** Extend native retrieval planning to treat JDdS, other configured structured providers, official/web research, and user-enabled MCP data as selectable source classes when appropriate. Add source health scoped by provider × market × asset class × capability × observation time; freshness/TTL by data type; requested as-of semantics; stale-but-usable labeling; parallel or sequential fallback; conflict preservation; and provider-independent evidence provenance. Do not silently claim equal trust or quality across providers. Keep direct MCP tool use available even when a tool does not implement Eclipse's retrieval contract. Acceptance: tests demonstrate stale JDdS loses preference when a fresher eligible source exists, no-data/failure/stale are distinct, conflicts survive, and the agent can explain source choice. Users can inspect or override source preferences. *Delivered (Phase 6 / 6.1): `mcp/mcp_retrieval.py` adapts an operator-declared `data_source_tools` entry into a native `RetrievalSource`, threaded via `manager.mcp_sources()` → `ToolContext.mcp_manager` → `FinancialRetrievalLayer(mcp_sources=...)` → `plan_retrieval(additional_sources=...)`; provenance stays `secondary`/`eclipseVerified=false`. Direct MCP tool use stays available for an undeclared tool. See `docs/harness/mcp-phase-6-progress.md` and ADR-H73.*

**5G — Effectful tools and approval. — IMPLEMENTED (2026-09-24).** Support tools that write or cause external effects only after their effects and permission requirements are declared, and after Eclipse can bind user approval to the exact server, tool, arguments/payload digest, run, and expiry. Re-approval is required if arguments or server identity change; deny unknown effect class by default. Acceptance: no prompt injection, tool description, prior approval, or model claim can authorize a changed action. Financial integrations remain user-directed; this approval gate governs consequential execution, not research topics or analytical choices. *Delivered: `python/harness/mcp/approvals.py` (`McpApproval` in `agent-memory.db`, digest binding, expiry, terminal denial, `unknown` never approvable), enforcement in `ToolRegistry` via `ToolContext.authorize_effect`, `enabled_effects` opt-in per server, `/mcp/approvals` + TS proxies + Settings panel; vault secret references (`secret_refs` → encrypted `mcp_secrets_v1`, resolved via `mcp_secret_resolve`).*

**5H — Eclipse as MCP server. — IMPLEMENTED (2026-09-30; was NOT STARTED).** Expose selected existing read APIs through a separately authenticated MCP server/transport. Reuse the existing services and ownership checks; provide stable schemas, instructions, attribution, pagination/limits, and protocol compatibility. Start with status/capability and research receipt access, then allow user-selected data capabilities. Acceptance: external clients receive only authorized data and no credentials or internal orchestration state; a client smoke test validates interoperability. *Delivered (Phase 6 M7): `mcp/server_exposure.py` exposes a narrow read-only surface (`eclipse_status`, `eclipse_list_receipts`, `eclipse_get_receipt`) with its own bearer auth (`HARNESS_MCP_SERVER_TOKEN`; unconfigured = disabled, never open), bounded pagination, structured errors, a recorded protocol version and a schema-hygiene guard (no secret/env/vault key). Exercised offline by two SDK clients (Streamable HTTP + SSE) plus an unauthenticated 401; a real Hermes interop transcript is recorded in `docs/harness/mcp-phase-6-progress.md`.*

**5I — Resources, prompts, subscriptions, evaluation, and operations. — IMPLEMENTED (2026-09-30; was PARTIAL); subscriptions remain a documented non-goal.** Add only capabilities the product can govern and explain: resource URI authorization and bounds; prompt versioning; subscription notification ownership/rate limits; diagnostics, health, metrics, reconnect and graceful degradation; adversarial prompt-injection and credential-isolation evaluations; interoperability matrix against representative clients/models (including DeepSeek function/tool calling). Acceptance: evaluation records protocol/client/server versions, tests context growth and catalog-size behavior, and verifies restart/cancellation/shutdown without leaked subprocesses or duplicate side effects. *Delivered (Phase 6 / 6.1): resources/prompts utility tools registered only when the live session advertises the capability AND the operator toggles (`tools.resources`/`tools.prompts`), with a per-server `resource_schemes` narrowing whose ceiling is the global allowlist; sampling/elicitation governed by `interactions.py` (off by default, per-call consent); setup diagnostics + health/metrics + keepalive/recycle/reconnect lifecycle; adversarial suites (`test_mcp_adversarial.py`, `test_mcp_injection_adversarial.py`, credential isolation, catalog flood, context-growth measurement); graceful degradation (`test_mcp_graceful_degradation.py`). **Subscriptions: explicitly NOT implemented** — an MCP notification cannot trigger a run or a write (recorded in the ADR and `__init__` docstring).*

**Phase completion gate.** User can connect local and remote MCP servers, inspect and select tools, choose finance workflows without a JDdS gate, and see every call with source/effect attribution. Calls pass through Eclipse's existing runtime validation, permissions, timeout/cancellation, persistence and observability. Native research can use multiple configured sources and treats JDdS as fallible; freshness, conflicts, provenance and uncertainty are explicit. Consequential actions are bound to fresh user approval. Eclipse can also expose selected read capabilities over MCP without duplicating domain services.
Phase 6 — Workflow engine
Automation
Build:
- Declarative workflow schema.
- Sequential execution.
- Parallel execution.
- Conditional nodes.
- Skill nodes.
- Agent nodes.
- Approval nodes.
- Checkpoints.
- Retry and cancellation.
- Run visualization.
Phase 7 — Code agent
Engineering
Build:
- Repository inspection.
- Code generation.
- Sandbox execution.
- Test runner.
- Patch review.
- Skill generation.
- MCP server scaffolding.
- Controlled deployment workflows.
Phase 8 — Agent and bot builder
User extensibility
Build:
- Agent configuration UI.
- Skill selection.
- Tool permissions.
- Model profile selection.
- Bot schedules.
- Watchlists.
- Run history.
- User-created workflows.
Phase 9 — Self-improvement and advanced autonomy
Advanced
Build:
- Trajectory analysis.
- Skill improvement proposals.
- Automated regression tests.
- Evaluation datasets.
- Workflow optimization.
- Agent performance comparisons.
- Background maintenance.
- Controlled publishing.

32. The first real workflow we should implement
I recommend starting with a Financial Research Agent.
Why?
Because it connects the most important parts of the system:
- Harness runtime.
- Model provider.
- Tool calling.
- JDdS.
- Skills.
- Research artifacts.
- Memory.
- Evaluation.
- User interface.
It is a better starting point than immediately building a visual workflow designer or self-modifying agent.
First workflow: Company Research
Company Research Pipeline
Initial target

User request


Research planning skill


Retrieve company data
JDdS · Market data · Fundamentals · Sources


Validate data


Fundamental analysis skill


Source verification


Generate report


Save research artifact + memory candidates


The workflow should return a structured report with:
- Company overview.
- Financial performance.
- Valuation inputs and assumptions.
- Risk factors.
- Evidence table.
- Missing data.
- Research limitations.
- Source links.
- Last updated timestamps.
The first implementation should support one company well, then expand to peer comparison and multi-company research.





33. The architecture principles I would not compromise on
These are the decisions that will determine whether Eclipse becomes a serious platform or a collection of loosely connected AI features.
Principle 1 — The harness is the product, not the model
Models will change. Providers will change. Open-source models will improve.
Your runtime, skills, workflows, financial tools, research artifacts, and user experience should remain useful across model changes.
Principle 2 — Every important capability needs a contract
Tools, skills, agents, and workflows should have:
- Defined inputs.
- Defined outputs.
- Permissions.
- Versioning.
- Error behavior.
- Evaluation criteria.
Avoid capabilities that only work because a particular prompt happens to produce a good result.
Principle 3 — Research must be evidence-first
Financial research should have source metadata, timestamps, assumptions, and limitations.
Do not let the system confuse plausible language with verified financial information.
Principle 4 — Memory is not truth
Memory helps the system retrieve prior context. Fresh evidence and deterministic validation should take precedence over stale or unverified memory.
Principle 5 — Autonomy should be bounded
Give agents the ability to complete useful tasks without asking for permission at every step. But make their authority explicit, observable, and limited.
Principle 6 — Build for extension, not premature complexity
Use modular interfaces and adapters. Don't build ten distributed services when a well-structured application can do the job.
Principle 7 — Make every major run inspectable
A user should be able to understand what Eclipse did, which tools it used, what evidence it found, and where uncertainty remains.
Principle 8 — Optimize for user outcomes
The system should help users research, understand, compare, and act on information. It should not optimize for impressive-looking agent loops or excessive tool calls.

34. What I would add to make Eclipse genuinely differentiated
Beyond matching general-purpose harness capabilities, I would focus on features that emerge from your finance-first direction.
These are product opportunities, not guarantees of market success.

1. Financial Knowledge Graph
Strategic

Connect companies, sectors, suppliers, products, economic indicators, earnings, and events.
Example: How does an energy-price shock relate to a company's costs, margins, and industry exposure?




2. Research That Evolves
Research workspaces retain prior evidence, compare new reports, and highlight changed assumptions.
The user can ask what changed without rebuilding the entire research process from scratch.




3. Research-to-Quant Pipeline
A research hypothesis can become a formal strategy specification, a backtest, a robustness evaluation, and a documented result.
This connects fundamental research, technical research, and engineering into one workflow.




4. Personal Financial Operating Environment
Users can create their own research agents, workflows, dashboards, skills, and memory policies.
The product adapts to different investment research processes without forcing everyone into one interface.




5. Open Financial Skills Ecosystem
Allow developers and users to publish, share, test, and install finance-focused skills and tool integrations.
Skills can be reusable assets across agents, workflows, and compatible environments.




35. What not to build first
This is important because your vision is very large.
I would not start with:
- A fully autonomous trading agent.
- A huge marketplace of agents.
- A complex visual node editor.
- A custom vector database before understanding retrieval needs.
- A multi-agent swarm for every question.
- Automatic self-modification of production code.
- Ten different financial data adapters before defining contracts.
- A complicated distributed microservice architecture.
Instead, build one complete and reliable research workflow, then generalize the successful abstractions.
The order matters because the first implementation will reveal what actually needs to be generalized.

36. The exact first milestone
I would define the first milestone as:
Eclipse Harness v0.1 — A working financial research agent with reusable skills, internal tool calling, structured research artifacts, persistent run history, and a foundation for MCP and workflows.

Acceptance criteria
- Agent can create and execute a research plan.
- Agent can call internal financial tools.
- Tools have validated schemas and permission checks.
- Skills can be discovered and loaded.
- Skills have versioned definitions.
- Run state is persisted.
- Tool calls and errors are visible.
- Research outputs contain source metadata.
- Financial calculations use deterministic services.
- Research artifacts can be revisited.
- The architecture supports future MCP integration.
- The runtime does not require a visual workflow builder to operate.
This is a meaningful vertical slice, not a toy chatbot.

37. Your first OpenCode implementation prompt
Once you are ready to begin, use a focused prompt that asks OpenCode to implement the foundation without turning the entire project into an uncontrolled refactor.
BlackEclipse — Build Harness Foundation v0.1
We are starting the agentic harness layer for BlackEclipse, a finance-first AI operating environment. Implement the initial harness foundation inside the existing repository.
Objective
Build a modular, provider-agnostic harness runtime that supports:
- Agent execution
- Internal tool calling
- Skill loading and discovery
- Persistent run state
- Structured execution events
- A foundation for MCP and workflow execution
Requirements
1. Inspect the existing codebase and reuse current model providers, JDdS interfaces, authentication, database patterns, and financial services. Do not rewrite working features.
2. Create clear module boundaries for runtime, agents, skills, tools, memory, MCP, workflows, and evaluation.
3. Implement the core run lifecycle: create, execute, persist state, handle tool calls, record events, complete, fail, and cancel.
4. Add a typed internal tool registry with schema validation, permission checks, timeouts, and structured errors.
5. Add a versioned skill manifest and skill loader with progressive disclosure. Support loading finance research skills.
6. Define stable interfaces so internal tools can later be exposed through MCP without duplicating business logic.
7. Use deterministic financial services for calculations. Do not let the LLM become the source of truth for financial arithmetic.
8. Keep the initial implementation modular and simple. Avoid unnecessary dependencies, premature microservices, or a large UI redesign.
9. Add focused tests for the runtime, tool validation, skill loading, and failure handling.
10. Do not modify production trading or live financial side-effect functionality.
Execution rules
- Work directly in the existing repository.
- Inspect only relevant files before modifying code.
- Make the smallest coherent implementation.
- Do not repeatedly reread the same files or loop on errors.
- Do not replace existing working systems without a concrete compatibility reason.
- If a dependency or architecture decision is unclear, use the existing project conventions first.
- Run focused checks after implementation.
- Report changed files, completed functionality, test results, and remaining limitations.
Start with the harness runtime and typed contracts. Implement the foundation first, then add a minimal working financial research tool call and skill-loading demonstration.





38. Final direction
My recommendation is to think of Eclipse as three connected products:
BlackEclipse
One platform, three complementary layers

Financial Intelligence
Markets · Data · Research · Analytics · Portfolio

Agentic Harness
Agents · Skills · Workflows · MCP · Memory · Code

Investor Environment
Command Center · Research Workspace · Terminal · Personal Automation


The harness should make the financial intelligence usable in many ways. The financial intelligence should make the harness genuinely valuable for investors. The interface should make the combined system understandable and useful.
The first objective is not to build the largest number of features. It is to establish a strong core that can support a growing ecosystem of financial tools, skills, agents, and workflows.
And yes—skills should become workflows, workflows should be reusable by agents, agents should be composable, and MCP should make Eclipse extensible beyond its own codebase.
That is the architecture I would pursue.
Bismillah. The first serious engineering step is the Harness Kernel + Tool Contract + Skill System. Once those three are solid, the rest of the platform has a foundation to grow on.








  







Monday 10:03 AM

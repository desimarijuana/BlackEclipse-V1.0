"""Finance presets and workflow templates (Phase 5 — product layer).

MCP should not be presented to an investor as a list of servers and tool names.
This module is the *task-oriented* layer on top of the raw MCP machinery:

  * **Integrations** — known finance-relevant servers with plain-language setup,
    what they are for, and exactly which secret/credential they need.
  * **Workflows** — named finance jobs ("Import Portfolio", "Prepare Earnings
    Brief", …) that say in plain words what they do, which integrations they use,
    which steps run, what they produce, and which steps need approval.

It is pure data + small helpers, deliberately free of I/O so it is trivially
testable and so the API/UI cannot disagree with the runtime about what a workflow
means. It never activates anything: a workflow is a plan the user reviews, not a
permission grant. Actual tool execution still goes through the one ToolRegistry
and its effect/approval gates.

Eclipse's native JDdS + portfolio data stay authoritative for a user's own
positions and Eclipse-retrieved market data. Integrations here are for data the
user owns elsewhere (spreadsheets, documents, decks) and for external research,
which is always labelled external and never Eclipse-verified.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Effect/approval language is shared with the runtime so the UI cannot claim a
# step is read-only when it is not.
EFFECT_READ = "read"
EFFECT_WRITE = "write"
EFFECT_EXTERNAL = "external_action"


@dataclass
class IntegrationSpec:
    """A finance-relevant MCP integration and how to set it up."""

    id: str
    label: str
    purpose: str
    category: str  # spreadsheets | research | calendar | documents | decks | notes
    transport: str  # "stdio" | "http"
    # Suggested launch values for a stdio server (never including a token).
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    url: Optional[str] = None
    # Auth / credential requirements, in plain language.
    secret_ref: Optional[str] = None  # suggested vault secret NAME
    secret_label: Optional[str] = None  # what the user must obtain
    requires_node: bool = False
    requires_python: bool = False
    # Tool-name hints (substrings) so a discovered catalog can be matched to the
    # integration and its read vs write tools classified for the user.
    read_tool_hints: list[str] = field(default_factory=list)
    write_tool_hints: list[str] = field(default_factory=list)
    # True when the integration is a community/third-party server whose quality
    # and data accuracy vary — surfaced honestly in the UI.
    community: bool = False
    # True only when the launch values below were confirmed against the package
    # registry. An unverified entry is a TEMPLATE the user must point at a real
    # server; the UI says so plainly.
    verified: bool = False
    notes: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowStep:
    """One step of a workflow, in plain language."""

    id: str
    title: str
    detail: str
    effect: str = EFFECT_READ  # read | write | external_action
    integration: Optional[str] = None  # IntegrationSpec.id, or None for native
    # True when this step uses Eclipse's own JDdS/portfolio data (authoritative).
    native_data: bool = False

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowSpec:
    """A named finance job the user recognises, not a raw tool."""

    id: str
    name: str
    summary: str
    category: str  # portfolio | research | earnings | journal | reporting
    integrations: list[str] = field(default_factory=list)  # IntegrationSpec ids
    steps: list[WorkflowStep] = field(default_factory=list)
    output: str = ""
    # Native-first: workflows that need the user's own positions are driven by
    # Eclipse's portfolio/JDdS data; integrations add imports/exports only.
    requires_native_portfolio: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "category": self.category,
            "integrations": list(self.integrations),
            "output": self.output,
            "requiresNativePortfolio": self.requires_native_portfolio,
            "steps": [s.to_public() for s in self.steps],
            "approvalSteps": [s.id for s in self.steps if s.effect != EFFECT_READ],
        }


# ── Integrations ─────────────────────────────────────────────────────────────
# Verified-installable entries only. Community servers are flagged; none ships
# enabled or selected — the user reviews and activates.
INTEGRATIONS: list[IntegrationSpec] = [
    IntegrationSpec(
        id="google_sheets",
        label="Google Sheets",
        purpose="Import holdings, watchlists, budgets and trade logs; export analysis tables.",
        category="spreadsheets",
        transport="stdio",
        command="npx",
        args=["-y", "mcp-google-sheets"],
        secret_ref="google_service_account_path",
        secret_label="Path to a Google service-account or OAuth JSON file with Sheets access",
        requires_node=True,
        read_tool_hints=["read", "get", "list", "search"],
        write_tool_hints=["write", "update", "append", "create", "set"],
        community=True,
        verified=True,
        notes="Community server (verified package). Eclipse's own watchlist/portfolio remain authoritative; this is for your existing sheets.",
    ),
    IntegrationSpec(
        id="excel",
        label="Excel files",
        purpose="Read and write local .xlsx models, holdings and trade logs.",
        category="spreadsheets",
        transport="stdio",
        command="npx",
        args=["-y", "@negokaz/excel-mcp-server"],
        requires_node=True,
        read_tool_hints=["read", "get", "list", "sheet"],
        write_tool_hints=["write", "update", "create", "set", "add"],
        community=True,
        verified=True,
    ),
    IntegrationSpec(
        id="filesystem",
        label="Local research files",
        purpose="Read filings, notes and exported CSVs stored on disk.",
        category="documents",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "."],
        requires_node=True,
        read_tool_hints=["read", "list", "search", "directory"],
        write_tool_hints=["write", "create", "edit", "move"],
        verified=True,
    ),
    IntegrationSpec(
        id="sec_filings",
        label="SEC / filings research",
        purpose="Retrieve company filings and compare changes between them.",
        category="research",
        transport="http",
        url="https://mcp.example.com/sec/mcp",
        secret_ref="sec_filings_token",
        secret_label="API token for your SEC/filings MCP server",
        read_tool_hints=["filing", "search", "fetch", "read", "get"],
        write_tool_hints=["create", "write"],
        notes="Template (UNVERIFIED): point this at a filings MCP server you trust. Eclipse's own SEC route stays native.",
    ),
    IntegrationSpec(
        id="web_search",
        label="Web search (Tavily)",
        purpose="Independent web research and page extraction for context and news.",
        category="research",
        transport="stdio",
        command="npx",
        args=["-y", "tavily-mcp"],
        secret_ref="tavily_api_key",
        secret_label="Tavily API key (tavily.com)",
        requires_node=True,
        read_tool_hints=["search", "extract", "crawl", "map"],
        write_tool_hints=[],
        verified=True,
    ),
    IntegrationSpec(
        id="calendar",
        label="Calendar & releases",
        purpose="Track earnings dates, Fed meetings and economic releases.",
        category="calendar",
        transport="http",
        url="https://mcp.example.com/calendar/mcp",
        secret_ref="calendar_token",
        secret_label="API token for your calendar / economic-calendar MCP server",
        read_tool_hints=["list", "get", "event", "search", "calendar"],
        write_tool_hints=["create", "add", "update"],
        notes="Template (UNVERIFIED): Eclipse's native economic calendar remains the built-in source.",
    ),
    IntegrationSpec(
        id="dropbox",
        label="Dropbox / Box / SharePoint",
        purpose="Search research PDFs and broker documents in your cloud drive.",
        category="documents",
        transport="http",
        url="https://mcp.example.com/drive/mcp",
        secret_ref="drive_token",
        secret_label="Access token for your document-store MCP server",
        read_tool_hints=["search", "read", "list", "download", "get"],
        write_tool_hints=["upload", "create", "move", "delete"],
        notes="Template (UNVERIFIED): point this at the document-store MCP server you use.",
    ),
    IntegrationSpec(
        id="canva",
        label="Canva",
        purpose="Create investment memos, portfolio reviews and earnings decks.",
        category="decks",
        transport="http",
        url="https://mcp.canva.com/mcp",
        secret_ref="canva_token",
        secret_label="Canva access token / OAuth connection",
        read_tool_hints=["list", "get", "search"],
        write_tool_hints=["create", "generate", "design", "upload"],
        notes="Template (UNVERIFIED): Canva is remote/OAuth-only. Presentation layer only — numbers in a deck still come from Eclipse/native evidence, not the tool.",
    ),
    IntegrationSpec(
        id="figma",
        label="Figma",
        purpose="Create presentation boards and diagram a thesis or portfolio map.",
        category="decks",
        transport="http",
        url="https://mcp.figma.com/mcp",
        secret_ref="figma_token",
        secret_label="Figma personal access token",
        read_tool_hints=["get", "list"],
        write_tool_hints=["create", "update", "write"],
        notes="Template (UNVERIFIED): remote/design layer only.",
    ),
    IntegrationSpec(
        id="powerpoint",
        label="Word / Excel / PowerPoint (Office)",
        purpose="Create investment memos, portfolio reviews and earnings decks (.pptx/.docx/.xlsx).",
        category="decks",
        transport="stdio",
        command="npx",
        args=["-y", "@mindstone/mcp-server-office"],
        requires_node=True,
        read_tool_hints=["read", "get", "list"],
        write_tool_hints=["create", "write", "add", "update"],
        verified=True,
        notes="Community server (verified package). Writes a local Office file — needs approval.",
    ),
    IntegrationSpec(
        id="notion",
        label="Notion",
        purpose="Save theses, decisions and research records as durable notes.",
        category="notes",
        transport="stdio",
        command="npx",
        args=["-y", "@notionhq/notion-mcp-server"],
        secret_ref="notion_integration_token",
        secret_label="Notion internal integration token",
        requires_node=True,
        read_tool_hints=["search", "get", "retrieve", "list"],
        write_tool_hints=["create", "append", "update", "post"],
        verified=True,
    ),
]

INTEGRATIONS_BY_ID = {i.id: i for i in INTEGRATIONS}


# ── Workflows ────────────────────────────────────────────────────────────────
def _step(id: str, title: str, detail: str, *, effect: str = EFFECT_READ,
          integration: Optional[str] = None, native: bool = False) -> WorkflowStep:
    return WorkflowStep(id=id, title=title, detail=detail, effect=effect,
                        integration=integration, native_data=native)


WORKFLOWS: list[WorkflowSpec] = [
    WorkflowSpec(
        id="import_portfolio",
        name="Import Portfolio",
        summary="Import holdings, watchlists or a trade log from a spreadsheet into Eclipse.",
        category="portfolio",
        integrations=["google_sheets", "excel", "filesystem"],
        requires_native_portfolio=True,
        output="Holdings/watchlist rows read from your sheet or file, ready to review and import.",
        steps=[
            _step("read_source", "Read your source file", "Read the selected sheet/workbook/file (read-only).", integration="google_sheets"),
            _step("map_columns", "Map columns", "Match your columns to Eclipse's portfolio schema.", native=True),
            _step("verify_identity", "Verify instruments", "Resolve each ticker against Eclipse's instrument master (native, authoritative).", native=True),
            _step("stage_rows", "Stage the import", "Show what will be imported before anything is written.", native=True),
        ],
    ),
    WorkflowSpec(
        id="review_portfolio_risk",
        name="Review Portfolio Risk",
        summary="Analyse concentrations, exposures and drawdown for your Eclipse portfolio.",
        category="portfolio",
        integrations=[],
        requires_native_portfolio=True,
        output="A risk review computed from Eclipse's authoritative portfolio + JDdS data.",
        steps=[
            _step("load_portfolio", "Load your portfolio", "Use Eclipse's own portfolio holdings (native, authoritative).", native=True),
            _step("load_market", "Load market data", "Retrieve prices/history through Eclipse's native retrieval layer.", native=True),
            _step("compute_risk", "Compute risk", "Run Eclipse's deterministic risk/correlation math.", native=True),
            _step("summarise", "Summarise", "Explain the result and its limitations.", native=True),
        ],
    ),
    WorkflowSpec(
        id="prepare_earnings_brief",
        name="Prepare Earnings Brief",
        summary="Prepare a sourced brief for an upcoming or recent earnings event.",
        category="earnings",
        integrations=["sec_filings", "web_search", "calendar", "filesystem"],
        output="A sourced brief: the event, key figures with provenance, and open questions.",
        steps=[
            _step("find_event", "Find the earnings date", "Check the calendar for the next/actual report date.", integration="calendar"),
            _step("retrieve_filings", "Retrieve filings/statements", "Get the latest filing/statements (native first, filings server as an external route).", integration="sec_filings"),
            _step("external_context", "Gather commentary", "Independent web search for context and guidance (external, labelled).", integration="web_search"),
            _step("compose_brief", "Compose the brief", "Cite each material figure with source, date and verification state.", native=True),
        ],
    ),
    WorkflowSpec(
        id="compare_companies",
        name="Compare Companies",
        summary="Compare two companies on the metrics you choose.",
        category="research",
        integrations=["sec_filings", "web_search"],
        output="A side-by-side comparison with per-figure provenance and explicit gaps.",
        steps=[
            _step("define_metrics", "Define metrics & periods", "Agree on periods, currency, units and accounting basis.", native=True),
            _step("retrieve_both", "Retrieve both companies", "Native retrieval first; filings server as an external route.", integration="sec_filings"),
            _step("check_comparability", "Check comparability", "Block incompatible comparisons with the exact reason (native gate).", native=True),
            _step("render_comparison", "Render the comparison", "Report each figure with its source and freshness.", native=True),
        ],
    ),
    WorkflowSpec(
        id="analyze_trade_journal",
        name="Analyze Trade Journal",
        summary="Read your trade log and analyse performance, patterns and mistakes.",
        category="journal",
        integrations=["google_sheets", "excel", "filesystem"],
        requires_native_portfolio=True,
        output="Journal analytics from your trade history plus a plain-language review.",
        steps=[
            _step("read_trades", "Read your trade log", "Read trades from a sheet/workbook/file (read-only).", integration="google_sheets"),
            _step("import_journal", "Import into Eclipse", "Load trades into Eclipse's journal (native).", native=True),
            _step("compute_analytics", "Compute analytics", "Win rate, expectancy, drawdown and patterns (native math).", native=True),
            _step("review", "Review", "Summarise what worked, what did not, and why.", native=True),
        ],
    ),
    WorkflowSpec(
        id="create_investment_memo",
        name="Create Investment Memo",
        summary="Produce an investment memo from Eclipse research and your saved notes.",
        category="reporting",
        integrations=["notion", "web_search", "canva", "figma", "powerpoint"],
        output="A structured memo, optionally saved to Notion and/or exported as a deck.",
        steps=[
            _step("gather", "Gather findings", "Collect Eclipse research + selected evidence.", native=True),
            _step("draft", "Draft the memo", "Write thesis, evidence, risks and limitations.", native=True),
            _step("save_thesis", "Save the thesis", "Save to Notion as a durable research record.", effect=EFFECT_WRITE, integration="notion"),
            _step("export_deck", "Export a deck", "Create a presentation in Canva/Figma/PowerPoint.", effect=EFFECT_WRITE, integration="canva"),
        ],
    ),
    WorkflowSpec(
        id="export_portfolio_report",
        name="Export Portfolio Report",
        summary="Export a portfolio review to a spreadsheet or presentation.",
        category="reporting",
        integrations=["google_sheets", "excel", "powerpoint", "canva"],
        requires_native_portfolio=True,
        output="A report written to your sheet/workbook or a generated deck.",
        steps=[
            _step("build_report", "Build the report", "Assemble holdings, performance and risk from Eclipse data.", native=True),
            _step("export_table", "Export the table", "Write the report table to Sheets/Excel.", effect=EFFECT_WRITE, integration="google_sheets"),
            _step("export_deck", "Export a deck", "Create a portfolio-review deck.", effect=EFFECT_WRITE, integration="powerpoint"),
        ],
    ),
]

WORKFLOWS_BY_ID = {w.id: w for w in WORKFLOWS}


def list_integrations() -> list[dict[str, Any]]:
    return [i.to_public() for i in INTEGRATIONS]


def list_workflows() -> list[dict[str, Any]]:
    return [w.to_public() for w in WORKFLOWS]


def integration(integration_id: str) -> Optional[IntegrationSpec]:
    return INTEGRATIONS_BY_ID.get(integration_id)


def workflow(workflow_id: str) -> Optional[WorkflowSpec]:
    return WORKFLOWS_BY_ID.get(workflow_id)


def workflows_for_server_tools(tool_names: list[str]) -> list[str]:
    """Which integration ids a discovered catalog plausibly satisfies.

    Matches on the read/write tool-name hints. Honest about uncertainty: it
    returns candidates, never a claim that a server *is* an integration.
    """
    lowered = [t.lower() for t in tool_names]
    matched: list[str] = []
    for spec in INTEGRATIONS:
        hints = [h.lower() for h in (*spec.read_tool_hints, *spec.write_tool_hints)]
        if any(h in name for name in lowered for h in hints):
            matched.append(spec.id)
    return matched


def classify_tool_effect_hint(tool_name: str) -> str:
    """A *hint* at a tool's effect from its name (never authoritative).

    Used only to pre-fill the UI; the authoritative effect still comes from the
    operator declaration / catalog confirmation in the manager.
    """
    name = tool_name.lower()
    write_words = ("write", "update", "create", "append", "delete", "remove", "upload",
                   "move", "set", "add", "edit", "post", "send", "execute", "run",
                   "export", "insert", "put", "patch", "publish", "share", "generate")
    read_words = ("read", "get", "list", "search", "retrieve", "fetch", "query", "download", "preview")
    if any(w in name for w in write_words):
        return EFFECT_WRITE
    if any(w in name for w in read_words):
        return EFFECT_READ
    return "unknown"


__all__ = [
    "IntegrationSpec",
    "WorkflowSpec",
    "WorkflowStep",
    "INTEGRATIONS",
    "WORKFLOWS",
    "list_integrations",
    "list_workflows",
    "integration",
    "workflow",
    "workflows_for_server_tools",
    "classify_tool_effect_hint",
    "EFFECT_READ",
    "EFFECT_WRITE",
    "EFFECT_EXTERNAL",
]

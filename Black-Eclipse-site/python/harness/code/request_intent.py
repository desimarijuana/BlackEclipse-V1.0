"""The deterministic chat code-request classifier (Phase 14 §6.1).

Decides whether an ordinary chat turn is a request to CHANGE software or to
work on DATA (or a question about either), so the front door can hand the turn
the narrow chat code profile or activate the analysis sandbox. It is pure,
deterministic code with NO model call — a model's opinion cannot grant a
capability (ADR-H117, roadmap §3.1/§3.2).

Bias: a wrong `code_change` hands the turn a narrow, workspace-confined tool set;
a wrong `data_task` only ACTIVATES the analysis sandbox on the ordinary finance
surface (additive, no widening), and a wrong `not_code` answers a constructible
request with finance tools and refuses honestly. An ambiguous turn is still
`not_code` — the refusal path remains the safe failure — but an explicit data
signal routes to `data_task`, so Eclipse computes instead of refusing.

This module imports nothing from `graph.py` (it is a leaf), so it can be tested
and called independently of the run loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

IntentVerdict = Literal["code_change", "code_question", "data_task", "app_control", "not_code"]
Confidence = Literal["certain", "likely"]

# A directive verb. It must sit in the SAME clause as a software object.
_DIRECTIVE_VERBS = (
    "build", "create", "add", "fix", "refactor", "rename", "delete", "remove",
    "test", "run", "implement", "write", "update", "change", "modify", "make",
    "move", "edit", "wire", "hook", "patch", "repair", "debug", "upgrade",
    "generate", "rewrite", "extract", "support", "handle", "convert", "migrate",
    # file-system style directives: without them, "count the files on my desktop"
    # classified as not_code and the user saw a refusal of all tools.
    "count", "list", "show", "display", "view", "open", "inspect", "scan",
    "search", "find", "read", "pull up", "check",
    # software acquisition: "download and install X" is work on the machine.
    # "download the prices" is unaffected — a data object with no software
    # object still routes to `data_task`.
    "install", "uninstall", "download", "set up", "setup",
)

# Acquisition verbs strong enough to stand alone: "install X" has no finance
# reading, so no software object is required. Kept separate from
# `_DIRECTIVE_VERBS` so "download the prices" still routes to `data_task`.
_STRONG_ACQUIRE_VERBS = ("install", "uninstall")

# A software object — a thing a code change acts on. Concrete on purpose: a
# vague finance noun ("report", "portfolio", "watchlist") is NOT here, so
# "build me a report" stays `not_code`. But the product's own reason to exist
# ("create a new application", "build algorithms", "write a backtest") IS here;
# omitting those made the classifier answer the user's literal wish with
# `not_code` — the very refusal this phase exists to remove.
_SOFTWARE_OBJECTS = (
    "file", "function", "method", "component", "endpoint", "api", "route",
    "handler", "test", "tests", "script", "feature", "bug", "type error",
    "typeerror", "class", "module", "interface", "variable", "import",
    "config", "configuration", "migration", "schema", "page", "button", "form",
    "parser", "service", "hook", "utility", "utils", "library", "package",
    "dependency", "exception", "stack trace", "traceback", "code",
    "regex", "regexp", "template", "widget", "check", "checks", "linter",
    "compiler", "server", "client", "database", "query", "sql", "css", "html",
    "reducer", "prop", "props", "build",
    # Things the user asks Eclipse to build (the "create applications / build
    # algorithms" complaint). Each is a software artifact, not a finance fact.
    "application", "app", "algorithm", "algorithms", "dashboard", "tool",
    "pipeline", "backtest", "simulator", "simulation", "bot", "cli",
    "screener", "screen", "indicator", "automation", "integration",
    "plugin", "extension", "backend", "frontend", "ui", "report generator",
    "tracker", "chart", "scraper",
    # software a user downloads or installs, and the skill it may arrive as
    "software", "program", "executable", "installer", "binary",
    "skill", "skills",
    # places a user asks the agent to read/write in
    "desktop", "desktop folder", "folder", "directory", "files", "file system",
    "filesystem", "path", "website", "web site",
)

# A data-work verb names work on DATA — extracting, cleaning, transforming,
# computing — rather than on software. Kept separate from `_DIRECTIVE_VERBS` so
# "show the data" stays an ordinary retrieval ask. This verdict does NOT widen
# the tool surface: it activates the analysis sandbox for the turn.
_DATA_VERBS = (
    "scrape", "crawl", "extract", "clean", "cleanse", "transform", "convert",
    "parse", "collect", "download", "export", "import", "merge", "join",
    "dedupe", "deduplicate", "normalize", "normalise", "wrangle", "resample",
    "simulate", "compute", "calculate", "aggregate", "reconcile",
    "plot", "chart", "visualize", "visualise",
    # Computation/analysis verbs ("analyze the drawdown", "backtest this
    # strategy") — work the deterministic analysis sandbox exists to do.
    "analyze", "analyse", "backtest", "optimize", "optimise",
    "annualize", "annualise", "stress-test",
)

# A data object — a thing data work acts on. Deliberately narrower than every
# finance noun: "report", "portfolio" and "watchlist" are NOT here, so a display
# ask like "show me the data" stays `not_code`; but a COMPUTATION ask ("compute
# the YTD return") names a metric and is a data task.
_DATA_OBJECTS = (
    "data", "dataset", "datasets", "data set", "csv", "excel", "xlsx", "xls",
    "spreadsheet", "sheet", "workbook", "json", "xml", "parquet", "dataframe",
    "table", "tables", "file", "files", "records", "entries", "rows", "columns",
    "series", "time series", "history", "prices", "price history", "ohlcv",
    "candles", "ticks", "returns", "drawdown", "correlation", "covariance",
    "volatility", "ratio", "ratios", "metric", "metrics", "sharpe", "sortino",
    "number", "numbers", "value", "values",
    # Finance-computation metrics observed in live asks ("AAPL 11,551 bars" →
    # YTD refused with ANALYSIS_NOT_ENABLED because no object matched).
    "ytd", "year to date", "return", "performance", "cagr", "alpha", "beta",
    "exposure", "allocation", "holdings",
    "site", "website", "web site", "webpage", "web page", "url", "page",
)

# Distinctive phrases that are data work on their own, with any directive
# ("run a Monte Carlo" is not a software object, but it is work to construct).
_DATA_PHRASES = (
    "monte carlo", "monte-carlo",
    # A report/analysis OF something is computation, not a software change
    # ("run a report on my portfolio"). "report" alone stays a finance noun.
    "an analysis", "analysis of", "analyses of", "a report on", "a report of",
)

# A question ABOUT code is read-only. These openers plus a software object (or a
# pasted path) classify as `code_question`.
_QUESTION_OPENERS = (
    "how", "how would", "how do", "how does", "what's", "what is", "whats",
    "what does", "what do", "what are", "what is wrong", "what's wrong",
    "why", "where", "when", "which", "who",
    "can you tell me", "can you explain", "could you explain", "explain",
    "is there", "are there", "does",
)

# A bug report: a symptom the user reports, with a software object or a path in
# the turn. "the app crashes when I click" is a request to fix code, not a
# finance question; "the market crashed" is not (no software object).
_SYMPTOMS = (
    "crashes", "crash", "crashed", "doesn't work", "does not work",
    "isn't working", "is not working", "won't work", "will not work",
    "broken", "is broken", "fails", "failing", "is failing", "throws",
    "won't compile", "doesn't compile", "won't build", "doesn't build",
    "errors out", "goes wrong", "returning an error", "not loading",
    # A named exception/error. The regex is bounded to a bare type token + the
    # word "error" so an ordinary prose "errors" does not match.
    "typeerror", "valueerror", "keyerror", "indexerror", "attributeerror",
    "null pointer", "stack overflow", "segfault",
)
_NAMED_ERROR_RE = re.compile(
    r"(?:[A-Z][A-Za-z]+Error|TypeError|AttributeError|KeyError|IndexError|"
    r"NullPointer\w*|\b\d{3}\b\s+error)",
)

# A follow-up to a prior coding turn.
_FOLLOW_UPS = (
    "do it", "do that", "yes", "yes please", "yes go ahead", "go ahead",
    "go for it", "proceed", "continue", "please do", "make it so", "sounds good",
)

_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\.{0,2}[\\/])?[\w.-]+[\\/][\w./\\-]+"
    r"\.(?:py|ts|tsx|js|jsx|json|md|css|html|sql|yml|yaml|toml|sh)\b",
    re.IGNORECASE,
)
_STACK_TRACE_RE = re.compile(
    r"(traceback \(most recent call last\)|^\s+file \"[^\"]+\", line \d+|"
    r"\w*error:\s.+\n\s+at\s|^\s+at\s+[\w.$]+\([^)]*:\d+:\d+\))",
    re.IGNORECASE | re.MULTILINE,
)
# A trailing document extension names a project file ("update the README",
# "update the docs"), a change request — not the finance noun "report".
_DOC_OBJECTS = ("readme", "changelog", "docs", "documentation", "docstring")
_CLAUSE_SPLIT_RE = re.compile(r"[.!?;\n]+|\bthen\b|\band\b|\bbut\b", re.IGNORECASE)

_APP_CONTROL_ACTIONS = _DIRECTIVE_VERBS + (
    "apply", "restyle", "style", "lock", "unlock", "save", "reset", "set", "switch",
    "hide", "reorder", "rearrange", "organize", "organise", "customize", "customise",
    "pin", "unpin", "enable", "disable",
)
_APP_CONTROL_STRONG_SURFACES = (
    "command center", "dashboard layout", "layout", "layouts", "board", "boards",
    "theme", "themes", "color scheme", "colour scheme", "dark mode", "light mode",
    "sidebar", "navigation", "nav", "watchlist", "columns", "column", "zones", "zone",
    "preset", "presets",
)
_APP_CONTROL_CODE_ONLY = (
    "react", "tsx", "typescript", "source code", "the source", "edit the source",
    "new widget kind", "new kind of widget", "new widget type", "new kind",
    "renderer", "dependency", "codebase", "implementation", "bug", "compile",
    "refactor", "backend", "frontend", "unit test", "unit tests",
)
_APP_CONTROL_DASHBOARD_RE = re.compile(
    r"\b(my|the|this|active|current)\s+(command center|dashboard)\b", re.IGNORECASE,
)
_APP_CONTROL_FOLLOW_UP_RE = re.compile(
    r"^(save|keep|store|name|call)\s+(this|it|that)(\s+as\s+.+)?[.!]?$", re.IGNORECASE,
)


@dataclass(frozen=True)
class CodeIntent:
    """The classifier's verdict. `confidence` is never a float and never shown."""

    verdict: IntentVerdict
    confidence: Confidence
    reason: str
    signals: tuple[str, ...]


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    for word in words:
        if " " in word:
            if word in lowered:
                return True
        elif re.search(rf"(^|[^a-z0-9]){re.escape(word)}([^a-z0-9]|$)", lowered):
            return True
    return False


def _matched_terms(text: str, words: tuple[str, ...]) -> set[str]:
    """The set of dictionary terms that occur in `text` (whole-word)."""
    lowered = text.casefold()
    found: set[str] = set()
    for word in words:
        if " " in word:
            if word in lowered:
                found.add(word)
        elif re.search(rf"(^|[^a-z0-9]){re.escape(word)}([^a-z0-9]|$)", lowered):
            found.add(word)
    return found


def _has_directive_and_object(clause: str) -> bool:
    """A directive verb and a software object in the SAME clause.

    The object must be a word the directive does NOT already supply. Several
    terms are both a verb and a noun ("test", "build", "run", "check"); without
    this guard "test the market" matched `test` as both and misread a finance
    question as a code change.
    """
    verbs = _matched_terms(clause, _DIRECTIVE_VERBS)
    if not verbs:
        return False
    objects = _matched_terms(clause, _SOFTWARE_OBJECTS)
    return bool(objects - verbs)


def _has_data_work(clause: str) -> bool:
    """Data work in ONE clause: a data verb + a data object (or distinctive
    phrase); or a distinctive phrase + any directive verb ("run a Monte Carlo").
    A bare data verb with no object ("clean it up") is too vague — `not_code`.
    """
    verbs = _matched_terms(clause, _DATA_VERBS)
    if verbs and (
        _matched_terms(clause, _DATA_OBJECTS)
        or _matched_terms(clause, _DATA_PHRASES)
    ):
        return True
    return bool(
        _matched_terms(clause, _DATA_PHRASES)
        and _matched_terms(clause, _DIRECTIVE_VERBS)
    )


def _last_user_turn(history: Optional[list[dict]]) -> Optional[str]:
    if not history:
        return None
    for turn in reversed(history):
        if not isinstance(turn, dict):
            continue
        if turn.get("role") != "user":
            continue
        content = turn.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def _looks_like_app_control(text: str) -> bool:
    lowered = text.casefold()
    if _has_word(text, _APP_CONTROL_CODE_ONLY):
        return False
    has_dashboard = bool(_APP_CONTROL_DASHBOARD_RE.search(lowered))
    has_surface = has_dashboard or _has_word(text, _APP_CONTROL_STRONG_SURFACES)
    if not has_surface and "page" in lowered:
        has_surface = _has_word(text, ("nav", "navigation", "sidebar", "called"))
    return has_surface and _has_word(text, _APP_CONTROL_ACTIONS)


def _is_question(text: str) -> bool:
    lowered = text.casefold().strip()
    if lowered.endswith("?"):
        return True
    # An opener only counts at the START of the turn (or right after a clause
    # boundary): "where it breaks" inside a statement must not turn a pasted path
    # into a question.
    for clause in _CLAUSE_SPLIT_RE.split(lowered):
        head = clause.strip()
        if not head:
            continue
        if any(head.startswith(opener) for opener in _QUESTION_OPENERS):
            return True
        break  # only the first non-empty clause decides the opener
    return False


def _verdict(
    verdict: IntentVerdict,
    confidence: Confidence,
    reason: str,
    signals: tuple[str, ...],
) -> CodeIntent:
    return CodeIntent(verdict=verdict, confidence=confidence, reason=reason, signals=signals)


def classify_code_request(
    query: str, history: Optional[list[dict]] = None,
) -> CodeIntent:
    """Decide whether a chat turn is a request to CHANGE software.

    Rules (deterministic, no model call):
      * a directive verb + a software object in the SAME clause
      * a pasted path or a stack trace
      * data work (a data verb + a data object) ⇒ `data_task`, which activates
        the analysis sandbox on the ordinary finance surface — additive
      * a follow-up ("do it") whose PREVIOUS user turn was `code_change` or
        `data_task`
      * a question ("how would you…", "what's wrong with…") ⇒ `code_question`
    """
    text = (query or "").strip()
    if not text:
        return _verdict("not_code", "certain", "The turn was empty.", ("empty",))

    # A question about code is read-only — checked FIRST, so a question that
    # merely mentions a path or a verb is not mistaken for a change.
    if _is_question(text):
        if _has_word(text, _SOFTWARE_OBJECTS) or _PATH_RE.search(text):
            return _verdict(
                "code_question", "likely",
                "The turn asks about code, so the answer may read it.",
                ("question", "software_object"),
            )
        return _verdict("not_code", "certain", "The turn is a question, not a request to change software.", ("question",))

    # A pasted path or a stack trace is an unambiguous change request.
    if _STACK_TRACE_RE.search(text):
        return _verdict(
            "code_change", "certain",
            "The turn pastes an error trace, so something needs changing.",
            ("stack_trace",),
        )
    if _PATH_RE.search(text):
        return _verdict(
            "code_change", "certain",
            "The turn names a project path, so a change is likely wanted.",
            ("pasted_path",),
        )

    if _looks_like_app_control(text):
        return _verdict(
            "app_control", "certain",
            "The turn controls an Eclipse app surface, so the SDK tools serve it.",
            ("app_control", "app_surface"),
        )

    if _APP_CONTROL_FOLLOW_UP_RE.match(text.strip()):
        previous = _last_user_turn(history)
        if previous:
            prior = classify_code_request(previous, history=_history_before(history))
            if prior.verdict == "app_control":
                return _verdict(
                    "app_control", "likely",
                    "This continues an earlier request to control an Eclipse app surface.",
                    ("follow_up", "app_control"),
                )

    # A directive + software object in the SAME clause.
    clauses = [c for c in _CLAUSE_SPLIT_RE.split(text) if c.strip()]
    for clause in clauses:
        if _has_directive_and_object(clause):
            return _verdict(
                "code_change", "certain",
                "The turn asks for a software change.",
                ("directive+software_object",),
            )

    # A directive + a project document ("update the README", "update the docs").
    for clause in clauses:
        if _has_word(clause, _DIRECTIVE_VERBS) and _has_word(clause, _DOC_OBJECTS):
            return _verdict(
                "code_change", "certain",
                "The turn asks to change a project document.",
                ("directive+doc_object",),
            )

    # A bare STRONG acquisition verb ("install blender", "uninstall foo") is
    # itself a code change — there is no finance reading of "install X". Weaker
    # acquisition words ("download", "set up") still need a software object, so
    # "download the prices" keeps routing to `data_task`.
    for clause in clauses:
        if _matched_terms(clause, _STRONG_ACQUIRE_VERBS):
            return _verdict(
                "code_change", "likely",
                "The turn asks to install or remove software.",
                ("acquire",),
            )

    # A reported symptom with a software object or a path ("the app crashes when
    # I click"). A symptom alone ("the market crashed") is not a code request.
    # A NAMED error/exception ("it says TypeError on line 5") is itself enough:
    # it can only come from running software.
    if (_has_word(text, _SYMPTOMS) and (
            _has_word(text, _SOFTWARE_OBJECTS) or _PATH_RE.search(text))) \
            or _NAMED_ERROR_RE.search(text):
        return _verdict(
            "code_change", "likely",
            "The turn reports something broken in software.",
            ("symptom",),
        )

    # Data work — extracting, scraping, cleaning, transforming, computing. The
    # verdict does NOT widen the tool surface: it activates the analysis sandbox
    # for the turn, so Eclipse can construct the result instead of refusing.
    for clause in clauses:
        if _has_data_work(clause):
            return _verdict(
                "data_task", "certain",
                "The turn asks for work on data, so the analysis sandbox is available.",
                ("data_work",),
            )

    # A follow-up to a prior coding or data turn. The previous USER turn is
    # classified recursively (bounded depth) so a chain of "do it" stays correct.
    if _has_word(text, _FOLLOW_UPS):
        previous = _last_user_turn(history)
        if previous:
            prior = classify_code_request(previous, history=_history_before(history))
            if prior.verdict == "code_change":
                return _verdict(
                    "code_change", "likely",
                    "This continues an earlier request to change software.",
                    ("follow_up",),
                )
            if prior.verdict == "data_task":
                return _verdict(
                    "data_task", "likely",
                    "This continues an earlier request to work on data.",
                    ("follow_up",),
                )
            if prior.verdict == "app_control":
                return _verdict(
                    "app_control", "likely",
                    "This continues an earlier request to control an Eclipse app surface.",
                    ("follow_up", "app_control"),
                )
        return _verdict("not_code", "certain", "The turn alone does not ask to change software.", ("follow_up",))

    return _verdict(
        "not_code", "certain",
        "The turn is ambiguous or not about software, so it stays on the ordinary path.",
        ("ambiguous",),
    )


def _history_before(history: Optional[list[dict]]) -> Optional[list[dict]]:
    """The history with its LAST user turn removed, so a follow-up chain is bounded."""
    if not history:
        return None
    for index in range(len(history) - 1, -1, -1):
        turn = history[index]
        if isinstance(turn, dict) and turn.get("role") == "user":
            return list(history[:index])
    return None


__all__ = ["CodeIntent", "IntentVerdict", "classify_code_request"]

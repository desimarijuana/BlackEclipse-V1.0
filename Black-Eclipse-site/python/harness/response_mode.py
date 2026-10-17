"""The Intelligent Response Orchestrator — the deterministic response-mode planner.

The Interactive Response Engine already lets the model emit structured
`eclipse-response` blocks, so *whether* an answer can be visual is solved. What
was missing is a decision layer: nothing classified a turn and chose HOW to
present it. In practice the model volunteered a fence or it did not, and a
deterministic post-planner only upgraded Markdown tables/source lists.

This module is that missing decision layer. Given the user's turn (and, for a
follow-up, the prior mode), it selects ONE presentation mode —

  * `text`          — plain prose; simple questions and chat (the safe default)
  * `explanation`   — teach/explain: stepper, details, comparison, diagram
  * `visualization` — real data to plot: chart, financial_chart, table, metrics
  * `simulation`    — what-if / parameters / backtests: controls + results
  * `workflow`      — agent/plan/execution: workflow, flow, node_graph, timeline
  * `composite`     — two or more of the above genuinely apply

— and produces a compact prompt directive that steers the model toward the right
structure. It is PURE, deterministic code with NO model call (mirroring
`code/request_intent.py`): a model's opinion cannot force a presentation, and the
planner can be tested independently of the run loop. It never mandates structure
— a simple request still answers as prose — and it never fabricates data.

Bias: when the signals are ambiguous the verdict is `text`. The rich modes are
chosen only on distinctive, unambiguous signals, because a forced widget is a
worse failure than a plain answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

ResponseMode = Literal[
    "text", "explanation", "visualization", "simulation", "workflow", "composite",
]
Confidence = Literal["certain", "likely", "unsure"]

# The order rich modes are considered when several are matched (specific first).
_MODE_ORDER: tuple[str, ...] = (
    "workflow", "simulation", "visualization", "explanation",
)
# The modes that imply data/tool work: a composite answer is only proposed when a
# data-bearing mode co-occurs with another real mode.
_DATA_MODES = frozenset({"workflow", "simulation", "visualization"})

# ── signal vocabularies (whole-word matched unless the term holds a space) ─────

# Agent / plan / execution / debugging. A diagnostic turn ("why did my agent
# fail?") is a process question, not a data one.
_WORKFLOW_TERMS = (
    "agent", "agents", "subagent", "subagents", "multi-agent", "delegate",
    "delegation", "workflow", "orchestration", "orchestrator", "dependency",
    "dependencies", "dag", "tool call", "tool calls", "failed step",
    "execution trace", "pipeline", "escalation",
)

# What-if / parameter / backtest questions: the answer is a computation the user
# should be able to drive.
_SIMULATION_TERMS = (
    "backtest", "back-test", "backtested", "simulate", "simulation",
    "monte carlo", "monte-carlo", "scenario", "scenarios", "what-if", "what if",
    "walk-forward", "walkforward", "walk forward", "optimize", "optimise",
    "optimization", "optimisation", "stress test", "stress-test", "sensitivity",
    "projection", "if i change", "if we change", "if you change",
)

# Data to be seen: charts, comparisons, distributions, market metrics.
_VISUALIZATION_TERMS = (
    "chart", "charts", "graph", "graphs", "plot", "plots", "compare",
    "comparison", "versus", "vs", "correlation", "heatmap", "heat map",
    "distribution", "drawdown", "equity curve", "time series", "timeseries",
    "trend", "trends", "visualize", "visualise", "breakdown", "ranking",
    "leaderboard", "allocation", "exposure", "performance",
)

# Teaching and explanation. Deliberately about EXPLAINING, not about generic
# interrogatives: "what is the price of AAPL" is a lookup (text), not a
# walkthrough. "explain RSI" / "how does RSI work" / "teach me Python" are not.
_EXPLANATION_TERMS = (
    "explain", "explanation", "teach me", "teach", "tutorial", "walk me through",
    "walk through", "difference between", "help me understand", "how does",
    "how do", "learn", "learning", "roadmap", "curriculum", "study plan",
)

# A learning request is an explanation whose best shape is `learning_map`.
_LEARNING_TERMS = (
    "teach", "teach me", "tutorial", "learn", "learning", "roadmap",
    "curriculum", "study plan", "lesson", "course",
)

# Conversational openers/closers: never a rich mode even if a stray term matches.
_GREETING_TERMS = (
    "hi", "hello", "hey", "yo", "thanks", "thank you", "good morning",
    "good afternoon", "good evening", "bye", "goodbye", "ok", "okay", "cool",
    "nice", "great",
)

# A short follow-up that inherits the PREVIOUS user turn's mode.
_FOLLOW_UPS = (
    "do it", "do that", "go ahead", "go for it", "proceed", "continue",
    "please do", "sounds good", "and then", "what about",
)

_CLAUSE_SPLIT_RE = re.compile(r"[.!?;\n]+|\bthen\b|\band\b|\bbut\b", re.IGNORECASE)
_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


@dataclass(frozen=True)
class ResponsePlan:
    """The planner's verdict. `confidence` is never a float and never shown."""

    mode: ResponseMode
    confidence: Confidence
    reason: str
    signals: tuple[str, ...]
    suggested_blocks: tuple[str, ...] = ()
    learning: bool = False

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe record (for the `response.plan` run event)."""
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "reason": self.reason,
            "signals": list(self.signals),
            "suggestedBlocks": list(self.suggested_blocks),
            "learning": self.learning,
        }


def _word_re(word: str) -> re.Pattern[str]:
    cached = _WORD_RE_CACHE.get(word)
    if cached is None:
        cached = re.compile(rf"(^|[^a-z0-9]){re.escape(word)}([^a-z0-9]|$)")
        _WORD_RE_CACHE[word] = cached
    return cached


def _matched_terms(text: str, terms: tuple[str, ...]) -> set[str]:
    """The set of dictionary terms that occur in `text` (whole-word)."""
    lowered = text.casefold()
    found: set[str] = set()
    for term in terms:
        if " " in term or "-" in term:
            if term in lowered:
                found.add(term)
        elif _word_re(term).search(lowered):
            found.add(term)
    return found


def _turn_role_content(turn: Any) -> Optional[tuple[str, str]]:
    """Read `(role, content)` from a dict or an object (schemas.ConversationTurn)."""
    if turn is None:
        return None
    if isinstance(turn, dict):
        role = turn.get("role")
        content = turn.get("content")
    else:
        role = getattr(turn, "role", None)
        content = getattr(turn, "content", None)
    if not isinstance(role, str) or not isinstance(content, str):
        return None
    return role, content


def _last_user_turn(history: Optional[list[Any]]) -> Optional[str]:
    if not history:
        return None
    for turn in reversed(history):
        parsed = _turn_role_content(turn)
        if parsed and parsed[0] == "user" and parsed[1].strip():
            return parsed[1]
    return None


def _history_before(history: Optional[list[Any]]) -> Optional[list[Any]]:
    """`history` with its LAST user turn removed, so a follow-up chain is bounded."""
    if not history:
        return None
    for index in range(len(history) - 1, -1, -1):
        parsed = _turn_role_content(history[index])
        if parsed and parsed[0] == "user":
            return list(history[:index])
    return None


def _suggested_blocks(mode: str, learning: bool) -> tuple[str, ...]:
    if mode == "explanation":
        if learning:
            return ("learning_map", "stepper", "details", "diagram", "comparison_grid")
        return ("stepper", "details", "comparison_grid", "diagram", "callout")
    if mode == "visualization":
        return ("chart", "financial_chart", "data_table", "metric_grid", "citations")
    if mode == "simulation":
        return ("simulation", "controls", "chart", "metric_grid", "key_value")
    if mode == "workflow":
        return ("workflow", "flow", "node_graph", "timeline", "stepper")
    if mode == "composite":
        return ("markdown", "chart", "data_table", "controls", "citations")
    return ()


def _directive_body(mode: str, learning: bool) -> str:
    """The mode's one-paragraph guidance (kept in one place, easy to review)."""
    if mode == "explanation":
        base = (
            "present an INTERACTIVE EXPLANATION. Prefer `stepper` for ordered "
            "steps, `details` for expandable depth, `comparison_grid` for "
            "side-by-side options and `diagram`/`node_graph` when a picture "
            "clarifies; keep connected prose in ONE markdown block. Add a "
            "`chart` only if it genuinely clarifies."
        )
        if learning:
            base += (
                " This is a learning request: build it with `learning_path_build` "
                "first and render a `learning_map` with prerequisite-ordered "
                "nodes, resources, exercises and a `pathId`."
            )
        return base
    if mode == "visualization":
        return (
            "present a DATA VISUALIZATION. Retrieve the real values with tools "
            "FIRST, then render them with `chart`/`financial_chart`/`data_table`/"
            "`metric_grid`; every number must come from a tool result you hold or "
            "be marked `unavailable`. Carry the source and as-of where relevant. "
            "Never invent a series, price or metric."
        )
    if mode == "simulation":
        return (
            "present an INTERACTIVE SIMULATION. For a simple, trusted formula the "
            "user should drive (e.g. a risk/reward or break-even explorer) use a "
            "`simulation` block — it computes a result locally and is always "
            "labelled illustrative. For anything needing real data or a backtest, "
            "ground the parameters in the quant/backtest tools, expose adjustable "
            "inputs with a `controls` block and show results with `chart`/"
            "`metric_grid`/`key_value`. NEVER imply a real backtest re-ran when "
            "only illustrative values changed — route any real run through the "
            "backtest tools."
        )
    if mode == "workflow":
        return (
            "present a WORKFLOW / AGENT VISUALIZATION. Show the process with "
            "`workflow` (linear stages), `flow`/`node_graph` (branching / "
            "dependencies) and `timeline`/`stepper` for execution state; map each "
            "node to real tool calls or plan steps you observed, and mark what "
            "you could not see instead of inventing it."
        )
    if mode == "composite":
        return (
            "present a COMPOSITE ANSWER. Lead with a short markdown answer, then "
            "the minimal set of blocks that add value (chart / table / controls / "
            "evidence); keep all connected prose in ONE markdown block and do not "
            "restate it. Every number still needs a tool result or `unavailable`."
        )
    return (
        "answer in clear PROSE. Do NOT emit an eclipse-response fence unless the "
        "answer genuinely needs structure — a short or conversational reply stays "
        "plain Markdown."
    )


def response_mode_prompt_block(plan: ResponsePlan) -> str:
    """Render a plan as the prompt directive appended to the system head."""
    body = _directive_body(plan.mode, plan.learning)
    lines = [
        "## Response plan (presentation guidance, chosen by the orchestrator)",
        f"Mode: {plan.mode}. {body}",
    ]
    if plan.suggested_blocks:
        lines.append("Suggested blocks: " + ", ".join(plan.suggested_blocks) + ".")
    lines.append(
        "This is guidance, not a mandate: if the request turns out simpler than "
        "the mode suggests, answer plainly. Never fabricate a block, number or "
        "source to satisfy it."
    )
    return "\n".join(lines)


def plan_for_mode(
    mode: ResponseMode,
    confidence: Confidence,
    reason: str,
    signals: tuple[str, ...],
    *,
    learning: bool = False,
) -> ResponsePlan:
    """Build a plan for `mode` with its suggested blocks resolved."""
    return ResponsePlan(
        mode=mode,
        confidence=confidence,
        reason=reason,
        signals=signals,
        suggested_blocks=_suggested_blocks(mode, learning),
        learning=learning,
    )


def _plan(
    mode: ResponseMode,
    confidence: Confidence,
    reason: str,
    signals: tuple[str, ...],
    *,
    learning: bool = False,
) -> ResponsePlan:
    return plan_for_mode(mode, confidence, reason, signals, learning=learning)


# ── The model-assisted fallback (pure parts) ────────────────────────────────
# When the deterministic classifier is `unsure`, a bounded model call may pick a
# mode. The prompt and the reply parser live here (pure, testable); the model
# construction + invocation live in `response_mode_llm.py`.

MODE_CLASSIFIER_SYSTEM = (
    "You classify how a chat answer should be PRESENTED. Reply with exactly ONE "
    "word from: text, explanation, visualization, simulation, workflow, "
    "composite. Definitions: text = a simple question or chat, prose is enough; "
    "explanation = teach or explain a concept (steps, comparisons); "
    "visualization = show real data (a chart, table or metrics); simulation = a "
    "what-if the user should drive (parameters, backtests); workflow = an agent, "
    "plan or execution process; composite = more than one of these genuinely "
    "apply. Reply with the single word and nothing else. When in doubt, reply "
    "text."
)

_MODE_WORD_RE = re.compile(
    r"\b(text|explanation|visualization|simulation|workflow|composite)\b",
    re.IGNORECASE,
)
_MODE_SYNONYMS: tuple[tuple[str, ResponseMode], ...] = (
    ("composite", "composite"),
    ("multiple", "composite"),
    ("workflow", "workflow"),
    ("execution", "workflow"),
    ("agent", "workflow"),
    ("visual", "visualization"),
    ("chart", "visualization"),
    ("graph", "visualization"),
    ("table", "visualization"),
    ("simulat", "simulation"),
    ("what-if", "simulation"),
    ("backtest", "simulation"),
    ("scenario", "simulation"),
    ("explain", "explanation"),
    ("teach", "explanation"),
    ("tutorial", "explanation"),
    ("prose", "text"),
    ("plain", "text"),
)


def mode_classifier_prompt(query: str) -> str:
    """The user turn to classify (the system prompt is `MODE_CLASSIFIER_SYSTEM`)."""
    return f"Classify how to present this request:\n\n{query.strip()}"


def parse_mode_reply(text: str) -> Optional[ResponseMode]:
    """Extract a response mode from a classifier reply, or None.

    Prefers an explicit mode word; falls back to distinctive synonyms. Total —
    never raises on odd input.
    """
    if not text:
        return None
    direct = _MODE_WORD_RE.search(text)
    if direct:
        return direct.group(1).casefold()  # type: ignore[return-value]
    lowered = text.casefold()
    for needle, mode in _MODE_SYNONYMS:
        if needle in lowered:
            return mode
    return None


def classify_response_mode(
    query: str, history: Optional[list[Any]] = None,
) -> ResponsePlan:
    """Choose the presentation mode for a chat turn (deterministic, no model call).

    Rules (in order):
      1. empty turn → `text`
      2. a mode-specific signal fires → that mode (or `composite` when two or
         more rich modes fire and one of them is data-bearing)
      3. a bare greeting / very short signal-free turn → `text`
      4. a short follow-up ("do it") inherits the PRIOR user turn's mode
      5. anything else → `text` (the safe default)
    """
    text = (query or "").strip()
    if not text:
        return _plan("text", "certain", "The turn was empty.", ("empty",))

    matched = {
        "workflow": _matched_terms(text, _WORKFLOW_TERMS),
        "simulation": _matched_terms(text, _SIMULATION_TERMS),
        "visualization": _matched_terms(text, _VISUALIZATION_TERMS),
        "explanation": _matched_terms(text, _EXPLANATION_TERMS),
    }
    fired = [mode for mode in _MODE_ORDER if matched[mode]]
    learning = bool(_matched_terms(text, _LEARNING_TERMS))

    # Composite: two rich modes genuinely co-occur and at least one is data.
    if len(fired) >= 2 and (_DATA_MODES & set(fired)):
        signals = tuple(f"mode:{m}" for m in fired)
        return _plan(
            "composite", "likely",
            "The turn needs more than one presentation (a data mode plus another).",
            signals,
        )

    mode = fired[0] if fired else None
    if mode is not None:
        if mode == "explanation":
            # A generic "what is X" is a lookup, not a walkthrough: keep a lone
            # soft interrogation as text unless the term is a teaching signal.
            confidence: Confidence = "likely"
        else:
            confidence = "certain"
        return _plan(
            mode, confidence,
            f"The turn matches the {mode} signals.",
            tuple(f"mode:{mode}"),
            learning=learning if mode == "explanation" else False,
        )

    # A greeting stays prose.
    lowered = text.casefold().strip(" !.")
    if lowered in _GREETING_TERMS:
        return _plan(
            "text", "certain",
            "A greeting needs no structure.",
            ("chat",),
        )

    # A short follow-up inherits the PRIOR user turn's mode (bounded recursion).
    # Checked BEFORE the short-turn rule so "do it" is not swallowed as chat.
    if _matched_terms(text, _FOLLOW_UPS):
        previous = _last_user_turn(history)
        if previous:
            prior = classify_response_mode(previous, history=_history_before(history))
            if prior.mode != "text":
                return _plan(
                    prior.mode, "likely",
                    f"This continues an earlier {prior.mode} turn.",
                    ("follow_up", f"mode:{prior.mode}"),
                    learning=prior.learning,
                )
        return _plan(
            "text", "certain",
            "The turn is a follow-up with no presentation signal of its own.",
            ("follow_up",),
        )

    # A very short, signal-free turn is chat, not a rich answer.
    if len(text.split()) <= 3 and not text.endswith("?"):
        return _plan(
            "text", "certain",
            "A short, conversational turn needs no structure.",
            ("chat",),
        )

    return _plan(
        "text", "unsure",
        "No distinctive presentation signal; defaulting to prose.",
        ("ambiguous",),
    )


__all__ = [
    "MODE_CLASSIFIER_SYSTEM",
    "Confidence",
    "ResponseMode",
    "ResponsePlan",
    "classify_response_mode",
    "mode_classifier_prompt",
    "parse_mode_reply",
    "plan_for_mode",
    "response_mode_prompt_block",
]

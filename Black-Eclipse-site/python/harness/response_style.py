"""Just-in-time design modules for the Interactive Response Engine.

The block CONTRACT (exact field names, enums, limits) is injected into the
system prompt from the TS renderer. What a schema cannot carry is *taste*: when a
family of blocks is the right answer, how the members differ, and what a good
document in that family looks like.

Loading all of that into every prompt is expensive and goes stale. Instead the
base prompt carries a small module INDEX, and the model loads ONE family's guide
plus worked examples on demand — the `response_style_guide` tool. This mirrors
the "read the style guide before the first widget" pattern: the base prompt stays
small, the examples steer quality, and the rules are versionable here without
touching the prompt.

Pure and deterministic. No model calls, no I/O — the tool handler in
`response_tools.py` fetches the live field map and passes it in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class DesignModule:
    """One family of blocks, its nuance, and worked examples."""

    key: str
    title: str
    blocks: tuple[str, ...]
    guidance: str
    examples: tuple[tuple[str, dict[str, Any]], ...]


# ── Module definitions ────────────────────────────────────────────────────────
# Keep each `guidance` to the choices a producer actually gets wrong. The field
# names do NOT belong here — they come from the live contract.

_MODULES: tuple[DesignModule, ...] = (
    DesignModule(
        key="data",
        title="Data, metrics and comparisons",
        blocks=(
            "metric_grid",
            "stat_hero",
            "data_table",
            "key_value",
            "citations",
            "gauge",
            "ranked_list",
            "badge_row",
            "comparison_grid",
            "timeline",
        ),
        guidance=(
            "Pick by shape, not by habit. `metric_grid` is a compact KPI set "
            "(2–6 small numbers); `stat_hero` is ONE to four oversized headline "
            "numbers with room for context — never a grid of them. `data_table` "
            "is for rows a reader will scan or sort; if there are fewer than "
            "three rows and no comparison, prose is better. `comparison_grid` is "
            "options-as-columns vs attributes-as-rows (a pricing table), with "
            "booleans rendering as check/cross. `ranked_list` is a leaderboard "
            "whose bars scale to the real maximum. `badge_row` is tags only, "
            "never a metric. `timeline` is time-stamped events; an ordered "
            "procedure is `stepper`, not a timeline. Always carry `source` and "
            "`asOf` when the numbers came from a tool, and set `unavailable` "
            "instead of inventing a value."
        ),
        examples=(
            (
                "KPI grid grounded in a tool result",
                {
                    "blocks": [
                        {
                            "type": "metric_grid",
                            "title": "Q3 FY25",
                            "source": "Company 10-Q",
                            "asOf": "2025-09-30",
                            "columns": 3,
                            "metrics": [
                                {"label": "Revenue", "value": "$1.21B", "delta": "8.0%", "deltaTone": "up", "hint": "YoY"},
                                {"label": "Gross margin", "value": "61.4%", "delta": "0.9pp", "deltaTone": "up"},
                                {"label": "Free cash flow", "value": "$214M", "delta": "-3.1%", "deltaTone": "down"},
                            ],
                        }
                    ]
                },
            ),
            (
                "Availability over invention",
                {
                    "blocks": [
                        {
                            "type": "stat_hero",
                            "title": "Current drawdown",
                            "description": "The series is not held for this window.",
                            "unavailable": True,
                            "caption": "Price history for this period was unavailable, so no figure is shown.",
                            "stats": [],
                        }
                    ]
                },
            ),
        ),
    ),
    DesignModule(
        key="chart",
        title="Charts and market series",
        blocks=("chart", "financial_chart"),
        guidance=(
            "A chart block IS the drawing: put the data in the block and let the "
            "engine draw it. For a short series use `series`; for a named market "
            "series use `dataSource` (symbol + optional interval/start/end/field) "
            "so 250 prices never travel in the message. Use `financial_chart` "
            "only when the user named a symbol and wants the live terminal view. "
            "A linear regression is a `regression` mark (or `chartType: "
            "\"regression\"`); never fit the line yourself. Use `panels`/`marks` "
            "for anything the simple kinds cannot express (violin, box, Gantt, "
            "funnel, dual axis). Carry `source`/`asOf`, and put a tool's "
            "`formula` in `provenance.formula` for a derived figure. Never invent "
            "points, and never draw an empty chart for data you do not hold."
        ),
        examples=(
            (
                "A short categorical series",
                {
                    "blocks": [
                        {
                            "type": "chart",
                            "chartType": "bar",
                            "title": "Revenue by segment",
                            "source": "Company 10-Q",
                            "asOf": "2025-09-30",
                            "categories": ["Cloud", "Services", "Hardware"],
                            "series": [{"name": "Revenue ($M)", "data": [120, 180, 90]}],
                        }
                    ]
                },
            ),
            (
                "A named market series fetched by the engine",
                {
                    "blocks": [
                        {
                            "type": "chart",
                            "chartType": "line",
                            "title": "AAPL — 6 months",
                            "dataSource": {"symbol": "AAPL", "interval": "1d"},
                        }
                    ]
                },
            ),
        ),
    ),
    DesignModule(
        key="diagram",
        title="Structure and relationships",
        blocks=("diagram", "node_graph", "mermaid", "flow"),
        guidance=(
            "Choose by what the reader must do. `diagram` is a static picture of "
            "nodes/edges (`flowchart`/`dependency`/`state`) — never a hand-written "
            "flowchart in Mermaid. `node_graph` is the same layout but SELECTABLE, "
            "so a node can reveal `detail`; use it for architectures and "
            "dependencies. `flow` is responsive cards for an ordered process with "
            "branching paths. `mermaid` is ONLY for sequence, ER, class and Gantt "
            "diagrams. Keep node ids stable and edges pointing at real ids; a "
            "label is not an id. Do not draw a chart with a diagram."
        ),
        examples=(
            (
                "A dependency graph",
                {
                    "blocks": [
                        {
                            "type": "node_graph",
                            "title": "Retrieval path",
                            "direction": "LR",
                            "nodes": [
                                {"id": "q", "label": "User query", "tone": "info"},
                                {"id": "router", "label": "Source router"},
                                {"id": "db", "label": "JDdS", "tone": "success"},
                                {"id": "web", "label": "Web research"},
                            ],
                            "edges": [
                                {"from": "q", "to": "router"},
                                {"from": "router", "to": "db", "label": "market data"},
                                {"from": "router", "to": "web", "label": "filing text"},
                            ],
                        }
                    ]
                },
            ),
        ),
    ),
    DesignModule(
        key="workflow",
        title="Processes, plans and next steps",
        blocks=("workflow", "stepper", "timeline", "action_group"),
        guidance=(
            "`workflow` is a LINEAR sequence of icon stages with connectors; "
            "`stepper` is a numbered list of steps with status and no connectors; "
            "`flow` (see the diagram module) is for branching. Use `timeline` only "
            "when each item has a real time. `action_group` proposes next steps — "
            "each action's `prompt` is sent as a NEW user turn, so phrase it as "
            "something the user would type, and never imply it already ran. Set "
            "`icon` from the schema's icon vocabulary, never an emoji."
        ),
        examples=(
            (
                "A linear process with status",
                {
                    "blocks": [
                        {
                            "type": "workflow",
                            "title": "How the run was built",
                            "stages": [
                                {"id": "plan", "title": "Plan", "description": "Split the question.", "status": "done"},
                                {"id": "retrieve", "title": "Retrieve", "description": "Pull the filing and prices.", "status": "done"},
                                {"id": "verify", "title": "Verify", "description": "Check coverage and conflicts.", "status": "active"},
                            ],
                        }
                    ]
                },
            ),
        ),
    ),
    DesignModule(
        key="interactive",
        title="Parameters the user can drive",
        blocks=("controls", "simulation", "inputs", "learning_map", "action_group"),
        guidance=(
            "Two different jobs. `controls` collects parameters and sends a "
            "follow-up prompt that re-enters the agent loop — use it when the "
            "answer needs a new tool run or real data. `simulation` computes "
            "LOCALLY from a trusted formula with no model call and no data: use it "
            "only for an illustrative what-if, and never imply a backtest re-ran. "
            "`inputs` drives envelope `state` variables. A `learning_map` must "
            "come from `learning_path_build` and carry its `pathId` so progress "
            "persists. Prefer fewer, meaningful inputs over a wall of sliders."
        ),
        examples=(
            (
                "A local risk/reward calculator (illustrative only)",
                {
                    "blocks": [
                        {
                            "type": "simulation",
                            "title": "Risk / reward",
                            "description": "Move the entries to see the ratio change. Illustrative, not market data.",
                            "inputs": [
                                {"id": "entry", "label": "Entry", "value": 100, "min": 1, "max": 500, "step": 1},
                                {"id": "stop", "label": "Stop", "value": 95, "min": 1, "max": 500, "step": 1},
                                {"id": "target", "label": "Target", "value": 110, "min": 1, "max": 500, "step": 1},
                            ],
                            "outputs": [
                                {"id": "rr", "label": "Reward / risk", "expression": "(target - entry) / (entry - stop)", "precision": 2},
                                {"id": "upside", "label": "Upside", "expression": "(target - entry) / entry", "format": "percent", "precision": 1},
                            ],
                        }
                    ]
                },
            ),
            (
                "Parameters that need a real re-run",
                {
                    "blocks": [
                        {
                            "type": "controls",
                            "title": "Refine the screen",
                            "description": "Run the screen again with these filters",
                            "controls": [
                                {"kind": "slider", "id": "pe", "label": "Max P/E", "min": 5, "max": 40, "step": 1, "default": 20},
                                {"kind": "select", "id": "sector", "label": "Sector", "options": [{"value": "tech", "label": "Technology"}, {"value": "energy", "label": "Energy"}]},
                            ],
                            "promptTemplate": "Re-run the equity screen with max P/E {{pe}} and sector {{sector}}.",
                        }
                    ]
                },
            ),
        ),
    ),
    DesignModule(
        key="explanation",
        title="Teaching and explanation",
        blocks=("stepper", "details", "callout", "comparison_grid", "tabs", "report", "key_value"),
        guidance=(
            "Lead with a short prose answer, then add structure only where it "
            "carries depth. `stepper` for an ordered method; `details` for optional "
            "depth a reader can expand; `comparison_grid` for side-by-side options; "
            "`tabs` for parallel facets; `report` for a long multi-section answer. "
            "Keep connected prose in ONE markdown block — do not scatter one "
            "sentence across cards. A lone definition needs no blocks at all."
        ),
        examples=(
            (
                "A method with optional depth",
                {
                    "blocks": [
                        {
                            "type": "stepper",
                            "title": "How duration is estimated",
                            "steps": [
                                {"title": "Measure cash-flow timing", "description": "Weight each payment by when it arrives.", "status": "done"},
                                {"title": "Annualise the weighted time", "description": "Divide by (1 + yield).", "status": "done"},
                                {"title": "Compare across bonds", "description": "Duration is only comparable at the same yield convention.", "status": "active"},
                            ],
                        },
                        {
                            "type": "details",
                            "summary": "Why duration is not maturity",
                            "markdown": "A zero-coupon bond has duration equal to maturity; a coupon bond returns cash earlier, so its duration is shorter.",
                        },
                    ]
                },
            ),
        ),
    ),
    DesignModule(
        key="mechanical",
        title="Mechanical and 3D explanations",
        blocks=("anatomy", "model3d"),
        guidance=(
            "These are compiled from a DECLARATIVE part graph — never SVG, meshes, "
            "shaders or code. Use `anatomy` for an isometric cutaway of a mechanism "
            "on a bench (parts: slab/prism/cylinder/disc/knob/lathe/cone/sphere; "
            "wires join part ids), and `model3d` for an orbitable WebGL assembly "
            "(parts: box/cylinder/cone/sphere/torus/lathe/extrude/tube/gear, or a "
            "`recipe` such as motor/pump/valve/gauge). Give every part and wire a "
            "stable id, put labels/readouts in `stages` so a number is never "
            "invented by animation, and keep the part count small enough to read. "
            "Use it to explain a mechanism, not to decorate a finance answer."
        ),
        examples=(
            (
                "An isometric mechanism",
                {
                    "blocks": [
                        {
                            "type": "anatomy",
                            "title": "Matching engine",
                            "hint": "Hover a part; step the stages.",
                            "parts": [
                                {"id": "base", "kind": "slab", "w": 180, "d": 120, "height": 14, "screws": True},
                                {"id": "drum", "kind": "cylinder", "x": -30, "z": 14, "radius": 34, "height": 70, "tone": "info", "knurl": True},
                                {"id": "gauge", "kind": "lathe", "x": 55, "y": 20, "z": 20, "profile": [[0, 0], [6, 22], [12, 18], [18, 24]], "smooth": True, "tone": "warning"},
                            ],
                            "wires": [{"from": "base", "to": "drum", "tone": "info", "label": "feed"}],
                            "legend": [{"label": "Order book drum", "mark": "cylinder"}, {"label": "Depth gauge", "mark": "lathe"}],
                        }
                    ]
                },
            ),
            (
                "An orbitable 3D assembly",
                {
                    "blocks": [
                        {
                            "type": "model3d",
                            "title": "Gearbox",
                            "parts": [
                                {"id": "housing", "kind": "box", "w": 60, "h": 40, "d": 40, "material": "metal"},
                                {"id": "shaft", "kind": "cylinder", "radius": 6, "h": 80, "position": [0, 0, 30], "rotation": [90, 0, 0], "material": "metal"},
                            ],
                            "legend": [{"label": "Housing", "mark": "box"}, {"label": "Input shaft", "mark": "cylinder"}],
                        }
                    ]
                },
            ),
        ),
    ),
)

_BY_KEY = {module.key: module for module in _MODULES}


def module_names() -> tuple[str, ...]:
    return tuple(module.key for module in _MODULES)


def get_module(key: str) -> Optional[DesignModule]:
    return _BY_KEY.get((key or "").strip().casefold())


def _fmt_fields(payload: dict[str, Any], wanted: tuple[str, ...]) -> list[str]:
    """Exact field lines for the module's blocks, from the live contract."""
    lines: list[str] = []
    for block in payload.get("blocks") or []:
        block_type = str(block.get("type") or "")
        if block_type not in wanted:
            continue
        parts: list[str] = []
        for field in block.get("fields") or []:
            name = str(field.get("name"))
            kind = str(field.get("kind") or "value")
            items = field.get("itemFields")
            detail = f"{kind}{{{','.join(str(i) for i in items)}}}" if items else kind
            parts.append(f"{name}{'' if field.get('required') else '?'}:{detail}")
        lines.append(f"- {block_type}: " + "; ".join(parts))
    return lines


def format_style_guide(module: DesignModule, schema_payload: dict[str, Any]) -> str:
    """Render one module: nuance, exact fields, and worked examples."""
    lines = [
        f"Design guide — {module.title}",
        "Blocks in this family: " + ", ".join(module.blocks) + ".",
        "",
        module.guidance,
        "",
    ]
    fields = _fmt_fields(schema_payload, module.blocks)
    if fields:
        lines.append("Exact fields (live contract; `?` marks optional; enum(a|b) lists the only values):")
        lines.extend(fields)
    else:
        lines.append(
            "Exact fields: not reachable this call — use `response_block_schema` "
            "for this family before emitting it."
        )
    lines.append("")
    lines.append(
        "Worked examples — structure only. The numbers and labels are "
        "placeholders: replace them with results you actually hold, or mark the "
        "figure `unavailable`. Emit ONE fence whose `blocks` array is the whole "
        "document."
    )
    for index, (caption, example) in enumerate(module.examples, start=1):
        lines.append("")
        lines.append(f"Example {index} — {caption}")
        lines.append("```json")
        lines.append(json.dumps(example, ensure_ascii=False, separators=(",", ":")))
        lines.append("```")
    return "\n".join(lines)


def response_style_index_prompt_block() -> str:
    """The small, always-on index of loadable design modules.

    Deliberately NOT the modules themselves: one line here, the details on
    demand through `response_style_guide`. Stable text, so it costs little in
    the byte-stable system head.
    """
    return (
        "## Design modules (load before authoring that family)\n"
        "The block schema below gives exact FIELDS; it does not give taste. Before "
        "the first block of a family, call `response_style_guide` with one module "
        "and use its worked examples:\n"
        + "\n".join(f"- `{module.key}` — {module.title}" for module in _MODULES)
        + "\nLoad at most the families you are about to use; do not load every "
        "module. Field names always come from the schema, never from an example."
    )


__all__ = [
    "DesignModule",
    "format_style_guide",
    "get_module",
    "module_names",
    "response_style_index_prompt_block",
]

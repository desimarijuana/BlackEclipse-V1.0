"""Structured agent nodes: classify, extract, summarize, critique.

Each node is ONE bounded model call returning strict JSON (see
`agent_structured.py`). They are deliberately NOT full agent turns: a
classification or an extraction does not need tools, so these use the model
runtime directly and cannot reach a tool at all. The graph stays the authority
for ordering and effects.

`bootstrap.py` binds the model runner at boot so tests can substitute a fake and
this module never imports the runtime.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .agent_structured import VERDICTS, normalize_labels, validate_extraction
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_INSTRUCTIONS = 2_000

# `(context, op, args) -> the model's parsed JSON object`.
ModelRunner = Callable[[NodeExecContext, str, dict[str, Any]], dict[str, Any]]
_runner: Optional[ModelRunner] = None


def set_structured_runner(runner: Optional[ModelRunner]) -> None:
    global _runner
    _runner = runner


def _model(context: NodeExecContext, op: str, args: dict[str, Any]) -> dict[str, Any]:
    if _runner is None:
        raise ValueError("the structured model runner is not configured in this graph runtime")
    result = _runner(context, op, args)
    if not isinstance(result, dict):
        raise ValueError("the structured model runner returned no JSON object")
    return result


def _text(context: NodeExecContext, label: str, field: str = "text") -> str:
    value = context.inputs.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{label} needs a text input (wire a string into Text)")
    text = value.strip()
    if not text:
        raise ValueError(f"{label} received empty text")
    return text


def _instructions(context: NodeExecContext) -> str:
    return str(context.config.get("instructions") or "").strip()[:MAX_INSTRUCTIONS]


def exec_classify(context: NodeExecContext) -> dict[str, Any]:
    text = _text(context, "agent.classify")
    labels = normalize_labels(context.config.get("labels"))
    if len(labels) < 2:
        raise ValueError("agent.classify needs at least two labels (Labels)")
    raw = _model(context, "classify", {
        "text": text,
        "labels": labels,
        "instructions": _instructions(context),
    })
    label = str(raw.get("label") or "").strip()
    if not label:
        raise ValueError("the model returned no label")
    match = next((item for item in labels if item.casefold() == label.casefold()), None)
    if match is None:
        raise ValueError(
            f"the model returned {label!r}, which is not one of the declared labels "
            f"({', '.join(labels)})"
        )
    confidence = raw.get("confidence")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise ValueError("the model returned no confidence in 0..1")
    scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    context.emit(f"classified as {match} ({float(confidence):.2f})")
    return {"label": match, "confidence": round(float(confidence), 4), "scores": scores}


def _schema(context: NodeExecContext) -> dict[str, Any]:
    wired = context.inputs.get("schema")
    if wired is not None:
        if not isinstance(wired, dict):
            raise ValueError("schema input must be a JSON object")
        return wired
    text = str(context.config.get("schemaJson") or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Schema (JSON) is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Schema (JSON) must be a JSON object")
    return parsed


def exec_extract(context: NodeExecContext) -> dict[str, Any]:
    text = _text(context, "agent.extract")
    schema = _schema(context)
    raw = _model(context, "extract", {
        "text": text,
        "schema": schema,
        "instructions": _instructions(context),
    })
    data = raw.get("data")
    if not isinstance(data, dict):
        raise ValueError("the model returned no `data` object")
    valid, issues = validate_extraction(data, schema)
    if not valid:
        # A shape mismatch is REPORTED, not thrown: the caller can still use the
        # partial extraction and branch on `valid`.
        context.emit("extraction does not match the schema: " + "; ".join(issues[:5]))
    return {
        "data": data,
        "raw": json.dumps(data, ensure_ascii=False),
        "valid": bool(valid),
    }


def exec_summarize(context: NodeExecContext) -> dict[str, Any]:
    body = context.inputs.get("text")
    if isinstance(body, str):
        if not body.strip():
            raise ValueError("agent.summarize received empty text")
    elif isinstance(body, (list, dict)):
        if not body:
            raise ValueError("agent.summarize received an empty collection")
    else:
        raise ValueError("agent.summarize needs a string, array or object in Text")

    try:
        max_words = int(context.config.get("maxWords", 200))
    except (TypeError, ValueError) as exc:
        raise ValueError("Max words must be a whole number") from exc
    max_words = max(10, min(max_words, 2_000))
    style = str(context.config.get("style") or "prose")
    if style not in ("prose", "bullets"):
        raise ValueError("style must be `prose` or `bullets`")

    raw = _model(context, "summarize", {
        "text": body,
        "maxWords": max_words,
        "style": style,
    })
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        raise ValueError("the model returned an empty summary")
    points = raw.get("keyPoints")
    key_points = [str(item).strip() for item in points if str(item).strip()] if isinstance(points, list) else []
    context.emit(f"summarized {len(key_points)} key point(s)")
    return {"summary": summary, "keyPoints": key_points[:12]}


def exec_critique(context: NodeExecContext) -> dict[str, Any]:
    finding = context.inputs.get("finding")
    if isinstance(finding, dict):
        text = str(finding.get("text") or "").strip()
        if not text:
            # A finding object with no text is still usable when it carries other
            # content (research, citations); one with nothing at all is empty.
            extras = {
                key: value
                for key, value in finding.items()
                if key != "text" and value not in (None, "", [], {})
            }
            text = json.dumps(extras, ensure_ascii=False) if extras else ""
    elif isinstance(finding, str):
        text = finding.strip()
    else:
        raise ValueError("agent.critique needs a finding (wire a finding or a string)")
    if not text:
        raise ValueError("agent.critique received an empty finding")

    rubric = str(
        context.inputs.get("rubric") or context.config.get("rubric") or ""
    ).strip()[:MAX_INSTRUCTIONS]
    raw = _model(context, "critique", {
        "finding": text,
        "evidence": context.inputs.get("evidence"),
        "rubric": rubric,
    })
    verdict = str(raw.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        raise ValueError(
            f"the model returned verdict {verdict!r}; expected one of {', '.join(VERDICTS)}"
        )
    score_raw = raw.get("score")
    score: Optional[float] = None
    if score_raw is not None:
        if (
            not isinstance(score_raw, (int, float))
            or isinstance(score_raw, bool)
            or not 0.0 <= float(score_raw) <= 1.0
        ):
            raise ValueError("the model returned a score outside 0..1")
        score = round(float(score_raw), 4)
    issues_raw = raw.get("issues")
    issues = [str(item).strip() for item in issues_raw if str(item).strip()] if isinstance(issues_raw, list) else []
    context.emit(f"verdict {verdict}" + (f" ({score:.2f})" if score is not None else ""))
    return {"verdict": verdict, "issues": issues[:12], "score": score}


def build_structured_agent_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="agent.classify", version="1.0.0", label="Classify",
            category="agent",
            inputs=(PortDef(id="text", name="Text", type=PortType.STRING),),
            outputs=(
                PortDef(id="label", name="Label", type=PortType.STRING),
                PortDef(id="confidence", name="Confidence", type=PortType.NUMBER),
                PortDef(id="scores", name="Scores", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("labels", "string", "", max_length=500),
                ConfigField("instructions", "string", "", max_length=MAX_INSTRUCTIONS),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_classify,
            metadata={
                "docs": (
                    "ONE bounded model call returning exactly one of the declared "
                    "labels. A label outside the set, or a confidence outside 0..1, "
                    "fails the node instead of being coerced. No tools."
                ),
            },
        ),
        NodeDef(
            type="agent.extract", version="1.0.0", label="Extract",
            category="agent",
            inputs=(
                PortDef(id="text", name="Text", type=PortType.STRING),
                PortDef(id="schema", name="Schema", type=PortType.OBJECT, optional=True),
            ),
            outputs=(
                PortDef(id="data", name="Data", type=PortType.OBJECT),
                PortDef(id="raw", name="Raw JSON", type=PortType.STRING),
                PortDef(id="valid", name="Valid", type=PortType.BOOLEAN),
            ),
            config_fields=(
                ConfigField("schemaJson", "string", "", max_length=20_000),
                ConfigField("instructions", "string", "", max_length=MAX_INSTRUCTIONS),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=180_000,
            executor=exec_extract,
            metadata={
                "docs": (
                    "ONE bounded model call that extracts a JSON object. The result "
                    "is checked against the supplied schema (type/required/properties/"
                    "items); a mismatch reports `valid: false` with the issues on the "
                    "run log rather than pretending the shape matched. No tools."
                ),
            },
        ),
        NodeDef(
            type="agent.summarize", version="1.0.0", label="Summarize",
            category="agent",
            inputs=(PortDef(id="text", name="Text", type=PortType.ANY),),
            outputs=(
                PortDef(id="summary", name="Summary", type=PortType.STRING),
                PortDef(id="keyPoints", name="Key points", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("maxWords", "integer", 200, minimum=10, maximum=2_000),
                ConfigField("style", "string", "prose", max_length=20),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=180_000,
            executor=exec_summarize,
            metadata={
                "docs": (
                    "ONE bounded model call that compresses a string, array or object. "
                    "Empty input fails by name; the prompt forbids adding facts. No tools."
                ),
            },
        ),
        NodeDef(
            type="agent.critique", version="1.0.0", label="Critique finding",
            category="agent",
            inputs=(
                PortDef(id="finding", name="Finding", type=PortType.RESEARCH_FINDING),
                PortDef(id="evidence", name="Evidence", type=PortType.EVIDENCE, optional=True),
                PortDef(id="rubric", name="Rubric", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="verdict", name="Verdict", type=PortType.STRING),
                PortDef(id="issues", name="Issues", type=PortType.ARRAY),
                PortDef(id="score", name="Score", type=PortType.NUMBER, nullable=True),
            ),
            config_fields=(
                ConfigField("rubric", "string", "", max_length=MAX_INSTRUCTIONS),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_critique,
            metadata={
                "docs": (
                    "ONE bounded model call that judges a finding against wired "
                    "evidence. `verdict` must be supported/weak/contradicted; anything "
                    "else fails the node. `score` is null when the model omitted it. "
                    "It never rewrites the finding. No tools."
                ),
            },
        ),
    ]


__all__ = [
    "MAX_INSTRUCTIONS",
    "build_structured_agent_nodes",
    "exec_classify",
    "exec_critique",
    "exec_extract",
    "exec_summarize",
    "set_structured_runner",
]

"""Model-backed synthesis for the research flow (Phase 4, Workstream 2).

The synthesis model is a *bounded extractor*, not an authority. It receives only:

  * the research mandate,
  * the bounded evidence packet (evidence ids + their normalized objects),
  * the deterministic coverage report,
  * optional repair feedback (the exact invalid claims / missing legs).

It is given NO tools and NO memory, so it cannot bypass retrieval. Its output is
parsed as strict JSON and validated by Pydantic before any deterministic check
runs. Provider-structured output is attempted when available; otherwise a robust
fenced-JSON extractor is used. A parse/validation failure becomes an honest gap,
never an unvalidated claim.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from .claims import Synthesis
from .coverage import CoverageReport
from .mandate import ResearchMandate

# Bounds — the packet must not carry an unbounded source document.
MAX_EVIDENCE_ITEMS = 40
MAX_OBJECTS_PER_ITEM = 20
MAX_PACKET_CHARS = 24_000
MAX_SUMMARY_CHARS = 400

SYNTHESIS_SYSTEM_PROMPT = """You are the synthesis step of a deterministic, evidence-grounded \
research harness. You do NOT know financial facts from memory and you have no tools. You may \
state a fact ONLY when it is supported by the evidence packet you are given. Every reported or \
derived claim MUST cite one or more evidence ids that appear in the packet. If a required fact is \
not present, or its identity/metric/period/basis/unit do not match the mandate, report it under \
\"gaps\" and DO NOT assert it.

Rules:
- Never invent evidence ids, URLs, numbers, dates or sources.
- Do not present an unsupported guess as a fact. Put uncertainty in \"gaps\" / \"assumptions\".
- Interpretations and causal statements go under claim kind \"interpretation\" and are treated as unverified.
- Answer in the language of the objective.

Return ONLY a single JSON object, no prose outside it, with this shape:
{
  "claims": [
    {
      "text": "<one factual sentence>",
      "kind": "reported_fact" | "derived_fact" | "qualitative_fact" | "interpretation",
      "evidenceIds": ["<evidence id from the packet>"],
      "legId": "<mandate leg id this claim addresses, if any>",
      "calculationId": "<registered calculation id, only for derived_fact>",
      "inputEvidenceIds": ["<evidence id, for derived_fact>"],
      "assumptions": [],
      "estimates": [],
      "interpretations": []
    }
  ],
  "gaps": ["<required fact that could not be established>"],
  "assumptions": [],
  "estimates": []
}"""


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Robustly extract the first JSON object from a model response."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)
    for candidate in candidates:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            continue
        snippet = candidate[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def parse_synthesis(text: str) -> Synthesis:
    """Parse a model response into a `Synthesis`, or a gap-bearing fallback.

    A response that is not valid JSON, or whose claims are not objects, yields a
    `Synthesis` whose only content is a gap — never a silently-trusted answer.
    """
    payload = _extract_json(text)
    if payload is None:
        return Synthesis(gaps=["the model response was not valid JSON; no claims were accepted"])

    raw_claims = payload.get("claims")
    if raw_claims is not None and not isinstance(raw_claims, list):
        return Synthesis(gaps=["the model response had a malformed claims list"])
    claims = [c for c in (raw_claims or []) if isinstance(c, dict)]
    dropped = len(raw_claims or []) - len(claims)

    gaps = [str(g) for g in (payload.get("gaps") or []) if isinstance(g, (str, int, float))]
    if dropped:
        gaps.append(f"{dropped} malformed claim(s) were ignored")

    try:
        return Synthesis(
            claims=claims,
            gaps=gaps,
            assumptions=[str(a) for a in (payload.get("assumptions") or [])],
            estimates=[str(e) for e in (payload.get("estimates") or [])],
            prose=payload.get("prose") if isinstance(payload.get("prose"), str) else None,
        )
    except Exception:  # noqa: BLE001
        return Synthesis(gaps=["the model response could not be validated"])


def _object_row(obj: Any) -> dict[str, Any]:
    return {
        "name": getattr(obj, "name", None),
        "value": getattr(obj, "value", None),
        "unit": getattr(obj, "unit", None),
        "currency": getattr(obj, "currency", None),
        "period": getattr(obj, "period", None),
        "basis": getattr(obj, "basis", None),
        "dataTimestamp": getattr(obj, "dataTimestamp", None),
        "publishedAt": getattr(obj, "publishedAt", None),
        "instrument": getattr(obj, "instrument", None),
    }


def _select_objects(objects: list[Any], wanted: set[str], wanted_periods: set[str]) -> list[Any]:
    """Choose up to MAX_OBJECTS_PER_ITEM objects, prioritising the requested facts.

    The previous blind `objects[:20]` slice was a real bug: `normalize_fundamentals`
    emits period-by-period, so a multi-year statement packet's first 20 objects
    were ALL the oldest fiscal year — the model literally never saw the requested
    periods. Objects matching a requested metric are surfaced first, and within
    that, objects whose period matches a requested period come first; the
    remainder fill the budget in original order.
    """
    if len(objects) <= MAX_OBJECTS_PER_ITEM:
        return list(objects)

    from .periods import periods_match

    def priority(obj: Any) -> tuple[int, int]:
        name = str(getattr(obj, "name", "") or "").strip().lower()
        metric_hit = 0 if name in wanted else 1
        if not wanted_periods:
            return (metric_hit, 0)
        period_hit = 0 if any(
            periods_match(req, getattr(obj, "period", None))
            or periods_match(req, getattr(obj, "dataTimestamp", None), candidate_is_timestamp=True)
            for req in wanted_periods
        ) else 1
        return (metric_hit, period_hit)

    indexed = list(enumerate(objects))
    ordered = sorted(indexed, key=lambda pair: (priority(pair[1]), pair[0]))
    return [obj for _, obj in ordered[:MAX_OBJECTS_PER_ITEM]]


def build_evidence_packet(
    evidence: list[Any],
    wanted_metrics: Optional[set[str]] = None,
    wanted_periods: Optional[set[str]] = None,
) -> str:
    """A bounded, deterministic JSON packet of the evidence the model may cite.

    When `wanted_metrics`/`wanted_periods` are supplied, each item's objects are
    selected so the requested facts are included even for a large multi-period
    statement.
    """
    wanted = {m.strip().lower() for m in (wanted_metrics or set())}
    periods = {p.strip() for p in (wanted_periods or set()) if p}
    items: list[dict[str, Any]] = []
    for item in evidence[:MAX_EVIDENCE_ITEMS]:
        source = getattr(item, "source", None)
        objects = [
            _object_row(obj)
            for obj in _select_objects(getattr(item, "objects", []) or [], wanted, periods)
        ]
        items.append(
            {
                "evidenceId": getattr(item, "id", None),
                "kind": getattr(item, "kind", None),
                "source": getattr(source, "source", None) if source else None,
                "sourceType": getattr(source, "sourceType", None) if source else None,
                "url": getattr(source, "url", None) if source else None,
                "publishedAt": getattr(source, "publishedAt", None) if source else None,
                "summary": (getattr(item, "summary", "") or "")[:MAX_SUMMARY_CHARS],
                "objects": objects,
            }
        )

    packet = json.dumps({"evidence": items}, default=str, ensure_ascii=False)
    if len(packet) > MAX_PACKET_CHARS:
        packet = packet[:MAX_PACKET_CHARS]
    return packet


def build_user_prompt(
    mandate: ResearchMandate,
    evidence: list[Any],
    coverage: CoverageReport,
    repair: Optional[dict[str, Any]] = None,
) -> str:
    """Assemble the bounded synthesis input (mandate + packet + coverage)."""
    legs = [
        {
            "legId": leg.id,
            "metric": leg.metric,
            "period": leg.period,
            "basis": leg.basis,
            "currency": leg.currency,
            "unit": leg.unit,
        }
        for leg in mandate.factLegs
    ]
    coverage_rows = [
        {"legId": c.legId, "status": c.status, "reason": c.reason} for c in coverage.legs
    ]
    wanted_metrics = {leg.metric for leg in mandate.factLegs}
    wanted_periods = {leg.period for leg in mandate.factLegs if leg.period}
    parts = [
        "OBJECTIVE:\n" + mandate.objective,
        "MANDATE FACT LEGS (what the answer must establish):\n" + json.dumps(legs, ensure_ascii=False),
        "COVERAGE (deterministic):\n" + json.dumps(coverage_rows, ensure_ascii=False),
        "EVIDENCE PACKET (the ONLY facts you may cite):\n"
        + build_evidence_packet(evidence, wanted_metrics, wanted_periods),
    ]
    if mandate.asOf:
        parts.append(f"AS-OF CUTOFF: {mandate.asOf} (evidence published after this is not admissible)")
    if repair:
        parts.append(
            "REPAIR REQUIRED — your previous answer had these problems. Fix them by citing only "
            "valid evidence ids, or move the fact to gaps:\n" + json.dumps(repair, ensure_ascii=False)[:6000]
        )
    parts.append("Return ONLY the JSON object described in the system instructions.")
    return "\n\n".join(parts)


def _extract_usage(message: Any) -> tuple[int, int]:
    """Best-effort (prompt, completion) tokens; missing usage yields (0, 0)."""
    prompt = completion = 0
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
    meta = getattr(message, "response_metadata", None) or {}
    if isinstance(meta, dict):
        raw = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(raw, dict):
            prompt = prompt or int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
            completion = completion or int(raw.get("completion_tokens") or raw.get("output_tokens") or 0)
    return prompt, completion


class ModelSynthesizer:
    """A `SynthesizeFn` backed by a LangChain chat model.

    Accumulates reported token usage in `self.usage` so the run can account for
    synthesis tokens honestly (never estimated).
    """

    def __init__(self, model: Any, *, timeout_s: float = 60.0) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self.usage = {"promptTokens": 0, "completionTokens": 0, "calls": 0}

    async def __call__(
        self,
        mandate: ResearchMandate,
        evidence: list[Any],
        coverage: CoverageReport,
        *,
        repair: Optional[dict[str, Any]] = None,
    ) -> Synthesis:
        import asyncio

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
            HumanMessage(content=build_user_prompt(mandate, evidence, coverage, repair)),
        ]
        response = await asyncio.wait_for(self._model.ainvoke(messages), timeout=self._timeout_s)
        text = _message_text(response)
        prompt_tokens, completion_tokens = _extract_usage(response)
        self.usage["promptTokens"] += prompt_tokens
        self.usage["completionTokens"] += completion_tokens
        self.usage["calls"] += 1
        return parse_synthesis(text)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


__all__ = [
    "MAX_EVIDENCE_ITEMS",
    "SYNTHESIS_SYSTEM_PROMPT",
    "parse_synthesis",
    "build_evidence_packet",
    "build_user_prompt",
    "ModelSynthesizer",
]

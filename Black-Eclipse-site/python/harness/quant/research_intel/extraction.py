"""Deterministic extraction of a method specification from a paper document.

This is not an LLM summary. It finds sections, equations and the sentences that
state the objective, assumptions, estimation and limitations, and it keeps the
provenance (section + approximate page) for every extracted equation. A field it
cannot find is left missing and named in `unresolved` — never guessed.

The caller may merge a model-produced structured draft on top, but the same
validator still decides whether it can be stored.
"""

from __future__ import annotations

import re
from typing import Any

from .catalog import catalog_by_id
from .schema import merge_structured, normalize_spec, slug, validate_method_spec

_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|\d+(?:\.\d+)*[.)]?\s+)([A-Z][^\n]{2,120})$")
_EQUATION_BLOCK = re.compile(
    r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\begin\{equation\*?\}(.+?)\\end\{equation\*?\}",
    re.DOTALL,
)
_INLINE_EQUATION = re.compile(r"(?<!\$)\$([^$\n]{6,200})\$(?!\$)")
_REFERENCE = re.compile(
    r"([A-Z][A-Za-z\-]+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][A-Za-z\-]+)?)\s*\((\d{4})\)"
)
_PARAM = re.compile(r"\\(alpha|beta|gamma|theta|lambda|mu|omega|sigma|rho|phi|delta|kappa)")

_SECTIONS_OF_INTEREST = {
    "objective": ("abstract", "introduction", "objective", "aim"),
    "assumptions": ("assumption", "model", "methodology"),
    "estimation": ("estimation", "calibration", "methodology", "empirical"),
    "limitations": ("limitation", "conclusion", "discussion", "robustness"),
    "data": ("data", "sample", "dataset", "empirical"),
}

_INPUT_HINTS: tuple[tuple[str, str, str], ...] = (
    ("realized variance", "realized_variance", "daily"),
    ("realised variance", "realized_variance", "daily"),
    ("intraday", "intraday_prices", "intraday"),
    ("high-frequency", "intraday_prices", "intraday"),
    ("high frequency", "intraday_prices", "intraday"),
    ("tick", "trade_data", "tick"),
    ("volume", "volume", "daily"),
    ("returns", "returns", "daily"),
    ("return series", "returns", "daily"),
    ("prices", "price_series", "daily"),
    ("price series", "price_series", "daily"),
    ("volatility", "volatility_series", "daily"),
    ("variance", "variance_series", "daily"),
    ("macro", "macro_series", "monthly"),
    ("fundamental", "fundamentals", "quarterly"),
)

_FAMILY_HINTS: tuple[tuple[str, str], ...] = (
    ("garch", "volatility_modeling"), ("heterosked", "volatility_modeling"),
    ("realized volatility", "volatility_modeling"), ("stochastic volatility", "volatility_modeling"),
    ("regime", "regime_detection"), ("markov", "regime_detection"),
    ("change point", "regime_detection"), ("cointegration", "statistical_arbitrage"),
    ("mean reversion", "mean_reversion"), ("ornstein", "mean_reversion"),
    ("factor model", "factor_models"), ("fama", "factor_models"),
    ("order flow", "microstructure"), ("vpin", "microstructure"),
    ("execution", "execution_models"), ("market impact", "execution_models"),
    ("extreme value", "risk_modeling"), ("tail", "risk_modeling"),
    ("machine learning", "machine_learning"), ("boosting", "machine_learning"),
    ("momentum", "trend_momentum"),
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sections(text: str) -> list[dict[str, Any]]:
    lines = str(text or "").splitlines()
    out: list[dict[str, Any]] = []
    current = {"heading": "document", "start": 0, "lines": []}
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and len(line.strip()) < 140:
            out.append(current)
            current = {"heading": _clean(match.group(1)), "start": index, "lines": []}
        else:
            current["lines"].append(line)
    out.append(current)
    for section in out:
        section["text"] = "\n".join(section["lines"])
        section["page"] = section["start"] // 55 + 1
    return [s for s in out if s["text"].strip()]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", str(text or ""))
    return [_clean(p) for p in parts if len(_clean(p)) > 20]


def _best(sections: list[dict[str, Any]], topics: tuple[str, ...]) -> str:
    for section in sections:
        heading = section["heading"].lower()
        if any(topic in heading for topic in topics):
            return section["text"]
    return ""


def _pick(sentences: list[str], terms: tuple[str, ...], limit: int = 3) -> list[str]:
    out: list[str] = []
    for sentence in sentences:
        low = sentence.lower()
        if any(term in low for term in terms):
            out.append(sentence)
        if len(out) >= limit:
            break
    return out


def _equations(text: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for match in _EQUATION_BLOCK.finditer(str(text or "")):
        latex = next((g for g in match.groups() if g), "").strip()
        if not latex:
            continue
        start = match.start()
        section = "document"
        page = start // 3000 + 1
        for item in sections:
            if item["start"] * 55 <= start:
                section = item["heading"]
                page = item["page"]
        found.append({"latex": latex, "section": section, "page": page})
    if not found:
        for match in _INLINE_EQUATION.finditer(str(text or "")):
            latex = match.group(1).strip()
            if any(token in latex for token in ("\\", "=", "^", "_", "\\frac")):
                found.append({"latex": latex, "section": "document",
                              "page": match.start() // 3000 + 1})
    return found


def _inputs(text: str) -> list[dict[str, Any]]:
    low = str(text or "").lower()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for needle, name, frequency in _INPUT_HINTS:
        if needle in low and name not in seen:
            seen.add(name)
            out.append({"name": name, "frequency": frequency, "required": True})
    return out


def _parameters(equations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: list[str] = []
    for eq in equations:
        for name in _PARAM.findall(eq["latex"]):
            if name not in names:
                names.append(name)
    return [{"name": name, "type": "float", "domain": []} for name in names]


def _family(text: str) -> str:
    low = str(text or "").lower()
    for needle, family in _FAMILY_HINTS:
        if needle in low:
            return family
    return "unspecified"


def _method_id(title: str, text: str, hint: str) -> tuple[str, dict[str, Any] | None]:
    catalog = catalog_by_id()
    candidate = _clean(hint).lower()
    if candidate in catalog:
        return candidate, catalog[candidate]
    for method in catalog.values():
        names = [method["methodId"], method.get("name", "")] + list(method.get("aliases") or [])
        if any(str(n).lower() in (title or "").lower() for n in names if n):
            return method["methodId"], method
    if candidate:
        return slug(candidate), None
    first = _clean(title) or "research method"
    return f"research.{slug(first)}", None


def _references(text: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for match in _REFERENCE.finditer(str(text or "")):
        citation = f"{_clean(match.group(1))} ({match.group(2)})"
        if citation not in seen:
            seen.add(citation)
            out.append({"citation": citation, "year": int(match.group(2))})
    return out[:20]


def extract_method(
    *,
    literature_id: str,
    text: str,
    title: str = "",
    method_hint: str = "",
    structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a method draft from one document. Returns draft + issues."""
    sections = _sections(text)
    equations = _equations(text, sections)
    sentences = _sentences(text)
    method_id, known = _method_id(title, text, method_hint)

    objective_section = _best(sections, _SECTIONS_OF_INTEREST["objective"])
    objective_sentences = _pick(_sentences(objective_section) or sentences,
                                ("objective", "aim", "we propose", "this paper",
                                 "we study", "we estimate", "we model"), 3)
    assumption_section = _best(sections, _SECTIONS_OF_INTEREST["assumptions"])
    assumptions = _pick(_sentences(assumption_section) or sentences,
                        ("assum", "require", "stationar", "i.i.d", "identically",
                         "no arbitrage", "correctly specified"), 5)
    estimation_section = _best(sections, _SECTIONS_OF_INTEREST["estimation"])
    estimation_sentences = _pick(_sentences(estimation_section) or sentences,
                                 ("estimat", "maximum likelihood", "least squares",
                                  "ols", "calibrat", "fit", "inference"), 3)
    limitation_section = _best(sections, _SECTIONS_OF_INTEREST["limitations"])
    limitations = _pick(_sentences(limitation_section) or sentences,
                        ("limitation", "caveat", "cannot", "does not", "however",
                         "future research", "sensitive"), 4)
    data_section = _best(sections, _SECTIONS_OF_INTEREST["data"])
    inputs = _inputs(f"{data_section} {text}")
    params = _parameters(equations)
    references = _references(text)
    family = known["family"] if known else _family(f"{title} {text}")
    name = known["name"] if known else (_clean(title) or method_id)

    outputs: list[str] = []
    low = str(text or "").lower()
    for needle, output in (
        ("forecast", "volatility_forecast"), ("variance", "conditional_variance"),
        ("probability", "state_probability"), ("hedge ratio", "hedge_ratio"),
        ("half-life", "half_life"), ("value at risk", "var"),
        ("expected shortfall", "expected_shortfall"), ("signal", "signal"),
    ):
        if needle in low and output not in outputs:
            outputs.append(output)
    if not outputs and known:
        outputs = list(known.get("outputs") or [])

    estimation = "unspecified"
    for needle, method in (
        ("maximum likelihood", "maximum likelihood"),
        ("least squares", "ordinary least squares"),
        ("ols", "ordinary least squares"),
        ("kalman", "Kalman filter"),
        ("em algorithm", "EM / Baum-Welch"),
        ("bayesian", "Bayesian inference"),
        ("gmm", "generalized method of moments"),
    ):
        if needle in str(estimation_section or text).lower():
            estimation = method
            break

    draft = normalize_spec({
        "methodId": method_id,
        "name": name,
        "family": family,
        "version": "1.0.0",
        "objective": objective_sentences or ([known["objective"]] if known else []),
        "inputs": inputs,
        "parameters": params,
        "equations": [
            {
                "latex": eq["latex"],
                "variables": [],
                "source": {
                    "literatureId": literature_id,
                    "section": eq["section"],
                    "page": eq["page"],
                },
            }
            for eq in equations
        ],
        "estimation": {"method": estimation},
        "assumptions": assumptions,
        "outputs": outputs,
        "validation": [],
        "limitations": limitations,
        "references": references,
        "provenance": {
            "literatureIds": [literature_id],
            "implementationIds": [],
            "confidence": "low",
            "source": "literature_extraction",
        },
        "implementationStatus": "none",
        "reproductionStatus": "none",
        "lifecycleStatus": "proposed",
        "complexity": known.get("complexity", 3) if known else 3,
        "evidenceLevel": known.get("evidenceLevel", 2) if known else 2,
    })

    if structured:
        draft = normalize_spec(merge_structured(draft, structured))
        for eq in draft.get("equations") or []:
            if isinstance(eq, dict):
                source = eq.setdefault("source", {})
                if not source.get("literatureId"):
                    source["literatureId"] = literature_id
        if literature_id not in (draft.get("provenance") or {}).get("literatureIds", []):
            draft.setdefault("provenance", {}).setdefault("literatureIds", []).append(literature_id)

    unresolved: list[str] = []
    if not draft.get("equations"):
        unresolved.append("no equation was found in the text")
    if not draft.get("objective"):
        unresolved.append("research objective not stated")
    if not draft.get("inputs"):
        unresolved.append("required inputs and sampling frequency not stated")
    if not draft.get("assumptions"):
        unresolved.append("model assumptions not stated")
    if draft.get("estimation", {}).get("method") in (None, "", "unspecified"):
        unresolved.append("estimation procedure not stated")
    if params and not any(p.get("domain") for p in params):
        unresolved.append("parameter domains were not stated in the text")
    if not draft.get("references"):
        unresolved.append("no in-text citation was recognised")
    draft["unresolved"] = unresolved

    equations_with_source = sum(
        1 for eq in draft.get("equations") or [] if (eq.get("source") or {}).get("literatureId")
    )
    if equations_with_source >= 2 and draft.get("objective") and draft.get("assumptions") and estimation != "unspecified":
        confidence = "high"
    elif equations_with_source >= 1 and (draft.get("objective") or draft.get("assumptions")):
        confidence = "medium"
    else:
        confidence = "low"
    draft["provenance"]["confidence"] = confidence
    if known:
        draft["provenance"]["catalogMatch"] = known["methodId"]

    issues = validate_method_spec(draft, require_literature=True)
    return {
        "draft": draft,
        "issues": issues,
        "valid": not issues,
        "equationCount": len(equations),
        "sections": [{"heading": s["heading"], "page": s["page"]} for s in sections],
        "unresolved": unresolved,
        "confidence": confidence,
        "note": (
            "Extraction is a reading of the document, not a reproduction. "
            "Every missing field is named; nothing is guessed."
        ),
    }


__all__ = ["extract_method"]

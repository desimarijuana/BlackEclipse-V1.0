"""Structured-response grader (the offline "visual delivery" check).

The final answer must carry its required TEXT (the answer survives), and its
``eclipse-response`` fences must decode: closed, valid JSON, a ``blocks`` list,
and — when required — a chart block with at least one named series carrying data.
This is the Python-side smoke check of the producer contract; the TypeScript
contract (``src/lib/response/contract.ts``) remains the authority and its
renderer robustness is covered by the front-end tests.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import GradeContext, Grader, GraderResult

_OPEN = re.compile(r"^ {0,3}(?:`{3,}|~{3,})\s*eclipse-response\s*$")
_CLOSE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})\s*$")


def _fences(text: str) -> list[dict[str, Any]]:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fences: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if _OPEN.match(lines[i]):
            body: list[str] = []
            i += 1
            closed = False
            while i < len(lines):
                if _CLOSE.match(lines[i]):
                    closed = True
                    i += 1
                    break
                body.append(lines[i])
                i += 1
            fences.append({"source": "\n".join(body), "closed": closed})
            continue
        i += 1
    return fences


def _decoded(fence: dict[str, Any]) -> Any:
    if not fence.get("closed"):
        return None
    try:
        return json.loads(fence["source"].strip())
    except Exception:  # noqa: BLE001 - unparseable is a real outcome
        return None


class ResponseGrader(Grader):
    name = "response"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config)
        output = ctx.final_output or ""
        failures: list[str] = []
        checks = 0

        for token in config.get("require_text") or []:
            checks += 1
            if str(token).lower() not in output.lower():
                failures.append(f"answer text missing {token!r}")

        fences = _fences(output)
        decoded = [(f, _decoded(f)) for f in fences]
        invalid = sum(
            1
            for f, value in decoded
            if not isinstance(value, dict) or not isinstance(value.get("blocks"), list)
        )
        if config.get("max_invalid_fences") is not None:
            checks += 1
            allowed = int(config["max_invalid_fences"])
            if invalid > allowed:
                failures.append(f"{invalid} invalid response fence(s) (allowed {allowed})")

        wanted = [str(t) for t in config.get("required_types_placeholder") or []]  # unused
        required_types = [str(t) for t in config.get("required_block_types") or []]
        if required_types or config.get("require_chart_series"):
            checks += 1
            found_types: set[str] = set()
            series_problems = 0
            for _f, value in decoded:
                if not isinstance(value, dict):
                    continue
                for block in value.get("blocks") or []:
                    if not isinstance(block, dict):
                        continue
                    kind = block.get("type")
                    if isinstance(kind, str):
                        found_types.add(kind)
                    if kind == "chart":
                        series = block.get("series")
                        if (
                            not isinstance(series, list)
                            or not series
                            or any(
                                not isinstance(s, dict)
                                or not isinstance(s.get("data"), list)
                                or not s.get("data")
                                for s in series
                            )
                        ):
                            series_problems += 1
            missing = [t for t in required_types if t not in found_types]
            if missing:
                failures.append(f"response blocks missing: {missing}")
            if config.get("require_chart_series") and series_problems:
                failures.append(f"{series_problems} chart block(s) lack a usable series")

        if checks == 0:
            return GraderResult.unmeasured_result(self.name, "no response contract configured")
        score = max(0.0, 1.0 - len(failures) / checks)
        return GraderResult(
            self.name, score, not failures,
            details={"fences": len(fences), "invalid_fences": invalid},
            failures=failures,
            evidence=[{"fences": len(fences)}],
        )

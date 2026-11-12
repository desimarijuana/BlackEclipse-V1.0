"""External benchmark adapters (C8.2).

One tiny protocol, four adapters. The committed fixtures are small,
license-safe, and fully offline; the real benchmark data is downloaded only when
an operator opts in (`HARNESS_EXTERNAL_IT=1`), never committed. An adapter that
has no data reports `available=False` with a reason, so a missing benchmark is
never mistaken for a passing score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from ..tasks import EvaluationTask, TaskValidationError

EXTERNAL_DIR = Path(__file__).resolve().parents[1] / "external"


@dataclass
class AdapterInfo:
    name: str
    version: str
    source: str
    license: str
    cases: int
    available: bool = True
    unmeasured_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version, "source": self.source,
            "license": self.license, "cases": self.cases,
            "available": self.available,
            "unmeasuredReason": self.unmeasured_reason or None,
        }


class DatasetAdapter(Protocol):
    name: str
    version: str

    def info(self) -> AdapterInfo: ...
    def load(self, *, split: str = "validation", limit: int = 50) -> list[EvaluationTask]: ...


@dataclass
class FixtureAdapter:
    """An offline fixture adapter; real downloads are a separate opt-in path."""

    name: str
    version: str
    source: str
    license: str
    fixture: str
    split: str = "validation"

    @property
    def path(self) -> Path:
        return EXTERNAL_DIR / self.fixture

    def _rows(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [row for row in data if isinstance(row, dict)]

    def info(self) -> AdapterInfo:
        rows = self._rows()
        return AdapterInfo(
            name=self.name, version=self.version, source=self.source, license=self.license,
            cases=len(rows), available=bool(rows),
            unmeasured_reason="" if rows else f"fixture missing: {self.path.name}",
        )

    def load(self, *, split: str = "validation", limit: int = 50) -> list[EvaluationTask]:
        rows = self._rows()[: max(1, int(limit))]
        tasks: list[EvaluationTask] = []
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            metadata.update({
                "split": metadata.get("split") or split or self.split,
                "external": {
                    "benchmark": self.name,
                    "caseId": row.get("id"),
                    "source": self.source,
                    "license": self.license,
                },
            })
            payload = {**row, "metadata": metadata}
            try:
                tasks.append(EvaluationTask.from_dict(payload))
            except TaskValidationError as exc:
                raise TaskValidationError(f"{self.name}: {exc}") from exc
        return tasks


ADAPTERS: tuple[FixtureAdapter, ...] = (
    FixtureAdapter(
        name="swe-bench-lite", version="lite-mini",
        source="https://www.swebench.com/", license="MIT (fixtures authored for this repo)",
        fixture="swebench_lite.json",
    ),
    FixtureAdapter(
        name="gaia", version="mini",
        source="https://huggingface.co/datasets/gaia-benchmark/GAIA",
        license="CC-BY-4.0 (fixtures authored for this repo)",
        fixture="gaia.json",
    ),
    FixtureAdapter(
        name="tau-bench", version="mini",
        source="https://github.com/sierra-research/tau-bench",
        license="MIT (fixtures authored for this repo)",
        fixture="taubench.json",
    ),
    FixtureAdapter(
        name="financebench", version="mini",
        source="https://github.com/patronus-ai/financebench",
        license="CC-BY-NC-4.0 (fixtures authored for this repo)",
        fixture="financebench.json",
    ),
)


def adapter_by_name(name: str) -> Optional[FixtureAdapter]:
    for adapter in ADAPTERS:
        if adapter.name == name:
            return adapter
    return None


__all__ = ["ADAPTERS", "AdapterInfo", "DatasetAdapter", "FixtureAdapter", "adapter_by_name"]

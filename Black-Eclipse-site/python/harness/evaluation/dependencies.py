"""The evaluation dependency map.

Maps a changed file / component to the evaluation suites that must run, so a
change does not force the entire benchmark. The map is data; :func:`affected_tasks`
applies it to a dataset.
"""

from __future__ import annotations

from typing import Any, Iterable

# path fragment → the categories/suites a change there can affect.
COMPONENT_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("harness/browser/", ("browser", "safety")),
    ("harness/research/web_", ("research", "citations", "finance")),
    ("harness/research/calculations", ("finance",)),
    ("harness/finance_facts/", ("finance",)),
    ("harness/market/", ("tools", "finance")),
    ("harness/retrieval/", ("tools", "research")),
    ("harness/search/", ("tools", "memory")),
    ("harness/eclipse_memory/", ("memory", "long_horizon")),
    ("harness/memory_providers/", ("memory",)),
    ("harness/model_runtime/", ("core", "planning", "regression")),
    ("harness/code/", ("coding", "tools", "safety")),
    ("harness/execution/", ("coding", "recovery")),
    ("harness/terminal/", ("tools", "recovery")),
    ("harness/tasks/", ("planning", "long_horizon", "parallel")),
    ("harness/orchestration/", ("parallel", "long_horizon")),
    ("harness/graph.py", ("core", "tools", "planning", "safety")),
    ("harness/tools.py", ("tools", "safety")),
    ("harness/skills/", ("core", "regression")),
    ("harness/mcp/", ("safety", "tools")),
    ("harness/vision/", ("browser", "core")),
    ("harness/document_intelligence/", ("research", "citations")),
    ("harness/portfolio/", ("finance",)),
    ("harness/quant/", ("finance",)),
    ("src/lib/harness/", ("core", "tools")),
)


def affected_categories(paths: Iterable[str]) -> list[str]:
    """The union of categories affected by any changed path (stable order)."""
    categories: list[str] = []
    normalized = [p.replace("\\", "/") for p in paths]
    for fragment, cats in COMPONENT_MAP:
        if any(fragment in path for path in normalized):
            for cat in cats:
                if cat not in categories:
                    categories.append(cat)
    return categories


def affected_tasks(tasks: list[Any], paths: Iterable[str]) -> list[Any]:
    """Filter a dataset to the tasks whose category a change touches.

    A path that maps to no known component returns an EMPTY list, not everything —
    an unmapped change is reported, not silently expanded to the full suite.
    """
    categories = set(affected_categories(paths))
    if not categories:
        return []
    return [task for task in tasks if task.category in categories or task.metadata.get("suite") in categories]


__all__ = ["COMPONENT_MAP", "affected_categories", "affected_tasks"]

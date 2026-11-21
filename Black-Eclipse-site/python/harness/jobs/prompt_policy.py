"""Scheduled-prompt policy: name the CAPABILITY, never the tool.

A scheduled job's prompt is persisted once and re-sent on every fire. If it names
a tool, the job breaks the day that tool is renamed, wrapped, or replaced — and
the breakage is silent until a delivery is missing. If it names a capability
("new regulatory filings", "overnight news"), the agent routes to whatever tool
currently provides it.

This module is the rule, executable: `lint_prompt` compares a prompt against the
tool names the runtime actually exposes and reports every mention with its
position and a suggested rewrite. `test_job_prompt_policy.py` runs it over every
bundled job template, so a template cannot ship with a tool name baked in.

It is deliberately a LINT, not a rewrite: a prompt that says "do not call
get_sec_filings" is a legitimate (if odd) sentence, and silently editing user
text would be worse than the problem.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

#: Tool-name shapes we look for. A name is matched as a whole token, so
#: `news` inside "news digest" is not a hit unless a tool is literally `news`.
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")

#: Functions/verbs that are ordinary English in a prompt and therefore only
#: count as a tool mention when the registry really has that name.
_IGNORE = frozenset({"open", "close", "get", "set", "run", "read", "write"})


def _tool_names(tool_names: Iterable[str] | Mapping[str, Any]) -> set[str]:
    names = tool_names.keys() if isinstance(tool_names, Mapping) else tool_names
    return {str(name) for name in names if name and str(name) not in _IGNORE}


def lint_prompt(text: str, tool_names: Iterable[str] | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every tool mention in `text`, with position and a capability hint.

    Returns `[]` when the prompt names capabilities only.
    """
    names = _tool_names(tool_names)
    if not names:
        return []
    findings: list[dict[str, Any]] = []
    for match in _TOKEN.finditer(str(text or "")):
        token = match.group(0)
        if token not in names:
            continue
        findings.append({
            "tool": token,
            "index": match.start(),
            "hint": (
                f"name the capability instead of the tool `{token}` "
                "(e.g. 'the latest price data' rather than a tool id)"
            ),
        })
    return findings


def is_clean(text: str, tool_names: Iterable[str] | Mapping[str, Any]) -> bool:
    return not lint_prompt(text, tool_names)


def lint_templates(templates: Iterable[Any], tool_names: Iterable[str] | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Lint every `objective`/`prompt` field on a template-like object."""
    problems: list[dict[str, Any]] = []
    for template in templates:
        template_id = getattr(template, "id", repr(template))
        target = getattr(template, "target", None) or {}
        for field in ("objective", "prompt"):
            value = target.get(field) if isinstance(target, dict) else getattr(target, field, None)
            if not value:
                continue
            for finding in lint_prompt(value, tool_names):
                problems.append({"template": template_id, "field": field, **finding})
    return problems


__all__ = ["is_clean", "lint_prompt", "lint_templates"]

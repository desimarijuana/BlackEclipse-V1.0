"""The bundled finance team library — YAML presets compiled to `TeamDefinition`.

A preset is a **documented collaboration pattern**, not code: members with
instructions, a dependency-aware subtask graph, and a policy. It is validated
here (unique ids, real dependencies, acyclic graph, every assignee is a member)
before the team runtime is ever touched, so a broken preset fails at load time
with a line number instead of half-way through a run.

`evidence_required` on a subtask is what makes the library different from a
prompt pack: a completed subtask with no evidence reference is refused by the
team service, so "the bull case" cannot be an unsourced paragraph.

Rendering: `{target}` / `{horizon}` style placeholders are substituted from the
declared `variables` list. A missing declared variable is an error, not a
silently literal `{target}` in a prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from .model import TeamDefinition

PRESET_DIR = Path(__file__).resolve().parent / "presets"

_VAR = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass(frozen=True)
class TeamPreset:
    """One bundled preset: its catalogue record plus the compiled definition."""

    id: str
    name: str
    description: str
    variables: tuple[str, ...]
    definition: TeamDefinition
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "variables": list(self.variables),
            "members": len(self.definition.members),
            "subtasks": len(self.definition.subtasks),
            "evidenceRequired": sum(1 for s in self.definition.subtasks if s.evidence_required),
        }


def _read(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: a preset must be a YAML mapping")
    return data


def _substitute(value: Any, values: dict[str, str]) -> Any:
    if isinstance(value, str):
        return _VAR.sub(lambda m: values.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [_substitute(item, values) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, values) for key, item in value.items()}
    return value


def _cycle(nodes: dict[str, list[str]]) -> Optional[list[str]]:
    """Return a cycle path when the dependency graph has one."""
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> Optional[list[str]]:
        if state.get(node) == 1:
            return stack[stack.index(node):] + [node]
        if state.get(node) == 2:
            return None
        state[node] = 1
        stack.append(node)
        for dep in nodes.get(node, []):
            found = visit(dep, stack)
            if found:
                return found
        stack.pop()
        state[node] = 2
        return None

    for name in nodes:
        found = visit(name, [])
        if found:
            return found
    return None


def validate_definition(definition: TeamDefinition) -> list[str]:
    """Every structural problem with a team definition. Empty = valid."""
    problems: list[str] = []
    member_ids = [m.agent_id for m in definition.members]
    if len(member_ids) != len(set(member_ids)):
        problems.append("duplicate member agentId")
    subtask_ids = [s.id for s in definition.subtasks]
    if len(subtask_ids) != len(set(subtask_ids)):
        problems.append("duplicate subtask id")
    known = set(subtask_ids)
    members = set(member_ids)
    graph: dict[str, list[str]] = {}
    for subtask in definition.subtasks:
        graph[subtask.id] = list(subtask.depends_on)
        for dep in subtask.depends_on:
            if dep not in known:
                problems.append(f"subtask {subtask.id!r} depends on unknown {dep!r}")
            if dep == subtask.id:
                problems.append(f"subtask {subtask.id!r} depends on itself")
        if subtask.assigned_agent_id and subtask.assigned_agent_id not in members:
            problems.append(
                f"subtask {subtask.id!r} is assigned to {subtask.assigned_agent_id!r}, "
                "which is not a member"
            )
    cycle = _cycle(graph)
    if cycle:
        problems.append("dependency cycle: " + " -> ".join(cycle))
    # The lead may be the built-in orchestrator (it delegates to the members);
    # any other lead must itself be a member.
    if definition.agent_id and definition.agent_id not in members \
            and definition.agent_id != "eclipse-orchestrator":
        problems.append(f"lead agent {definition.agent_id!r} is not a member")
    return problems


#: Keys that belong to the preset catalogue, not to `TeamDefinition`.
_PRESET_ONLY = ("description", "variables")


def _definition_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key not in _PRESET_ONLY}


def _compile(path: Path) -> TeamPreset:
    raw = _read(path)
    variables = tuple(raw.get("variables") or ())
    definition = TeamDefinition.model_validate(_definition_payload(raw))
    problems = validate_definition(definition)
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems))
    return TeamPreset(
        id=definition.id,
        name=definition.name,
        description=definition.objective or definition.name,
        variables=variables,
        definition=definition,
        path=str(path),
    )


def load_presets() -> list[TeamPreset]:
    """Every bundled preset, sorted by id. Raises on a malformed preset."""
    presets = [_compile(path) for path in sorted(PRESET_DIR.glob("*.yaml"))]
    ids = [preset.id for preset in presets]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate preset id in the bundled library")
    return presets


def list_presets() -> list[dict[str, Any]]:
    """Catalogue records only (no definition), for a picker."""
    return [preset.to_dict() for preset in load_presets()]


def get_preset(preset_id: str) -> Optional[TeamPreset]:
    for preset in load_presets():
        if preset.id == str(preset_id or "").strip():
            return preset
    return None


def render_preset(preset: TeamPreset, **values: Any) -> TeamDefinition:
    """Substitute the preset's declared variables into a concrete definition.

    Missing declared variables raise (a prompt must never ship with a literal
    `{target}`); undeclared placeholders are left untouched.
    """
    supplied = {str(key): str(value) for key, value in values.items()}
    missing = [name for name in preset.variables if name not in supplied]
    if missing:
        raise ValueError(f"{preset.id}: missing variables: {', '.join(missing)}")
    raw = _read(Path(preset.path))
    rendered = _substitute(raw, supplied)
    return TeamDefinition.model_validate(_definition_payload(rendered))


def evidence_subtasks(definition: TeamDefinition) -> list[str]:
    return [s.id for s in definition.subtasks if s.evidence_required]


__all__ = [
    "PRESET_DIR",
    "TeamPreset",
    "evidence_subtasks",
    "get_preset",
    "list_presets",
    "load_presets",
    "render_preset",
    "validate_definition",
]

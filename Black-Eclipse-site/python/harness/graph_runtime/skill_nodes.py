"""Skill node.

The graph node is a thin adapter over the EXISTING skill runtime
(`AgenticService.run_skill` → `skills.runtime.execute_skill`): it does not create
a second skill runtime, tool allowlist, permission check or version resolver.
`bootstrap.py` binds a runner at boot so tests can substitute a fake and this
module never imports the whole service.

ONE generic node, not one per installed skill: skills are runtime data, while the
node registry is a static contract mirrored by the TS manifest.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_INPUT_JSON = 20_000

# The skill runtime reports a successful run as `completed`
# (`SkillExecutionResult`). Anything else is a real failure and must fail the
# node — never an empty success.
SKILL_SUCCESS_STATUSES = frozenset({"completed"})

SkillRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_runner: Optional[SkillRunner] = None


def set_skill_runner(runner: Optional[SkillRunner]) -> None:
    global _runner
    _runner = runner


def _payload(context: NodeExecContext) -> dict[str, Any]:
    """Merge the configured Input (JSON) with the wired `input` object.

    The wire wins per key: a graph that computes one field can still inherit the
    rest from the node's saved payload.
    """
    raw = context.inputs.get("input")
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("input must be an object of named skill inputs")
    payload: dict[str, Any] = {}
    text = str(context.config.get("inputJson") or "").strip()
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Input (JSON) is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Input (JSON) must be an object of named skill inputs")
        payload.update(parsed)
    if isinstance(raw, dict):
        payload.update(raw)
    return payload


def _failure_detail(result: dict[str, Any]) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        if code and message:
            return f"{code}: {message}"
        return message or code
    if isinstance(error, str) and error.strip():
        return error.strip()
    return "no detail reported"


def exec_skill_invoke(context: NodeExecContext) -> dict[str, Any]:
    skill_id = str(context.config.get("skillId") or "").strip()
    if not skill_id:
        raise ValueError(
            "skill.invoke needs a skill: pick one in the inspector (Skill) "
            "or set skillId in the node config"
        )
    payload = _payload(context)
    if _runner is None:
        raise ValueError("the skill runtime is not configured in this graph runtime")
    version = str(context.config.get("version") or "").strip() or None
    config = {
        "skillId": skill_id,
        "version": version,
        "input": payload,
        "timeoutMs": int(context.config.get("timeoutMs") or 300_000),
    }
    result = _runner(context, config)
    if not isinstance(result, dict):
        raise ValueError("the skill runner returned no structured result")

    status = str(result.get("status") or "").strip().lower()
    if status not in SKILL_SUCCESS_STATUSES:
        raise ValueError(
            f"skill {skill_id} did not complete ({status or 'no status'}): "
            f"{_failure_detail(result)}"
        )

    output = result.get("output")
    context.emit(f"skill {skill_id} completed")
    return {
        "output": "" if output is None else str(output),
        # Bounded, provenance-carrying projection — not the raw execution row.
        "result": {
            "status": status,
            "skillId": result.get("skillId") or skill_id,
            "version": result.get("version"),
            "runId": result.get("runId"),
            "traceId": result.get("traceId"),
            "outputValidated": bool(result.get("outputValidated")),
            "warnings": list(result.get("warnings") or []),
            "missingData": list(result.get("missingData") or []),
            "limitations": list(result.get("limitations") or []),
            "metrics": dict(result.get("metrics") or {}),
        },
        "evidence": list(result.get("evidence") or []),
    }


def build_skill_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="skill.invoke", version="1.0.0", label="Run skill",
            category="skills",
            # Optional: the configured Input (JSON) is a valid alternative, and
            # `_payload` merges the wire over it per key.
            inputs=(PortDef(id="input", name="Input", type=PortType.OBJECT, optional=True),),
            outputs=(
                PortDef(id="output", name="Output", type=PortType.STRING),
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("skillId", "string", "", max_length=120),
                ConfigField("version", "string", "", max_length=40),
                ConfigField("inputJson", "string", "", max_length=MAX_INPUT_JSON),
                ConfigField("timeoutMs", "integer", 300_000, minimum=1_000, maximum=900_000),
            ),
            # A skill call is a model call on the agent plane. Reusing
            # `agent.run` keeps one capability vocabulary; the skill's OWN
            # permission check still runs inside the runtime.
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_skill_invoke,
            metadata={
                "docs": (
                    "Runs the EXISTING skill runtime (`execute_skill`) for the "
                    "selected skill@version. Status is the contract: only "
                    "`completed` produces outputs; not-enabled, missing-tool, "
                    "denied-permission, failed and cancelled all fail this node "
                    "with their code. A test/dry run may only execute a skill "
                    "whose declared tools are all read-only `DRY_RUN_TOOLS`."
                ),
            },
        ),
    ]


__all__ = [
    "MAX_INPUT_JSON",
    "SKILL_SUCCESS_STATUSES",
    "build_skill_nodes",
    "exec_skill_invoke",
    "set_skill_runner",
]

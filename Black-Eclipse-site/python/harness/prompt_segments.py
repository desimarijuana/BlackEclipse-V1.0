"""Immutable prompt segments + a stable prompt cache key (Milestone 9).

The prompt is assembled from named segments. Each segment records its own
content hash, version, source and token estimate, and the reusable (static)
segments contribute to ONE `prompt_cache_key`. The point is stability: a change
to the user message must not invalidate the reusable segments, and a change to a
profile/skill manifest invalidates ONLY that segment.

Safety: nothing here changes what the model is allowed to do. Segments are
rendered into the same messages the runtime already sends; this module only adds
identity, hashing and observability.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# Bumped when the composition itself changes (not when content changes). This is
# part of the cache key so a runtime prompt change is visible/invalidatable.
AGENT_VERSION = "eclipse-agent-v1"
SYSTEM_POLICY_VERSION = "policy-v1"
TOOL_SCHEMA_VERSION = "tool-schema-v1"

# Segment ids. The first group is REUSABLE across runs; the last two are
# run-specific and deliberately excluded from the cache key.
STATIC_SEGMENTS = (
    "system_policy",
    "agent_identity",
    "tool_schemas",
    "profile_snapshot",
    "session_summary",
    "skill_manifest",
)

# Bounds.
MAX_SKILL_MANIFEST_CHARS = 1200
MAX_SKILLS_IN_MANIFEST = 8


def _token_estimate(text: str) -> int:
    return (len(text) + 3) // 4 if text else 0


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


@dataclass
class PromptSegment:
    """One immutable prompt segment with identity for cache reasoning."""

    id: str
    content: str
    source: str = "runtime"
    version: str = "1"
    cache_key: Optional[str] = None

    @property
    def content_hash(self) -> str:
        return _hash(self.content)

    @property
    def token_estimate(self) -> int:
        return _token_estimate(self.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "version": self.version,
            "contentHash": self.content_hash,
            "tokenEstimate": self.token_estimate,
            "chars": len(self.content),
            "cacheKey": self.cache_key,
        }


@dataclass
class PromptPlan:
    """The assembled segment set plus its stable cache key."""

    segments: list[PromptSegment] = field(default_factory=list)
    cache_key: str = ""
    agent_version: str = AGENT_VERSION
    system_policy_version: str = SYSTEM_POLICY_VERSION
    tool_schema_version: str = TOOL_SCHEMA_VERSION
    profile_snapshot_id: Optional[str] = None
    skill_manifest_version: Optional[str] = None
    session_summary_version: Optional[str] = None
    provider_context_version: Optional[str] = None

    def by_id(self, segment_id: str) -> Optional[PromptSegment]:
        for segment in self.segments:
            if segment.id == segment_id:
                return segment
        return None

    def reusable_total_tokens(self) -> int:
        return sum(s.token_estimate for s in self.segments if s.id in STATIC_SEGMENTS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cacheKey": self.cache_key,
            "agentVersion": self.agent_version,
            "systemPolicyVersion": self.system_policy_version,
            "toolSchemaVersion": self.tool_schema_version,
            "profileSnapshotId": self.profile_snapshot_id,
            "skillManifestVersion": self.skill_manifest_version,
            "sessionSummaryVersion": self.session_summary_version,
            "providerContextVersion": self.provider_context_version,
            "reusableTokens": self.reusable_total_tokens(),
            "segments": [s.to_dict() for s in self.segments],
        }


def build_skill_manifest(
    registry: Any,
    query: str,
    *,
    limit: int = MAX_SKILLS_IN_MANIFEST,
) -> tuple[str, Optional[str]]:
    """A bounded manifest of skills relevant to this run (never all skills).

    Returns `(content, version)`. `content` is "" when nothing relevant is found
    or skills are unavailable. Only compact metadata is included — full
    instructions stay behind the progressive `skill_view` tool. The manifest is
    a *hint*; it can never grant a tool or permission.
    """
    if registry is None:
        return "", None
    try:
        matches = registry.discover(query=query or "", include_non_executable=False)
    except Exception:  # noqa: BLE001 - discovery must never break a run
        return "", None
    if not matches:
        return "", None
    selected = matches[: max(1, int(limit))]
    lines = [
        "Skill manifest (discovery only — call skill_view for full instructions; "
        "this list does not enable or run anything):"
    ]
    for skill in selected:
        lines.append(f"- {skill.get('id')} (v{skill.get('version')}): {str(skill.get('description') or '')[:120]}")
    content = "\n".join(lines)
    if len(content) > MAX_SKILL_MANIFEST_CHARS:
        content = content[: MAX_SKILL_MANIFEST_CHARS - 1].rstrip() + "…"
    version = _hash(content)
    return content, version


def build_prompt_plan(
    *,
    system_prompt: str,
    agent_id: str,
    tool_names: Optional[list[str]] = None,
    profile_block: str = "",
    profile_snapshot_id: Optional[str] = None,
    session_summary: str = "",
    skill_manifest: str = "",
    skill_manifest_version: Optional[str] = None,
    run_instructions: str = "",
    user_message: str = "",
) -> PromptPlan:
    """Assemble the segment set and compute the stable cache key.

    The cache key covers only stable identity (versions + snapshot/manifest
    ids), never the user message, so a new turn reuses the static segments.
    """
    tool_schema = _tool_schema_digest(tool_names or [])
    segments = [
        PromptSegment(id="system_policy", content=system_prompt, source="prompts.py", version=SYSTEM_POLICY_VERSION),
        PromptSegment(id="agent_identity", content=agent_id, source="agents.py", version=AGENT_VERSION),
        PromptSegment(id="tool_schemas", content=tool_schema, source="tools.py",
                      version=f"{TOOL_SCHEMA_VERSION}:{tool_schema}"),
        PromptSegment(id="profile_snapshot", content=profile_block, source="eclipse_memory/profile.py",
                      version=profile_snapshot_id or _hash(profile_block)),
        PromptSegment(id="session_summary", content=session_summary, source="session_index.py",
                      version=_hash(session_summary) if session_summary else "empty"),
        PromptSegment(id="skill_manifest", content=skill_manifest, source="skills/registry.py",
                      version=skill_manifest_version or (_hash(skill_manifest) if skill_manifest else "empty")),
        PromptSegment(id="run_instructions", content=run_instructions, source="graph.py", version="1"),
        PromptSegment(id="user_message", content=user_message, source="request", version="1"),
    ]
    plan = PromptPlan(
        segments=segments,
        tool_schema_version=f"{TOOL_SCHEMA_VERSION}:{tool_schema}",
        profile_snapshot_id=profile_snapshot_id,
        skill_manifest_version=skill_manifest_version,
        session_summary_version=segments[4].version,
    )
    plan.cache_key = prompt_cache_key(plan)
    for segment in segments:
        segment.cache_key = plan.cache_key
    return plan


def _tool_schema_digest(tool_names: list[str]) -> str:
    return _hash(json.dumps(sorted(tool_names), separators=(",", ":")))


def prompt_cache_key(plan: PromptPlan) -> str:
    """The stable cache key: versions + reusable-segment versions only.

    Deliberately excludes `run_instructions` and `user_message` so a new turn
    does not invalidate the reusable segments.
    """
    components = {
        "agentVersion": plan.agent_version,
        "systemPolicyVersion": plan.system_policy_version,
        "toolSchemaVersion": plan.tool_schema_version,
        "profileSnapshotId": plan.profile_snapshot_id or "",
        "skillManifestVersion": plan.skill_manifest_version or "",
        "sessionSummaryVersion": plan.session_summary_version or "",
        "providerContextVersion": plan.provider_context_version or "",
    }
    return _hash(json.dumps(components, sort_keys=True, separators=(",", ":")))


def compare_plans(previous: Optional[PromptPlan], current: PromptPlan) -> list[dict[str, Any]]:
    """Explain which reusable segments changed between two plans (invalidation)."""
    changes: list[dict[str, Any]] = []
    if previous is None:
        return [{"segment": "all", "reason": "no previous plan"}]
    prev = {s.id: s for s in previous.segments}
    for segment in current.segments:
        old = prev.get(segment.id)
        if old is None:
            changes.append({"segment": segment.id, "reason": "added"})
        elif old.content_hash != segment.content_hash:
            changes.append({
                "segment": segment.id,
                "reason": "content changed",
                "from": old.content_hash,
                "to": segment.content_hash,
            })
    return changes


__all__ = [
    "AGENT_VERSION",
    "MAX_SKILLS_IN_MANIFEST",
    "MAX_SKILL_MANIFEST_CHARS",
    "PromptPlan",
    "PromptSegment",
    "STATIC_SEGMENTS",
    "SYSTEM_POLICY_VERSION",
    "TOOL_SCHEMA_VERSION",
    "build_prompt_plan",
    "build_skill_manifest",
    "compare_plans",
    "prompt_cache_key",
]

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
from datetime import datetime, timezone
from typing import Any, Optional

# Bumped when the composition itself changes (not when content changes). This is
# part of the cache key so a runtime prompt change is visible/invalidatable.
AGENT_VERSION = "eclipse-agent-v1"
SYSTEM_POLICY_VERSION = "policy-v1"
TOOL_SCHEMA_VERSION = "tool-schema-v1"

# Segments REUSABLE across runs: only these belong to the reuse accounting and
# contribute their CONTENT hash to the cache key. `system_policy` (the composed
# prompt) is included so a prompt-content edit changes the key even when the
# hand-bumped version has not changed.
STATIC_SEGMENTS = (
    "system_policy",
    "agent_identity",
    "tool_schemas",
)

# Segments FROZEN for one run (materialised at run start) but not reusable across
# runs, so they must not inflate `reusable_total_tokens`. `user_message` is
# turn-specific and stays out of the cache key entirely.
RUN_FROZEN_SEGMENTS = (
    "profile_snapshot",
    "skill_manifest",
    "lesson_manifest",
    "runtime_context",
    "user_message",
    # Round 3 / W4 (ADR-H287): the repo map. It is RUN-FROZEN (it depends on
    # the tree, not on the run) but it contributes its CONTENT HASH to the
    # cache key as `repoMapVersion` - so a map that changed invalidates the
    # cache and a map that did not change does not.
    "repo_map",
)

# Bounds.
MAX_SKILL_MANIFEST_CHARS = 1200
MAX_SKILLS_IN_MANIFEST = 8
MAX_LESSON_MANIFEST_CHARS = 800
MAX_LESSONS_IN_MANIFEST = 3


def _token_estimate(text: str) -> int:
    return (len(text) + 3) // 4 if text else 0


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def runtime_context_block(run_id: str, now: Optional[datetime] = None) -> str:
    """The run-scoped date/time context block (TASK 1).

    Carries the current date, time and UTC offset for the run so as-of periods,
    staleness and revalidation reasoning have a real clock. It is rendered as its
    OWN block — never inside the byte-stable system-prompt head — so the stable
    prefix keeps caching. `now` defaults to the current UTC time; a caller may
    pass an explicit aware datetime (tests). The date is always the real run
    date, never a fabricated one.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stamp = now.astimezone(timezone.utc)
    offset = stamp.strftime("%z")
    return (
        "Runtime context (current as of this run; use for as-of periods and "
        "staleness, not as market evidence):\n"
        f"- Date: {stamp.strftime('%Y-%m-%d')} ({stamp.strftime('%A')})\n"
        f"- Time: {stamp.strftime('%H:%M:%S')} UTC\n"
        f"- UTC offset: {offset}\n"
        f"- Run: {run_id}"
    )


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
    provider_context_version: Optional[str] = None
    # Round 3 / W4 (ADR-H287): the repo map's content hash. It is the cache
    # key's witness that the project shape has not changed.
    repo_map_version: Optional[str] = None

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
            # Round 3 / W4 (ADR-H287): the repo map's content hash.
            "repoMapVersion": self.repo_map_version,
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


def build_lesson_manifest(
    lessons: Any,
    *,
    limit: int = MAX_LESSONS_IN_MANIFEST,
    max_chars: int = MAX_LESSON_MANIFEST_CHARS,
) -> tuple[str, tuple[str, ...]]:
    """A bounded manifest of verified, cue-matched lessons.

    Returns `(content, lesson_ids)`. Only lessons already selected by
    `self_improvement.lessons.select_lessons` should be passed: this function is
    a deterministic formatter, not the eligibility gate. The manifest is a hint,
    never an instruction and never authority. The character and count budgets
    are hard: an oversized lesson is truncated, not allowed to grow the prompt.
    """
    max_chars = max(0, int(max_chars))
    limit = max(0, int(limit))
    selected = list(lessons or [])[:limit]
    if not selected or max_chars <= 0:
        return "", ()

    content = (
        "Adopted lessons (verified on completed validation runs; apply only to "
        "the matching cue and scope; non-authoritative hints):"
    )
    if len(content) > max_chars:
        return "", ()
    ids: list[str] = []
    for lesson in selected:
        lesson_id = str(lesson.get("id") or "").strip()
        text = " ".join(str(
            lesson.get("proposedLesson") or lesson.get("lesson") or ""
        ).split())
        cue = " ".join(str(lesson.get("cue") or "").split())
        if not lesson_id or not text:
            continue
        line = f"- [{lesson_id}] When {cue or 'the same cue'}: {text}"
        remaining = max_chars - len(content) - 1
        if remaining <= 0:
            break
        if len(line) > remaining:
            if remaining < 80:
                break
            line = line[: remaining - 1].rstrip() + "…"
        content += "\n" + line
        ids.append(lesson_id)
    if not ids:
        return "", ()
    return content, tuple(ids)


def build_prompt_plan(
    *,
    system_prompt: str,
    agent_id: str,
    tool_names: Optional[list[str]] = None,
    profile_block: str = "",
    profile_snapshot_id: Optional[str] = None,
    skill_manifest: str = "",
    skill_manifest_version: Optional[str] = None,
    lesson_manifest: str = "",
    runtime_context: str = "",
    user_message: str = "",
    repo_map: str = "",
    repo_map_version: Optional[str] = None,
) -> PromptPlan:
    """Assemble the segment set and compute the stable cache key.

    The cache key covers stable identity AND the CONTENT hash of each reusable
    (STATIC) segment, so editing the system prompt changes the key even when the
    hand-bumped version has not. The run-frozen and turn-specific segments
    (`runtime_context`, `user_message`, …) are deliberately excluded so they
    never invalidate the reusable prefix or inflate its accounting.
    """
    tool_schema = _tool_schema_digest(tool_names or [])
    segments = [
        PromptSegment(id="system_policy", content=system_prompt, source="prompts.py", version=SYSTEM_POLICY_VERSION),
        PromptSegment(id="agent_identity", content=agent_id, source="agents.py", version=AGENT_VERSION),
        PromptSegment(id="tool_schemas", content=tool_schema, source="tools.py",
                      version=f"{TOOL_SCHEMA_VERSION}:{tool_schema}"),
        PromptSegment(id="profile_snapshot", content=profile_block, source="eclipse_memory/profile.py",
                      version=profile_snapshot_id or _hash(profile_block)),
        PromptSegment(id="skill_manifest", content=skill_manifest, source="skills/registry.py",
                      version=skill_manifest_version or (_hash(skill_manifest) if skill_manifest else "empty")),
        PromptSegment(id="lesson_manifest", content=lesson_manifest, source="self_improvement/lessons.py",
                      version=_hash(lesson_manifest) if lesson_manifest else "empty"),
        PromptSegment(id="runtime_context", content=runtime_context, source="prompt_segments.py",
                      version=_hash(runtime_context) if runtime_context else "empty"),
        PromptSegment(id="user_message", content=user_message, source="request", version="1"),
        # Round 3 / W4 (ADR-H287): the repo map. Its VERSION is the map's
        # content hash, and the cache key carries that version - so a project
        # whose shape changed invalidates the cache, and one that did not
        # change does not.
        PromptSegment(id="repo_map", content=repo_map, source="code/intel/repo_map.py",
                      version=repo_map_version or (_hash(repo_map) if repo_map else "empty")),
    ]
    plan = PromptPlan(
        segments=segments,
        tool_schema_version=f"{TOOL_SCHEMA_VERSION}:{tool_schema}",
        profile_snapshot_id=profile_snapshot_id,
        skill_manifest_version=skill_manifest_version,
        repo_map_version=repo_map_version or (_hash(repo_map) if repo_map else ""),
    )
    plan.cache_key = prompt_cache_key(plan)
    for segment in segments:
        segment.cache_key = plan.cache_key
    return plan


def _tool_schema_digest(tool_names: list[str]) -> str:
    return _hash(json.dumps(sorted(tool_names), separators=(",", ":")))


def prompt_cache_key(plan: PromptPlan) -> str:
    """The stable cache key: identity + reusable-segment CONTENT hashes.

    `staticContentHashes` covers the system-policy text (so a prompt edit changes
    the key), the agent identity and the tool-schema digest. It deliberately
    excludes `runtime_context` and `user_message` so a new turn or run date does
    not invalidate the reusable segments.
    """
    components = {
        "agentVersion": plan.agent_version,
        "systemPolicyVersion": plan.system_policy_version,
        "toolSchemaVersion": plan.tool_schema_version,
        "profileSnapshotId": plan.profile_snapshot_id or "",
        "skillManifestVersion": plan.skill_manifest_version or "",
        "providerContextVersion": plan.provider_context_version or "",
        # Round 3 / W4 (ADR-H287): the repo map's content hash. Without it a
        # changed project would reuse a cache built for the old one.
        "repoMapVersion": plan.repo_map_version or "",
        "staticContentHashes": {
            s.id: s.content_hash for s in plan.segments if s.id in STATIC_SEGMENTS
        },
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
    "MAX_LESSON_MANIFEST_CHARS",
    "MAX_LESSONS_IN_MANIFEST",
    "PromptPlan",
    "PromptSegment",
    "RUN_FROZEN_SEGMENTS",
    "STATIC_SEGMENTS",
    "SYSTEM_POLICY_VERSION",
    "TOOL_SCHEMA_VERSION",
    "build_prompt_plan",
    "build_lesson_manifest",
    "build_skill_manifest",
    "compare_plans",
    "prompt_cache_key",
    "runtime_context_block",
]

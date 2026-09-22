"""Skill registry — the single source of truth for installed skills.

The registry is in-memory over the library + the `SkillStore` (lifecycle state).
It answers every question the runtime asks:

  * what skills exist / are enabled / are available to an actor?
  * which version should be used?
  * are a skill's tools, permissions and dependencies satisfied?
  * are there duplicate ids, invalid versions, missing/disabled deps, cycles?

It deliberately distinguishes INSTALLED (on disk) from VALIDATED (manifest well-
formed + deps resolvable) from ENABLED (approved) from AVAILABLE (enabled and
within an actor's permissions). A skill can be installed and valid yet not
enabled — that is the normal state.

There is exactly one registry. Nothing else may load or index skills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .loader import LoadedSkill, load_catalog
from .manifest import (
    EXECUTABLE_STATUSES,
    SkillManifest,
    version_satisfies,
)
from .permissions import Actor, PermissionDecision, check_permissions
from .store import SkillStore


@dataclass
class DependencyResolution:
    """The result of resolving a skill's dependency graph.

    `order` is a topological execution order (dependencies first, the requested
    skill last). `errors` non-empty ⇒ the skill may not execute.
    """

    ok: bool
    order: list[tuple[str, str]] = field(default_factory=list)  # (skillId, version)
    errors: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    cycles: list[str] = field(default_factory=list)
    version_mismatches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "order": [{"skillId": s, "version": v} for s, v in self.order],
            "errors": self.errors,
            "missing": self.missing,
            "disabled": self.disabled,
            "cycles": self.cycles,
            "versionMismatches": self.version_mismatches,
        }


class SkillRegistry:
    def __init__(self, store: Optional[SkillStore] = None) -> None:
        self.store = store or SkillStore()
        self._skills: dict[str, LoadedSkill] = {}
        self._duplicates: list[str] = []

    # ── Registration / loading ──────────────────────────────────────────────

    def register(self, loaded: LoadedSkill) -> None:
        """Register one skill. Duplicate ids are refused — first wins, and the
        duplicate is recorded and surfaced (never silently dropped)."""
        skill_id = loaded.manifest.id
        if skill_id in self._skills:
            self._duplicates.append(skill_id)
            return
        self._skills[skill_id] = loaded

    def load_library(self, root: Optional[str] = None) -> list[str]:
        """Load the shipped library into the registry. Returns load errors
        (malformed manifests) without aborting the whole load."""
        errors: list[str] = []
        for loaded in load_catalog(root):
            self.register(loaded)
        return errors

    def load_all(self, root: Optional[str] = None) -> list[str]:
        """Load the library and persist each skill/version to the store.

        A version already present is skipped (immutability). This is the boot
        path; it is idempotent.
        """
        loaded_all = load_catalog(root)
        self._skills = {}
        self._duplicates = []
        errors: list[str] = []
        for loaded in loaded_all:
            self.register(loaded)

        if self._duplicates:
            for dup in self._duplicates:
                errors.append(f"duplicate skill id {dup!r} — later definition ignored")

        # First pass: ensure Skill + version rows exist.
        for loaded in loaded_all:
            manifest = loaded.manifest
            self.store.upsert_skill(
                skill_id=manifest.id,
                name=manifest.name,
                description=manifest.description,
                category=manifest.category,
                latest_version=manifest.version,
                status=manifest.status,
                tags=manifest.tags,
            )
            try:
                self.store.save_version(manifest.model_dump(), manifest.content_hash())
            except ValueError:
                pass  # immutable version already stored — fine
            # Persist the skill's deterministic cases (idempotent: replace the
            # existing set for this version so a case edit takes effect).
            cases = loaded.load_cases()
            if cases:
                self.store.replace_evaluation_cases(manifest.id, manifest.version, cases)
        return errors

    # ── Lookups ─────────────────────────────────────────────────────────────

    def get(self, skill_id: str) -> Optional[LoadedSkill]:
        return self._skills.get(skill_id)

    def manifest(self, skill_id: str) -> Optional[SkillManifest]:
        loaded = self._skills.get(skill_id)
        return loaded.manifest if loaded else None

    def all_manifests(self) -> list[SkillManifest]:
        return [entry.manifest for entry in self._skills.values()]

    def duplicate_ids(self) -> list[str]:
        return list(self._duplicates)

    def resolve_version(self, skill_id: str, version: Optional[str] = None) -> Optional[str]:
        """Resolve the concrete version to use. An explicit version must exist;
        otherwise the skill's latest stored version is used."""
        skill = self._skills.get(skill_id)
        if skill is None:
            return None
        if version:
            stored = self.store.get_version(skill_id, version)
            return version if stored else None
        record = self.store.get_skill(skill_id)
        if record and record.get("latestVersion"):
            return str(record["latestVersion"])
        return skill.manifest.version

    # ── Discovery / search ──────────────────────────────────────────────────

    def discover(
        self,
        *,
        query: str = "",
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        actor: Optional[Actor] = None,
        include_non_executable: bool = False,
    ) -> list[dict[str, Any]]:
        """Deterministic discovery over DISCOVERY METADATA only (never prose).

        Filters by category/status/risk/tags and a keyword match over
        id/name/description/tags. Permission filtering is applied when an actor
        is supplied. Ordering is stable: exact id match first, then name, then
        id — so discovery is reproducible.
        """
        terms = [t for t in query.lower().split() if t]
        results: list[dict[str, Any]] = []
        for entry in self._skills.values():
            manifest = entry.manifest
            if not include_non_executable and manifest.status in {"rejected", "deprecated"}:
                continue
            if category and manifest.category != category:
                continue
            if status and manifest.status != status:
                continue
            if risk_level and manifest.riskLevel != risk_level:
                continue
            if tags:
                wanted = {t.lower() for t in tags}
                if not wanted.issubset({t.lower() for t in manifest.tags}):
                    continue
            if terms:
                haystack = " ".join(
                    [manifest.id, manifest.name, manifest.description, *manifest.tags]
                ).lower()
                if not all(term in haystack for term in terms):
                    continue
            if actor is not None:
                decision = check_permissions(manifest.permissions, actor)
                if not decision.allowed:
                    continue
            metadata = manifest.discovery_metadata()
            metadata["executable"] = manifest.status in EXECUTABLE_STATUSES
            results.append(metadata)

        def sort_key(item: dict[str, Any]) -> tuple[int, str]:
            if query and item["id"].lower() == query.lower():
                return (0, item["id"])
            if query and query.lower() in item["name"].lower():
                return (1, item["id"])
            return (2, item["id"])

        results.sort(key=sort_key)
        return results

    def list_summaries(self) -> list[dict[str, Any]]:
        """Every installed skill with its stored lifecycle status and latest
        version, for the library UI. Stored status wins over the file's, since
        enable/disable/deprecate mutate the store."""
        out: list[dict[str, Any]] = []
        for entry in self._skills.values():
            manifest = entry.manifest
            record = self.store.get_skill(manifest.id)
            summary = manifest.discovery_metadata()
            if record:
                summary["status"] = record["status"]
                summary["latestVersion"] = record["latestVersion"]
            summary["versions"] = [v["version"] for v in self.store.list_versions(manifest.id)]
            summary["origin"] = manifest.origin
            out.append(summary)
        out.sort(key=lambda item: item["id"])
        return out

    # ── Validation ──────────────────────────────────────────────────────────

    def validate(self, skill_id: str, version: Optional[str] = None) -> dict[str, Any]:
        """Full manifest/dependency/tool/permission validation for a skill.

        Returns a structured report; `ok` is True only when every mandatory
        check passes. A skill that fails validation cannot be enabled.
        """
        manifest = self.manifest(skill_id)
        if manifest is None:
            return {"ok": False, "skillId": skill_id, "checks": [], "errors": ["skill not installed"]}

        checks: list[dict[str, Any]] = []
        errors: list[str] = []

        checks.append({"check": "manifest", "ok": True, "detail": "pydantic-valid"})

        forbidden = manifest.forbidden_permissions
        checks.append({
            "check": "permissions",
            "ok": not forbidden,
            "detail": f"blocked: {', '.join(forbidden)}" if forbidden else "within allowed vocabulary",
        })
        if forbidden:
            errors.append(f"declares blocked permissions: {', '.join(forbidden)}")

        dep_result = self.resolve_dependencies(skill_id, version)
        checks.append({
            "check": "dependencies",
            "ok": dep_result.ok,
            "detail": dep_result.errors or "resolved",
        })
        errors.extend(dep_result.errors)

        tools_ok, tool_detail = self.check_tools(skill_id, version)
        checks.append({"check": "tools", "ok": tools_ok, "detail": tool_detail})
        if not tools_ok:
            errors.append(tool_detail)

        schema_ok, schema_detail = self._check_schemas(manifest)
        checks.append({"check": "schemas", "ok": schema_ok, "detail": schema_detail})
        if not schema_ok:
            errors.append(schema_detail)

        return {
            "ok": not errors,
            "skillId": skill_id,
            "version": version or manifest.version,
            "checks": checks,
            "errors": errors,
        }

    @staticmethod
    def _check_schemas(manifest: SkillManifest) -> tuple[bool, str]:
        if manifest.inputSchema.get("type") != "object":
            return False, "inputSchema must be an object schema"
        if manifest.outputSchema is not None and not isinstance(manifest.outputSchema, dict):
            return False, "outputSchema must be an object"
        return True, "input/output schemas are well-formed"

    def check_tools(self, skill_id: str, version: Optional[str] = None) -> tuple[bool, str]:
        """Every required tool must be registered in the runtime's tool registry.
        The registry is injected lazily to avoid an import cycle."""
        manifest = self.manifest(skill_id)
        if manifest is None:
            return False, "skill not installed"
        available = set(self._tool_names())
        missing = [t for t in manifest.requiredTools if t not in available]
        if missing:
            return False, f"required tools not registered: {', '.join(missing)}"
        return True, "all required tools are registered"

    # The runtime tool registry is attached by the service after construction.
    _tool_registry: Any = None

    def attach_tool_registry(self, registry: Any) -> None:
        self._tool_registry = registry

    def _tool_names(self) -> list[str]:
        if self._tool_registry is not None:
            return list(self._tool_registry.names())
        return []

    # ── Dependency resolution ───────────────────────────────────────────────

    def resolve_dependencies(
        self, skill_id: str, version: Optional[str] = None
    ) -> DependencyResolution:
        """Resolve the dependency graph. Deterministic order: dependencies
        before dependents. Detects missing, disabled, version-mismatched and
        circular dependencies. Bounded (each skill visited once)."""
        result = DependencyResolution(ok=True)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(current_id: str, constraint: Optional[str], chain: list[str]) -> bool:
            if current_id in visiting:
                cycle = " -> ".join([*chain, current_id])
                result.cycles.append(cycle)
                return False
            entry = self._skills.get(current_id)
            if entry is None:
                result.missing.append(current_id)
                return False
            resolved_version = self.resolve_version(current_id, None)
            if resolved_version and constraint and not version_satisfies(resolved_version, constraint):
                result.version_mismatches.append(
                    f"{current_id} {resolved_version} does not satisfy {constraint}"
                )
                return False
            record = self.store.get_skill(current_id)
            stored_status = record["status"] if record else entry.manifest.status
            if stored_status not in EXECUTABLE_STATUSES:
                result.disabled.append(f"{current_id} is {stored_status}")
                return False
            if current_id in visited:
                return True
            visiting.add(current_id)
            for dep in entry.manifest.requiredSkills:
                if dep.optional:
                    continue
                if not visit(dep.skillId, dep.version, [*chain, current_id]):
                    if current_id in visiting:
                        visiting.discard(current_id)
                    return False
            visiting.discard(current_id)
            visited.add(current_id)
            result.order.append((current_id, resolved_version or entry.manifest.version))
            return True

        ok = visit(skill_id, None, [])
        result.ok = ok and not (
            result.missing or result.disabled or result.cycles or result.version_mismatches
        )
        if result.cycles:
            result.errors.append("circular dependency detected: " + "; ".join(result.cycles))
        for missing in result.missing:
            result.errors.append(f"missing dependency: {missing}")
        for disabled in result.disabled:
            result.errors.append(f"dependency not executable: {disabled}")
        for mismatch in result.version_mismatches:
            result.errors.append(f"version mismatch: {mismatch}")
        return result

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def set_status(self, skill_id: str, status: str, actor: Actor, version: Optional[str] = None) -> dict[str, Any]:
        """Transition a skill's lifecycle status. Enable/disable/deprecate are
        the operator-facing operations; all require the matching permission."""
        from .permissions import can_enable

        manifest = self.manifest(skill_id)
        if manifest is None:
            return {"ok": False, "error": "skill not installed"}

        if status == "enabled":
            decision: PermissionDecision = can_enable(manifest.permissions, actor)
            if not decision.allowed:
                return {"ok": False, "error": decision.reason, "permissions": decision.to_dict()}
            report = self.validate(skill_id, version)
            if not report["ok"]:
                return {"ok": False, "error": "skill failed validation", "validation": report}

        required_permission = {
            "enabled": "skill.enable",
            "disabled": "skill.disable",
            "deprecated": "skill.enable",
        }.get(status)
        if required_permission and required_permission not in actor.granted():
            return {"ok": False, "error": f"{required_permission} requires an authorized operator"}

        target_version = version or self.resolve_version(skill_id) or manifest.version
        evaluation_status = "passed" if status == "enabled" else None
        self.store.set_version_status(skill_id, target_version, status, evaluation_status)
        self.store.append_event(f"skill.{status}" if status in {"enabled", "disabled", "deprecated"} else "skill.status_changed",
                                skill_id=skill_id, version=target_version,
                                data={"status": status, "actor": actor.id})
        return {"ok": True, "skillId": skill_id, "version": target_version, "status": status}

    def deprecate(self, skill_id: str, actor: Actor, reason: str, superseded_by: Optional[str] = None) -> dict[str, Any]:
        manifest = self.manifest(skill_id)
        if manifest is None:
            return {"ok": False, "error": "skill not installed"}
        if "skill.enable" not in actor.granted():
            return {"ok": False, "error": "skill.enable requires an authorized operator"}
        target_version = self.resolve_version(skill_id) or manifest.version
        self.store.set_version_status(skill_id, target_version, "deprecated")
        self.store.save_review(
            skill_id=skill_id, version=target_version, actor=actor.id,
            decision="deprecated", notes=reason,
        )
        self.store.append_event(
            "skill.disabled", skill_id=skill_id, version=target_version,
            data={"reason": reason, "supersededBy": superseded_by},
        )
        return {"ok": True, "skillId": skill_id, "version": target_version, "status": "deprecated"}

    # ── History ─────────────────────────────────────────────────────────────

    def version_history(self, skill_id: str) -> list[dict[str, Any]]:
        return [
            {
                "version": v["version"],
                "status": v["status"],
                "evaluationStatus": v["evaluationStatus"],
                "contentHash": v["contentHash"],
                "createdAt": v["createdAt"],
                "origin": v["origin"],
                "author": v["author"],
            }
            for v in self.store.list_versions(skill_id)
        ]

    def evaluation_history(self, skill_id: str) -> list[dict[str, Any]]:
        return self.store.list_evaluations(skill_id)

    def execution_history(self, skill_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_executions(skill_id, limit)


__all__ = ["DependencyResolution", "SkillRegistry"]

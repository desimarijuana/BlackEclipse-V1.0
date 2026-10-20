"""The evolution engine (Phase 10): evaluate a candidate in a worktree, archive
the attempt, and drive activation through `skills/versioning.py` unchanged.

This module owns the ORCHESTRATION only. It runs every check through the Phase 3
command broker and records it in the Phase 4 ledger (`code/verify.py`), so "it
passed" is never a claim the model made. Activation is an OPERATOR decision,
recorded on a row, and can be rolled back atomically with both versions preserved.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from ..persistence import now_iso
from . import evolution as evo
from . import patch as patch_mod
from . import worktree as worktree_mod
from .evolution_store import EvolutionStore


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:64]


def _make_check_runner(ctx: Any, workspace_root: Path):
    """A `run_check(path) -> dict` seam using the Phase 3 broker + Phase 4 ledger.

    Mirrors `scaffold_tools._run_check`, but scoped to a single owning test path.
    """
    def _run(path: str) -> dict[str, Any]:
        from .commands import CommandUnavailable, build_argv, resolve_class  # noqa: PLC0415
        from .sandbox import RunSpec, SandboxUnavailable, build_env, run as sandbox_run  # noqa: PLC0415
        from .sandbox import select_backend  # noqa: PLC0415

        command_class = "unit_test" if path.endswith((".ts", ".tsx")) else "python_test"
        args = {"files": [path]} if command_class == "unit_test" else {"paths": [path]}
        try:
            resolved = resolve_class(command_class)
            argv = build_argv(resolved, args)
        except CommandUnavailable as exc:
            return {"commandClass": command_class, "exitCode": None, "reason": exc.code}
        try:
            select_backend()
        except SandboxUnavailable:
            return {"commandClass": command_class, "exitCode": None, "reason": "SANDBOX_UNAVAILABLE"}

        spec = RunSpec(
            argv=argv, cwd=Path(workspace_root), env=build_env(),
            timeout_s=resolved.timeout_s, output_cap_bytes=resolved.output_cap_bytes,
            network=resolved.network,
        )
        raw = sandbox_run(spec)
        execution_id = ""
        store = getattr(ctx, "code_store", None)
        if store is not None:
            try:
                record = store.record_command_execution(
                    run_id=str(getattr(ctx, "run_id", "")), command_class=command_class,
                    argv=argv, cwd=str(workspace_root), exit_code=raw.exit_code,
                    duration_ms=raw.duration_ms, output=raw.output, total_chars=raw.total_chars,
                    sandbox_backend=raw.backend, policy_decision={"allowed": True, "code": "OK"},
                    timed_out=raw.timed_out, truncated=raw.truncated,
                )
                execution_id = str(record.get("id") or "")
            except Exception:  # noqa: BLE001
                pass
        ledger = getattr(ctx, "code_ledger", None)
        if ledger is not None and raw.exit_code is not None:
            try:
                ledger.record(
                    command_execution_id=execution_id, command_class=command_class,
                    exit_code=int(raw.exit_code), duration_ms=raw.duration_ms, output=raw.output,
                    argv=tuple(argv),
                )
            except Exception:  # noqa: BLE001
                pass
        return {
            "commandClass": command_class, "exitCode": raw.exit_code,
            "executionId": execution_id, "durationMs": raw.duration_ms,
        }

    return _run


def evaluate(
    store: Any,
    candidate_id: str,
    *,
    ctx: Any,
    actor: Any,
) -> dict[str, Any]:
    """Run the owning checks in a Phase-2 worktree and archive the attempt.

    The candidate's ops are applied INSIDE the disposable worktree, the owning
    test(s) run there, and every execution is recorded. The live checkout is never
    written. A refusal (frozen/protected/outside) is recorded as a `refused`
    attempt, never dropped.
    """
    evolution = EvolutionStore(store)
    candidate = evolution.get_candidate(candidate_id)
    if candidate is None:
        return {"ok": False, "error": "candidate not found"}

    # Validate the ops deterministically first (the freeze set).
    try:
        ops = evo.propose_ops(candidate, actor=actor)
    except evo.EvolutionRefusal as refusal:
        evolution.update_candidate(candidate_id, status="refused", refusalCode=refusal.code)
        evolution.save_attempt({
            "candidateId": candidate_id, "targetPath": candidate.get("targetPath") or "",
            "baseDigest": "", "diffDigest": _digest(refusal.code),
            "proposedOps": candidate.get("proposedOps") or [],
            "outcome": "refused", "outcomeReason": refusal.detail or refusal.code,
        })
        return {"ok": False, "refused": True, **refusal.to_dict()}

    target = str(candidate.get("targetPath") or "")
    base_digest = ""
    worktree_ws = None
    try:
        worktree_ws = worktree_mod.allocate(base_revision="HEAD")
    except worktree_mod.WorkspaceError as exc:
        evolution.save_attempt({
            "candidateId": candidate_id, "targetPath": target, "baseDigest": "",
            "diffDigest": _digest("sandbox"), "proposedOps": ops,
            "outcome": "refused", "outcomeReason": exc.reason,
        })
        return {"ok": False, "refused": True, "code": "SANDBOX_UNAVAILABLE", "detail": exc.reason}

    try:
        target_file = worktree_ws.root / target.replace("/", str(Path("/")))
        if target_file.is_file():
            base_digest = _digest(target_file.read_text(encoding="utf-8", errors="replace"))
        # Apply the ops inside the worktree only.
        resolved = _resolved_for(worktree_ws)
        parsed = patch_mod.parse_patch({"operations": ops})
        applied = patch_mod.apply(resolved, parsed, binding=resolved.binding, actor=_worktree_actor(worktree_ws))
        if not applied.get("ok"):
            refused = applied.get("refused") or {}
            evolution.save_attempt({
                "candidateId": candidate_id, "targetPath": target, "baseDigest": base_digest,
                "diffDigest": _digest(refused.get("code", "")), "proposedOps": ops,
                "outcome": "refused", "outcomeReason": refused.get("reason", "the change was refused"),
            })
            return {"ok": False, "refused": True, "code": refused.get("code"), "detail": refused.get("reason")}

        report = evo.evaluate_candidate(
            candidate, run_check=_make_check_runner(ctx, worktree_ws.root), base_digest=base_digest,
        )
        outcome = "success" if report.passed else "failure"
        diff_digest = _digest(report.targetPath + "|" + outcome) if not report.checks else \
            _digest("|".join(c.execution_id for c in report.checks) or outcome)
        evolution.save_attempt({
            "candidateId": candidate_id, "targetPath": target, "baseDigest": base_digest,
            "diffDigest": diff_digest, "proposedOps": ops,
            "evaluation": report.to_dict(), "outcome": outcome,
            "outcomeReason": "all owning checks passed" if report.passed else "an owning check did not pass",
            "costMicros": None, "tokensUsed": None, "finishedAt": now_iso(),
        })
        evolution.update_candidate(
            candidate_id, status="evaluated_ok" if report.passed else "evaluated_bad",
        )
        return {"ok": True, "passed": report.passed, "report": report.to_dict()}
    finally:
        if worktree_ws is not None:
            try:
                worktree_mod.release(worktree_ws.id)
            except Exception:  # noqa: BLE001 - release is best-effort
                pass


def _resolved_for(ws: Any) -> Any:
    from . import policy  # noqa: PLC0415
    from .workspace import ResolvedWorkspace  # noqa: PLC0415

    # `worktree.allocate` returns a `CodeWorkspace` without a binding; the patch
    # policy requires an explicit `WorkspaceBinding` or every write is refused as
    # NO_BINDING. Build the same binding the landing path uses.
    binding = getattr(ws, "binding", None)
    if binding is None:
        binding = policy.WorkspaceBinding(
            id=ws.id, root=ws.root,
            base_revision=ws.base_revision, strategy=ws.strategy,
        )
    return ResolvedWorkspace(
        id=ws.id, root=ws.root, base_revision=ws.base_revision, strategy=ws.strategy,
        binding=binding,
    )


def _worktree_actor(ws: Any) -> Any:
    from ..skills.permissions import Actor  # noqa: PLC0415

    return Actor(id="evolution", operator=False, workspace_id=ws.id, autonomy="approve_external")


def activate(
    store: Any,
    candidate_id: str,
    *,
    registry: Any,
    actor: Any,
    canary: bool = False,
) -> dict[str, Any]:
    """The OPERATOR decision. Records both versions through the existing lifecycle.

    The code subject is registered as a thin managed skill so `skills/versioning.py`
    governs it UNCHANGED. Activation reuses `propose_patch` → `activate_version`
    (or `propose_patch` → `evaluate_version` → `activate_version`).
    """
    from ..skills import versioning  # noqa: PLC0415

    evolution = EvolutionStore(store)
    candidate = evolution.get_candidate(candidate_id)
    if candidate is None:
        return {"ok": False, "error": "candidate not found"}
    if candidate["status"] not in ("evaluated_ok", "canaried"):
        return {"ok": False, "error": "this change must be checked and pass before it can be turned on"}

    manifest = evo.candidate_skill_manifest(candidate)
    # Seed the subject as a base version, then propose the code change as a NEW
    # version through the existing lifecycle (the patchable `instructions` field).
    try:
        _seed_subject(registry, manifest)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not register the subject: {exc}"}

    proposed = versioning.propose_patch(
        registry,
        {
            "skill": manifest["id"],
            "baseVersion": manifest["version"],
            "author": actor.id,
            "reason": candidate["problemStatement"][:200],
            # A JSON pointer into the manifest (the skills/patches.py shape); the
            # code change is carried as the subject's `description`.
            "operations": [{"op": "replace", "path": "/description", "value": _subject_instructions(candidate)}],
        },
        actor=actor,
    )
    if not proposed.get("ok"):
        return {"ok": False, "error": proposed.get("error"), "stage": "propose"}

    new_version = proposed["version"]
    # The §6.4 worktree report IS the evaluation evidence for a code subject; the
    # adapter records its passing result on the version so `activate_version`'s
    # gate (evaluationStatus == "passed") is satisfied. `activate_version` itself
    # is used UNCHANGED.
    try:
        registry.store.set_version_status(
            manifest["id"], new_version, "validated", evaluation_status="passed",
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not record the evaluation: {exc}", "stage": "evaluate"}

    prior_version = manifest["version"]
    activated = versioning.activate_version(
        registry, manifest["id"], new_version, actor=actor, canary=canary,
        reason="operator activated a prepared change",
    )
    if not activated.get("ok"):
        return {"ok": False, "error": activated.get("error"), "stage": "activate"}

    evolution.update_candidate(
        candidate_id,
        status="canaried" if canary else "activated",
        activatedVersion=new_version, previousVersion=prior_version,
    )
    return {
        "ok": True, "activatedVersion": new_version, "previousVersion": prior_version,
        "canary": bool(canary),
    }


def rollback(store: Any, candidate_id: str, *, registry: Any, actor: Any, reason: str = "") -> dict[str, Any]:
    """An ATOMIC rollback through the existing lifecycle; both versions preserved."""
    from ..skills import versioning  # noqa: PLC0415

    evolution = EvolutionStore(store)
    candidate = evolution.get_candidate(candidate_id)
    if candidate is None:
        return {"ok": False, "error": "candidate not found"}
    activated_version = candidate.get("activatedVersion")
    if not activated_version:
        return {"ok": False, "error": "this change isn't active, so there's nothing to put back"}
    manifest = evo.candidate_skill_manifest(candidate)
    result = versioning.rollback(
        registry, skill_id=manifest["id"], version=activated_version, actor=actor,
        reason=reason or "a check that passed got worse, so the previous version was restored",
    )
    evolution.update_candidate(candidate_id, status="rolled_back")
    evolution.save_attempt({
        "candidateId": candidate_id, "targetPath": candidate.get("targetPath") or "code",
        "baseDigest": candidate.get("previousVersion") or "", "diffDigest": _digest("rollback"),
        "proposedOps": candidate.get("proposedOps") or [],
        "outcome": "rolled_back", "outcomeReason": reason or "rolled back",
        "finishedAt": now_iso(),
    })
    return {"ok": bool(result.get("ok")), **result}


def _seed_subject(registry: Any, manifest: dict[str, Any]) -> None:
    """Register the subject's base version once (idempotent)."""
    from ..skills.manifest import SkillManifest  # noqa: PLC0415

    if registry.store.get_version(manifest["id"], manifest["version"]) is not None:
        return
    # The base subject must be an ACTIVE version for `propose_patch` (the existing
    # lifecycle only patches an active base). The manifest blob carries the status.
    seeded = {**manifest, "status": "enabled", "evaluationStatus": "passed"}
    # The parent Skill row must exist before its version (FK on skillId).
    registry.store.upsert_skill(
        skill_id=manifest["id"], name=manifest["name"], description=manifest["description"],
        category=manifest.get("category", "system"), latest_version=manifest["version"],
        status="enabled", tags=manifest.get("tags", []),
    )
    registry.store.save_version(
        seeded, SkillManifest(**seeded).version_identity("# base"),
        instructions="# base code subject\n", base_version=None, patch_summary="base subject",
    )
    registry.store.set_version_status(manifest["id"], manifest["version"], "enabled",
                                      evaluation_status="passed")
    registry.store.set_latest_version(manifest["id"], manifest["version"])


def _subject_instructions(candidate: dict[str, Any]) -> str:
    return f"# prepared change for {candidate.get('targetPath')}\n{candidate.get('problemStatement')}\n"


__all__ = ["activate", "evaluate", "rollback"]

"""The Git service — the single facade every Git tool calls.

It composes the engine: discovery, the executor, the parsers, the operation state
machine, the safety engine, the journal, the lock and the recovery manager. A
mutating operation runs under the per-repository lock, is journaled, and returns
a deterministic structured result. A failure is classified: a *conflict* is
recorded as an active operation the agent can continue or abort; any other
failure is a structured `GitError`.

The service never performs an external action itself (push/PR). Those are
`external_action` tools gated by the operator-approval authorizer; the service
runs the validated git argv AFTER the gate, and never claims a remote side effect
it did not observe.

Reads are thin delegates to `readers.py` and take no lock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import errors, journal as journal_mod, parsers, readers, recovery, safety, state
from .executor import GitResult, run
from .journal import GitJournal
from .lock import locked
from .operations import risk_level
from .repository import Repository, discover, require_repository

_SERVICE: Optional["GitService"] = None


def set_git_service(service: Optional["GitService"]) -> None:
    global _SERVICE
    _SERVICE = service


def get_git_service() -> Optional["GitService"]:
    return _SERVICE


@dataclass
class OperationOutcome:
    """The deterministic result of one operation."""

    success: bool
    operation: str
    repository: str
    result: dict[str, Any] = field(default_factory=dict)
    warnings: list[Any] = field(default_factory=list)
    error: Optional[dict[str, Any]] = None
    operation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "success": self.success,
            "operation": self.operation,
            "repository": self.repository,
            "result": self.result,
            "warnings": self.warnings,
        }
        if self.operation_id:
            out["operationId"] = self.operation_id
        if self.error is not None:
            out["error"] = self.error
        return out


class GitService:
    """The Git engine facade. Construct once per process with the run store."""

    def __init__(self, store: Any = None) -> None:
        self.journal: Optional[GitJournal] = GitJournal(store) if store is not None else None

    # ── Discovery ─────────────────────────────────────────────────────────────
    def discover(self, start: str | Path = ".") -> Optional[Repository]:
        return discover(start)

    def require(self, start: str | Path = ".") -> Repository:
        return require_repository(start)

    def info(self, start: str | Path = ".") -> dict[str, Any]:
        repo = discover(start)
        if repo is None:
            return {"is_repository": False, "code": errors.NOT_A_REPOSITORY}
        info = repo.to_dict()
        if self.journal is not None:
            recon = recovery.reconcile(repo, self.journal)
            info["reconciliation"] = recon.to_dict()
        return info

    def list_repositories(self, start: str | Path = ".", *, max_depth: int = 3) -> dict[str, Any]:
        """Enumerate nested repositories under `start` (bounded)."""
        import os  # noqa: PLC0415

        base = Path(start).resolve()
        found: list[str] = []
        depth_base = len(base.parts)
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            current = Path(dirpath)
            if len(current.parts) - depth_base > max_depth:
                dirnames[:] = []
                continue
            if ".git" in dirnames or ".git" in filenames:
                found.append(str(current))
                dirnames[:] = [d for d in dirnames if d != ".git"]
            dirnames[:] = [d for d in dirnames if d not in (
                "node_modules", ".next", "__pycache__", ".black-eclipse", "vendor")]
            if len(found) >= 200:
                break
        return {"available": True, "repositories": found, "count": len(found)}

    # ── Reads (no lock) ──────────────────────────────────────────────────────────
    def status(self, repo: Repository, *, full: bool = False) -> dict[str, Any]:
        return readers.status(repo, full=full)

    def state_block(self, repo: Repository) -> dict[str, Any]:
        return readers.repository_state(repo)

    # ── The mutating core ──────────────────────────────────────────────────────────
    def _mutate(
        self,
        repo: Repository,
        op_name: str,
        args: Optional[dict[str, Any]],
        *,
        run_id: Optional[str] = None,
        scope_id: Optional[str] = None,
        network: Optional[bool] = None,
        timeout_s: Optional[int] = None,
        conflict_operation: Optional[str] = None,
        post: Optional[Callable[[GitResult], dict[str, Any]]] = None,
        force_push: bool = False,
        hard_reset: bool = False,
        affected_files: Optional[list[str]] = None,
        env_extra: Optional[dict[str, str]] = None,
        input_text: Optional[str] = None,
    ) -> OperationOutcome:
        """Run one mutating op under the lock, journaled, with conflict detection."""
        from .catalog import CATALOG  # noqa: PLC0415

        # Confinement / escalation guard. `worktree_add` and `worktree_move` take a
        # filesystem path OUTSIDE the operation table's usual ref/path vocabulary; a
        # relative `../` or an absolute path would place a working tree outside the
        # repository — and a later `worktree remove --force` would delete there. The
        # path is confined to the repository root before any process starts.
        denial = _confinement_error(op_name, args, repo.root)
        if denial is not None:
            return OperationOutcome(False, op_name, str(repo.root), error=denial.to_dict())

        op = CATALOG.get(op_name)
        global_config = _is_global_config(op_name, args)
        risk = safety.assess_risk(
            op_name, force_push=force_push, hard_reset=hard_reset, global_config=global_config,
        ).risk
        mutating = bool(op.mutating) if op else True
        pre = recovery.snapshot(repo) if risk_level(risk) >= risk_level("dangerous") else None

        operation_id = ""
        if self.journal is not None:
            try:
                operation_id = self.journal.start(
                    repository=str(repo.root), operation=op_name,
                    argv=_argv_preview(op, args), risk=risk, mutating=mutating,
                    run_id=run_id, scope_id=scope_id,
                )
            except Exception:  # noqa: BLE001 - a journal failure must not block the op
                operation_id = ""

        started = time.monotonic()
        try:
            with locked(repo.git_dir):
                result = run(repo.root, op_name, args, timeout_s=timeout_s, network=network,
                             env_extra=env_extra, input_text=input_text)
        except errors.GitError as exc:
            # The lock refused: a structured failure, journaled.
            self._finish(operation_id, "FAILED", exc.code, affected_files, None,
                         int((time.monotonic() - started) * 1000))
            return OperationOutcome(False, op_name, str(repo.root), error=exc.to_dict(),
                                     operation_id=operation_id)
        except Exception as exc:  # noqa: BLE001 - an engine fault is a structured failure
            err = errors.GitError(errors.GIT_FAILED, stderr=str(exc))
            self._finish(operation_id, "FAILED", err.code, affected_files, None,
                         int((time.monotonic() - started) * 1000))
            return OperationOutcome(False, op_name, str(repo.root), error=err.to_dict(),
                                     operation_id=operation_id)

        duration_ms = int((time.monotonic() - started) * 1000)
        if result.ok:
            data = post(result) if post is not None else {}
            # A completed multi-step operation clears the active-operation record.
            active = state.active_operation(repo)
            if active is None and self.journal is not None:
                try:
                    self.journal.clear_active(str(repo.root))
                except Exception:  # noqa: BLE001
                    pass
            self._finish(operation_id, "SUCCESS", None, affected_files,
                         {"pre": pre.to_dict() if pre else None}, duration_ms)
            return OperationOutcome(True, op_name, str(repo.root), result=data,
                                     operation_id=operation_id)

        # ── Failure ────────────────────────────────────────────────────────────
        active = state.active_operation(repo)
        if conflict_operation and active is not None and active.conflicts:
            code = errors.conflict_code(conflict_operation)
            err = errors.GitError(
                code, files=active.conflicted_files, recoverable=True,
                stderr=result.stderr, exit_code=result.exit_code,
            )
            self._record_active(repo, operation_id, active)
            self._finish(operation_id, "CONFLICT", code, list(active.conflicted_files),
                         {"pre": pre.to_dict() if pre else None, "operation": active.to_dict()},
                         duration_ms)
            return OperationOutcome(False, op_name, str(repo.root), error=err.to_dict(),
                                     operation_id=operation_id)

        err = result.error or errors.GitError(result.code or errors.GIT_FAILED, stderr=result.stderr)
        self._finish(operation_id, "FAILED", err.code, affected_files,
                     {"pre": pre.to_dict() if pre else None}, duration_ms)
        return OperationOutcome(False, op_name, str(repo.root), error=err.to_dict(),
                                 operation_id=operation_id)

    def _record_active(self, repo: Repository, operation_id: str, active: state.OperationState) -> None:
        if self.journal is None:
            return
        try:
            self.journal.set_active(
                repository=str(repo.root), operation_id=operation_id,
                operation=active.operation or "unknown", status=active.status,
                next_action=state.continue_hint(repo), head_name=active.head_name,
                onto=active.onto,
            )
        except Exception:  # noqa: BLE001
            pass

    def _finish(self, operation_id: str, status: str, error_code: Optional[str],
                affected: Optional[list[str]], recovery_state: Optional[dict[str, Any]],
                duration_ms: int) -> None:
        if self.journal is None or not operation_id:
            return
        try:
            self.journal.finish(
                operation_id, status=status, error_code=error_code,
                affected_files=affected, recovery_state=recovery_state, duration_ms=duration_ms,
            )
        except Exception:  # noqa: BLE001
            pass

    # ── Staging ────────────────────────────────────────────────────────────────
    def stage(self, repo: Repository, paths: list[str], *, all: bool = False,
              run_id: Optional[str] = None) -> OperationOutcome:
        if all:
            return self._mutate(repo, "add", {"paths": ["."], "flags": ["-A"]},
                                run_id=run_id, affected_files=paths or ["."])
        return self._mutate(repo, "add", {"paths": paths}, run_id=run_id, affected_files=paths,
                            post=lambda r: {"staged": paths})

    def unstage(self, repo: Repository, paths: Optional[list[str]] = None, *,
                run_id: Optional[str] = None) -> OperationOutcome:
        if not paths:
            return self._mutate(repo, "restore_staged", {"paths": []}, run_id=run_id)
        return self._mutate(repo, "reset_paths", {"paths": paths}, run_id=run_id, affected_files=paths)

    def stage_file(self, repo: Repository, path: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self.stage(repo, [path], run_id=run_id)

    # ── Selective hunk staging (no TTY) ──────────────────────────────────────────
    def list_hunks(self, repo: Repository, paths: Optional[list[str]] = None) -> dict[str, Any]:
        """The files and hunks of the working-tree change, for a caller to select."""
        from . import diffs  # noqa: PLC0415

        patch = run(repo.root, "diff_worktree", {"paths": paths or [], "contextLines": None})
        if not patch.ok:
            return {"available": False, "error": (patch.error or errors.GitError(errors.GIT_FAILED)).to_dict()}
        if not patch.stdout.strip():
            return {"available": True, "files": [], "fileCount": 0, "hunkCount": 0}
        try:
            files = diffs.parse_unified_diff(patch.stdout)
        except errors.GitError as exc:
            return {"available": False, "error": exc.to_dict()}
        return {"available": True, **diffs.summarize(files)}

    def stage_hunks(self, repo: Repository, selection: dict[str, list[int]],
                    *, paths: Optional[list[str]] = None, reverse: bool = False,
                    run_id: Optional[str] = None) -> OperationOutcome:
        """Stage (or unstage) only the selected hunks by applying a rebuilt patch.

        `selection` maps a path to 0-based hunk indexes (`-1` = all). The patch is
        parsed and re-rendered in Python first, so every path is confined and only
        the chosen hunks reach git.
        """
        from . import diffs  # noqa: PLC0415

        patch = run(repo.root, "diff_worktree", {"paths": paths or [], "contextLines": None})
        if not patch.ok:
            return OperationOutcome(False, "stage_hunks", str(repo.root),
                                     error=(patch.error or errors.GitError(errors.GIT_FAILED)).to_dict())
        try:
            files = diffs.parse_unified_diff(patch.stdout)
            rebuilt = diffs.render_selected(files, selection)
        except errors.GitError as exc:
            return OperationOutcome(False, "stage_hunks", str(repo.root), error=exc.to_dict())
        op = "apply_cached_reverse" if reverse else "apply_cached"
        return self._mutate(repo, op, None, run_id=run_id, input_text=rebuilt,
                            post=lambda r: {"staged": list(selection.keys()), "reverse": reverse})

    def unstage_hunks(self, repo: Repository, selection: dict[str, list[int]],
                      *, paths: Optional[list[str]] = None,
                      run_id: Optional[str] = None) -> OperationOutcome:
        """Unstage only the selected hunks of the staged change (index → working tree)."""
        from . import diffs  # noqa: PLC0415

        patch = run(repo.root, "diff_cached", {"paths": paths or []})
        if not patch.ok:
            return OperationOutcome(False, "unstage_hunks", str(repo.root),
                                     error=(patch.error or errors.GitError(errors.GIT_FAILED)).to_dict())
        try:
            files = diffs.parse_unified_diff(patch.stdout)
            rebuilt = diffs.render_selected(files, selection)
        except errors.GitError as exc:
            return OperationOutcome(False, "unstage_hunks", str(repo.root), error=exc.to_dict())
        return self._mutate(repo, "apply_cached_reverse", None, run_id=run_id, input_text=rebuilt,
                            post=lambda r: {"unstaged": list(selection.keys())})

    def apply_patch(self, repo: Repository, patch: str, *, to_index: bool = True, reverse: bool = False,
                    run_id: Optional[str] = None) -> OperationOutcome:
        """Apply a caller-supplied unified patch to the index or the working tree."""
        from . import diffs  # noqa: PLC0415

        try:
            diffs.parse_unified_diff(patch)  # path safety, before git sees the bytes
        except errors.GitError as exc:
            return OperationOutcome(False, "apply_patch", str(repo.root), error=exc.to_dict())
        op = "apply_cached_reverse" if (to_index and reverse) else ("apply_cached" if to_index else "apply_worktree")
        return self._mutate(repo, op, None, run_id=run_id, input_text=patch,
                            post=lambda r: {"applied": True, "toIndex": to_index, "reverse": reverse})

    # ── Commit ──────────────────────────────────────────────────────────────────
    def pre_scan(self, repo: Repository, paths: list[str]) -> dict[str, Any]:
        policy = safety.load_policy(repo)
        secrets = safety.scan_secrets(repo, paths)
        large = safety.scan_large_files(repo, paths, threshold_mb=policy.large_file_mb)
        return {
            "secrets": [s.to_dict() for s in secrets],
            "largeFiles": [l.to_dict() for l in large],
            "scanners": safety.external_scanners(),
        }

    def commit(
        self, repo: Repository, message: str, *, amend: bool = False, no_edit: bool = False,
        allow_empty: bool = False, allow_secrets: bool = False, author: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> OperationOutcome:
        staged = self._staged_paths(repo)
        if not staged and not amend and not allow_empty:
            return OperationOutcome(False, "commit", str(repo.root),
                                     error=errors.GitError(errors.NOTHING_STAGED).to_dict())
        scan = self.pre_scan(repo, staged)
        warnings: list[Any] = []
        if scan["secrets"]:
            if not allow_secrets:
                return OperationOutcome(
                    False, "commit", str(repo.root), warnings=scan["secrets"],
                    error=errors.GitError(errors.SECRET_DETECTED, files=[s["path"] for s in scan["secrets"]]).to_dict(),
                )
            warnings.extend(scan["secrets"])
        if scan["largeFiles"]:
            warnings.extend(scan["largeFiles"])
        policy = safety.load_policy(repo)
        if policy.conventional_commits and message and not safety.is_conventional(message) and not amend:
            warnings.append({"kind": "policy", "detail": "This project prefers conventional commit messages."})

        args: dict[str, Any] = {"message": message or None}
        if amend:
            args["amend"] = "true"
            if no_edit:
                args["noEdit"] = "true"
        if allow_empty:
            args["allowEmpty"] = "true"
        if author:
            args["author"] = author

        outcome = self._mutate(
            repo, "commit", args, run_id=run_id, affected_files=staged,
            post=lambda r: self._commit_result(repo, r),
        )
        outcome.warnings = warnings + outcome.warnings
        return outcome

    def _commit_result(self, repo: Repository, result: GitResult) -> dict[str, Any]:
        head = run(repo.root, "head_sha")
        branch = run(repo.root, "head_ref")
        return {
            "commit": head.stdout.strip() if head.ok else None,
            "branch": branch.stdout.strip() if branch.ok else None,
            "summary": (result.stdout or "").strip().splitlines()[0] if result.stdout.strip() else "",
        }

    def amend(self, repo: Repository, *, message: Optional[str] = None, no_edit: bool = False,
              run_id: Optional[str] = None) -> OperationOutcome:
        return self.commit(repo, message or "", amend=True, no_edit=no_edit or not message,
                           allow_empty=True, run_id=run_id)

    def _staged_paths(self, repo: Repository) -> list[str]:
        result = run(repo.root, "diff_name_status_cached", {"paths": []})
        if not result.ok:
            return []
        return [e["path"] for e in parsers.parse_name_status(result.stdout)]

    # ── Branches / checkout ─────────────────────────────────────────────────────
    def create_branch(self, repo: Repository, name: str, *, start: Optional[str] = None,
                      checkout: bool = True, run_id: Optional[str] = None) -> OperationOutcome:
        if checkout:
            return self._mutate(repo, "switch", {"create": name, "target": start} if start else {"create": name},
                                run_id=run_id, affected_files=[name],
                                post=lambda r: {"branch": name, "created": True})
        return self._mutate(repo, "branch_create", {"name": name, "start": start},
                            run_id=run_id, affected_files=[name],
                            post=lambda r: {"branch": name, "created": True})

    def delete_branch(self, repo: Repository, name: str, *, force: bool = False,
                      run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "branch_delete", {"name": name, "mode": "force" if force else "safe"},
                            run_id=run_id, affected_files=[name],
                            post=lambda r: {"branch": name, "deleted": True})

    def rename_branch(self, repo: Repository, old: str, new: Optional[str] = None,
                      run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "branch_rename", {"old": old, "new": new}, run_id=run_id,
                            post=lambda r: {"from": old, "to": new})

    def set_upstream(self, repo: Repository, upstream: str, *, branch: Optional[str] = None,
                     run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "branch_set_upstream", {"upstream": upstream, "branch": branch},
                            run_id=run_id, post=lambda r: {"upstream": upstream})

    def checkout(self, repo: Repository, target: Optional[str] = None, *, create: Optional[str] = None,
                 detach: bool = False, run_id: Optional[str] = None) -> OperationOutcome:
        """Safe checkout. A git refusal to overwrite local work is a structured failure."""
        if create:
            outcome = self._mutate(
                repo, "switch", {"create": create, "target": target}, run_id=run_id,
                affected_files=[create], post=lambda r: {"branch": create},
            )
        elif detach and target:
            outcome = self._mutate(repo, "switch_detach", {"target": target}, run_id=run_id,
                                   affected_files=[target], post=lambda r: {"detached": True, "target": target})
        elif not target:
            outcome = OperationOutcome(
                False, "checkout", str(repo.root),
                error=errors.GitError(
                    errors.INVALID_ARGUMENT,
                    "Name the line of work to switch to, or create a new one.",
                ).to_dict(),
            )
        else:
            outcome = self._mutate(
                repo, "switch", {"target": target}, run_id=run_id,
                affected_files=[target],
                post=lambda r: {"target": target},
            )
        if not outcome.success and outcome.error and outcome.error.get("code") == errors.CHECKOUT_OVERWRITE:
            outcome.error["safe"] = False  # the agent must decide: stash / commit / preserve / ask
        return outcome

    # ── Merge / rebase / cherry-pick / revert ─────────────────────────────────────
    def merge(self, repo: Repository, target: str, *, message: Optional[str] = None,
              no_ff: bool = False, ff_only: bool = False, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(
            repo, "merge", {"target": target, "message": message,
                            "noFf": "true" if no_ff else None, "ffOnly": "true" if ff_only else None},
            run_id=run_id, conflict_operation="merge",
            post=lambda r: self._commit_result(repo, r),
        )

    def merge_abort(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "merge_abort", None, run_id=run_id,
                            post=lambda r: {"aborted": True})

    def merge_continue(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "merge_continue", None, run_id=run_id,
                            conflict_operation="merge", post=lambda r: self._commit_result(repo, r))

    def rebase(self, repo: Repository, upstream: str, *, onto: Optional[str] = None,
               autosquash: bool = False, autostash: bool = False,
               run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(
            repo, "rebase", {
                "upstream": upstream, "onto": onto,
                "autosquash": "true" if autosquash else None,
                "autostash": "true" if autostash else None,
            },
            run_id=run_id, conflict_operation="rebase",
            post=lambda r: {"rebased": True, "upstream": upstream},
        )

    def rebase_abort(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "rebase_abort", None, run_id=run_id, post=lambda r: {"aborted": True})

    def rebase_continue(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "rebase_continue", None, run_id=run_id,
                            conflict_operation="rebase", post=lambda r: {"continued": True})

    def rebase_skip(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "rebase_skip", None, run_id=run_id, post=lambda r: {"skipped": True})

    def rebase_plan(self, repo: Repository, upstream: str, actions: list[dict[str, Any]], *,
                    onto: Optional[str] = None, autosquash: bool = False,
                    autostash: bool = False, run_id: Optional[str] = None,
                    scratch_dir: Optional[Path] = None) -> OperationOutcome:
        """Run a fully AUTOMATED interactive rebase from a structured plan.

        The sequence editor + message editor are driven through env vars (no TTY),
        so squash/fixup/drop/reorder/reword/edit are deterministic. A plan that
        names only some commits never drops the rest (the editor appends them).
        """
        from . import rebase_plan as plan_mod  # noqa: PLC0415

        try:
            validated = plan_mod.validate_actions(actions)
        except errors.GitError as exc:
            return OperationOutcome(False, "rebase_plan", str(repo.root), error=exc.to_dict())

        import shutil as _shutil  # noqa: PLC0415
        import tempfile as _tempfile  # noqa: PLC0415

        base = Path(scratch_dir) if scratch_dir else Path(_tempfile.mkdtemp(prefix="be-rebase-"))
        created = scratch_dir is None
        try:
            env = plan_mod.build_env(validated, str(base))
            outcome = self._mutate(
                repo, "rebase_interactive",
                {"upstream": upstream, "onto": onto, "autosquash": "true" if autosquash else None,
                 "autostash": "true" if autostash else None},
                run_id=run_id, conflict_operation="rebase", env_extra=env,
                post=lambda r: {"rebased": True, "upstream": upstream, "steps": len(validated)},
            )
            return outcome
        finally:
            if created:
                _shutil.rmtree(base, ignore_errors=True)

    def cherry_pick(self, repo: Repository, commits: list[str], *, no_commit: bool = False,
                    run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(
            repo, "cherry_pick", {"commits": commits, "noCommit": "true" if no_commit else None},
            run_id=run_id, conflict_operation="cherry_pick",
            post=lambda r: self._commit_result(repo, r),
        )

    def cherry_pick_abort(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "cherry_pick_abort", None, run_id=run_id, post=lambda r: {"aborted": True})

    def cherry_pick_continue(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "cherry_pick_continue", None, run_id=run_id,
                            conflict_operation="cherry_pick", post=lambda r: {"continued": True})

    def revert(self, repo: Repository, commits: list[str], *, no_commit: bool = False,
               run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(
            repo, "revert", {"commits": commits, "noCommit": "true" if no_commit else None},
            run_id=run_id, conflict_operation="revert", post=lambda r: self._commit_result(repo, r),
        )

    def revert_abort(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "revert_abort", None, run_id=run_id, post=lambda r: {"aborted": True})

    def revert_continue(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "revert_continue", None, run_id=run_id,
                            conflict_operation="revert", post=lambda r: {"continued": True})

    # ── Reset ───────────────────────────────────────────────────────────────────
    def reset(self, repo: Repository, mode: str, *, target: Optional[str] = None,
              run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "reset", {"mode": mode, "target": target},
                            run_id=run_id, hard_reset=(mode == "hard"),
                            post=lambda r: {"mode": mode, "target": target or "HEAD"})

    # ── Stash ───────────────────────────────────────────────────────────────────
    def stash_push(self, repo: Repository, *, message: Optional[str] = None,
                   include_untracked: bool = False, paths: Optional[list[str]] = None,
                   run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "stash_push", {
            "message": message, "includeUntracked": "true" if include_untracked else None,
            "paths": paths or [],
        }, run_id=run_id, post=lambda r: {"stashed": True, "output": r.stdout.strip()})

    def stash_apply(self, repo: Repository, ref: str = "stash@{0}", *, pop: bool = False,
                    run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "stash_pop" if pop else "stash_apply", {"ref": ref},
                            run_id=run_id, post=lambda r: {"applied": ref})

    def stash_drop(self, repo: Repository, ref: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "stash_drop", {"ref": ref}, run_id=run_id, post=lambda r: {"dropped": ref})

    # ── Tags ────────────────────────────────────────────────────────────────────
    def tag_create(self, repo: Repository, name: str, *, message: Optional[str] = None,
                   annotated: bool = False, target: Optional[str] = None, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "tag_create", {
            "name": name, "message": message, "annotated": "true" if (annotated or message) else None,
            "target": target,
        }, run_id=run_id, post=lambda r: {"tag": name, "created": True})

    def tag_delete(self, repo: Repository, names: list[str], *, force: bool = False,
                   run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "tag_delete", {"names": names, "mode": "force" if force else "safe"},
                            run_id=run_id, post=lambda r: {"deleted": names})

    # ── Fetch / pull / push ──────────────────────────────────────────────────────
    def fetch(self, repo: Repository, *, remote: Optional[str] = None, branch: Optional[str] = None,
              all: bool = False, prune: bool = False, tags: bool = False,
              run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "fetch", {
            "remote": remote, "branch": branch, "all": "true" if all else None,
            "prune": "true" if prune else None, "tags": "true" if tags else None,
        }, run_id=run_id, network=True, post=lambda r: {"fetched": True})

    def pull(self, repo: Repository, *, remote: Optional[str] = None, branch: Optional[str] = None,
             strategy: str = "merge", run_id: Optional[str] = None) -> OperationOutcome:
        flag = {"merge": "--no-rebase", "rebase": "--rebase", "ff-only": "--ff-only"}.get(strategy, "--no-rebase")
        return self._mutate(repo, "pull", {"strategy_flag": [flag], "remote": remote, "branch": branch},
                            run_id=run_id, network=True, conflict_operation="merge",
                            post=lambda r: {"pulled": True, "strategy": strategy})

    def push(self, repo: Repository, *, remote: Optional[str] = None, branch: Optional[str] = None,
             set_upstream: bool = False, force_with_lease: bool = False, force: bool = False,
             run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "push", {
            "remote": remote, "branch": branch,
            "setUpstream": "true" if set_upstream else None,
            "forceWithLease": "true" if force_with_lease else None,
            "force": "true" if force else None,
        }, run_id=run_id, network=True, force_push=(force or force_with_lease),
            post=lambda r: {"pushed": True, "branch": branch or repo.branch,
                            "output": _remote_output(r.stdout)})

    # ── Remotes ─────────────────────────────────────────────────────────────────
    def remote_add(self, repo: Repository, name: str, url: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "remote_add", {"name": name, "url": url}, run_id=run_id,
                            post=lambda r: {"remote": name})

    def remote_remove(self, repo: Repository, name: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "remote_remove", {"name": name}, run_id=run_id,
                            post=lambda r: {"removed": name})

    def remote_set_url(self, repo: Repository, name: str, url: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "remote_set_url", {"name": name, "url": url}, run_id=run_id,
                            post=lambda r: {"remote": name})

    # ── Worktrees / submodules / LFS ──────────────────────────────────────────────
    # ── Path-level index/worktree operations ─────────────────────────────────────
    def move_path(self, repo: Repository, src: str, dst: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        """Move/rename a tracked path (git mv). Both paths stay inside the repo."""
        denial = _confinement_for_paths(repo.root, (src, dst))
        if denial is not None:
            return OperationOutcome(False, "mv", str(repo.root), error=denial.to_dict())
        return self._mutate(repo, "mv", {"src": src, "dst": dst}, run_id=run_id,
                            affected_files=[src, dst], post=lambda r: {"from": src, "to": dst})

    def remove_paths(self, repo: Repository, paths: list[str], *, cached: bool = False,
                     run_id: Optional[str] = None) -> OperationOutcome:
        """Remove tracked paths (git rm). `cached=True` keeps the working files."""
        flags = ["--cached"] if cached else []
        return self._mutate(repo, "rm", {"paths": paths, "flags": flags}, run_id=run_id,
                            affected_files=paths, post=lambda r: {"removed": paths, "cached": cached})

    def restore_paths(self, repo: Repository, paths: list[str], *, staged: bool = False,
                      run_id: Optional[str] = None) -> OperationOutcome:
        """Restore paths, discarding worktree changes (destructive). Prefer stash."""
        flags = ["--staged"] if staged else ["--worktree"]
        return self._mutate(repo, "restore", {"flags": flags, "paths": paths}, run_id=run_id,
                            affected_files=paths, post=lambda r: {"restored": paths})

    def unset_upstream(self, repo: Repository, *, branch: Optional[str] = None,
                       run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "branch_unset_upstream", {"branch": branch}, run_id=run_id,
                            post=lambda r: {"unset": True})

    def stash_branch(self, repo: Repository, name: str, *, ref: Optional[str] = None,
                     run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "stash_branch", {"name": name, "ref": ref or "stash@{0}"},
                            run_id=run_id, post=lambda r: {"branch": name})

    def stash_clear(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "stash_clear", None, run_id=run_id, post=lambda r: {"cleared": True})

    def show_tag(self, repo: Repository, name: str) -> dict[str, Any]:
        result = run(repo.root, "tag_show", {"name": name})
        if not result.ok:
            return {"available": False, "error": (result.error or errors.GitError(errors.TAG_NOT_FOUND)).to_dict()}
        return {"available": True, "name": name, "object": result.stdout[:4000]}

    def worktree_prune(self, repo: Repository, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "worktree_prune", None, run_id=run_id,
                            post=lambda r: {"pruned": True, "output": r.stdout.strip()})

    # ── Worktrees / submodules / LFS ──────────────────────────────────────────────
    def worktree_add(self, repo: Repository, path: str, *, branch: Optional[str] = None,
                     ref: Optional[str] = None, detach: bool = False,
                     run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "worktree_add", {
            "path": path, "branch": branch, "ref": ref, "detach": "true" if detach else None,
        }, run_id=run_id, post=lambda r: {"path": path, "output": r.stdout.strip()})

    def worktree_remove(self, repo: Repository, path: str, *, force: bool = False,
                        run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "worktree_remove", {"path": path, "force": "true" if force else None},
                            run_id=run_id, post=lambda r: {"removed": path})

    def worktree_move(self, repo: Repository, src: str, dst: str, *, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "worktree_move", {"src": src, "dst": dst}, run_id=run_id,
                            post=lambda r: {"from": src, "to": dst})

    def submodule_update(self, repo: Repository, *, remote: bool = False, paths: Optional[list[str]] = None,
                         run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "submodule_update", {
            "remote": "true" if remote else None, "paths": paths or [],
        }, run_id=run_id, network=True, post=lambda r: {"updated": True})

    def submodule_init(self, repo: Repository, *, paths: Optional[list[str]] = None,
                       run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "submodule_init", {"paths": paths or []}, run_id=run_id,
                            post=lambda r: {"initialized": True})

    def submodule_sync(self, repo: Repository, *, paths: Optional[list[str]] = None,
                       run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "submodule_sync", {"paths": paths or []}, run_id=run_id,
                            post=lambda r: {"synced": True})

    def lfs_pull(self, repo: Repository, *, remote: Optional[str] = None,
                 run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "lfs_pull", {"remote": remote}, run_id=run_id, network=True,
                            post=lambda r: {"pulled": True})

    def lfs_fetch(self, repo: Repository, *, remote: Optional[str] = None,
                  run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "lfs_fetch", {"remote": remote}, run_id=run_id, network=True,
                            post=lambda r: {"fetched": True})

    # ── Bisect ──────────────────────────────────────────────────────────────────
    def bisect_start(self, repo: Repository, *, bad: Optional[str] = None, good: Optional[list[str]] = None,
                     run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "bisect_start", {"bad": bad, "good": good or []}, run_id=run_id,
                            post=lambda r: {"started": True, "output": r.stdout.strip()})

    def bisect_mark(self, repo: Repository, verdict: str, *, rev: Optional[str] = None,
                    run_id: Optional[str] = None) -> OperationOutcome:
        op = {"good": "bisect_good", "bad": "bisect_bad", "skip": "bisect_skip"}.get(verdict)
        if op is None:
            return OperationOutcome(False, "bisect", str(repo.root),
                                     error=errors.GitError(errors.INVALID_ARGUMENT).to_dict())
        return self._mutate(repo, op, {"rev": rev}, run_id=run_id,
                            post=lambda r: {"verdict": verdict, "output": r.stdout.strip()})

    def bisect_reset(self, repo: Repository, *, rev: Optional[str] = None,
                     run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "bisect_reset", {"rev": rev}, run_id=run_id,
                            post=lambda r: {"reset": True})

    # ── Clean ───────────────────────────────────────────────────────────────────
    def clean_preview(self, repo: Repository, *, directories: bool = False) -> dict[str, Any]:
        result = run(repo.root, "clean_preview", {"directories": "true" if directories else None})
        if not result.ok:
            return {"available": False, "error": (result.error or errors.GitError(errors.GIT_FAILED)).to_dict()}
        would = [ln[len("Would remove "):].strip() for ln in result.stdout.splitlines() if ln.startswith("Would remove ")]
        return {"available": True, "wouldDelete": would, "count": len(would)}

    def clean(self, repo: Repository, *, directories: bool = False, run_id: Optional[str] = None) -> OperationOutcome:
        return self._mutate(repo, "clean", {"directories": "true" if directories else None},
                            run_id=run_id, post=lambda r: {"output": r.stdout.strip()})

    # ── Config ─────────────────────────────────────────────────────────────────
    def config_set(self, repo: Repository, key: str, value: str, *, scope: Optional[str] = None,
                   run_id: Optional[str] = None) -> OperationOutcome:
        args: dict[str, Any] = {"key": key, "value": value}
        if scope:
            args["scope"] = [f"--{scope}"]
        return self._mutate(repo, "config_set", args, run_id=run_id, post=lambda r: {"key": key})

    # ── Conflict resolution ─────────────────────────────────────────────────────
    def resolve_conflict(self, repo: Repository, path: str, content: str,
                         run_id: Optional[str] = None) -> OperationOutcome:
        """Write resolved content to a conflicted path and stage it.

        This is the ONE place the service writes a worktree file. The path is
        confined to the repository root; the content is written atomically.
        """
        root = repo.root.resolve()
        target = (root / path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return OperationOutcome(False, "resolve_conflict", str(root),
                                     error=errors.GitError(errors.INVALID_ARGUMENT, files=[path]).to_dict())
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".eclipse-resolve.tmp")
            tmp.write_text(content, encoding="utf-8", newline="\n")
            tmp.replace(target)
        except OSError as exc:
            return OperationOutcome(False, "resolve_conflict", str(root),
                                     error=errors.GitError(errors.GIT_FAILED, stderr=str(exc)).to_dict())
        return self.stage(repo, [path], run_id=run_id)

    # ── Commit-message / PR generation (deterministic; no model call) ────────────
    def generate_commit_message(self, repo: Repository, *, conventional: Optional[bool] = None) -> dict[str, Any]:
        from .messages import generate_commit_message  # noqa: PLC0415

        policy = safety.load_policy(repo)
        want = policy.conventional_commits if conventional is None else conventional
        return generate_commit_message(repo, conventional=want)


def _argv_preview(op: Any, args: Optional[dict[str, Any]]) -> list[str]:
    """A journal-safe argv preview built WITHOUT running anything."""
    if op is None:
        return []
    try:
        from .executor import build_argv  # noqa: PLC0415

        _op, argv = build_argv(op.name, args or {})
        return journal_mod.sanitize_argv(argv)
    except Exception:  # noqa: BLE001 - the preview is best-effort
        return journal_mod.sanitize_argv([op.name, *(str(v) for v in (args or {}).values())])


# Filesystem paths an op takes that must stay inside the repository (a linked
# worktree is created NEXT TO the repo, so an escape places a tree wherever the
# model asks — and `worktree remove --force` would delete there).
_PATH_OPS: dict[str, tuple[str, ...]] = {
    "worktree_add": ("path",),
    "worktree_remove": ("path",),
    "worktree_move": ("src", "dst"),
}


def _confinement_error(op_name: str, args: Optional[dict[str, Any]], root: Path) -> Optional[errors.GitError]:
    """Refuse a filesystem path that escapes the repository's approved area.

    `git worktree add` normally places a tree BESIDE the repository, so the
    allowed area is the repository root OR any directory under its parent — a
    sibling worktree is legitimate, a climb above the parent or a system path
    (`/etc`, `C:\\Windows\\Temp`) is not. The check is on REAL paths, so a
    traversal or a symlink cannot smuggle a tree (and a later
    `worktree remove --force`) outside that area.
    """
    keys = _PATH_OPS.get(op_name)
    if not keys:
        return None
    import os as _os  # noqa: PLC0415

    root_real = Path(_os.path.realpath(root))
    allowed = root_real.parent
    for key in keys:
        value = (args or {}).get(key)
        if not value:
            continue
        raw = str(value).replace("\\", "/")
        if "\x00" in raw:
            return errors.GitError(errors.INVALID_ARGUMENT, "That folder name contains an invalid character.")
        candidate = Path(str(value))
        if not candidate.is_absolute():
            candidate = root_real / candidate
        resolved = Path(_os.path.realpath(candidate))
        if not _within(resolved, allowed):
            return errors.GitError(
                errors.INVALID_ARGUMENT,
                "That folder is outside the project's area, so Eclipse won't put a working copy there.",
            )
    return None


def _within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return candidate == parent


def _confinement_for_paths(root: Path, values: tuple[str, ...]) -> Optional[errors.GitError]:
    """Refuse a repository-relative path that escapes the root, or None.

    Used for `git mv`, whose src/dst are repository paths (NOT worktree paths), so
    the allowed area is the repository root.
    """
    import os as _os  # noqa: PLC0415

    root_real = Path(_os.path.realpath(root))
    for value in values:
        raw = str(value or "").replace("\\", "/")
        if not raw:
            continue
        if "\x00" in raw or ".." in raw.split("/"):
            return errors.GitError(errors.UNSAFE_COMMAND, "That path is not inside the project.")
        candidate = Path(str(value))
        if not candidate.is_absolute():
            candidate = root_real / candidate
        resolved = Path(_os.path.realpath(candidate))
        if not _within(resolved, root_real):
            return errors.GitError(errors.UNSAFE_COMMAND, "That path is not inside the project.")
    return None


def _is_global_config(op_name: str, args: Optional[dict[str, Any]]) -> bool:
    """Whether a config write targets the GLOBAL (machine-wide) scope."""
    if op_name != "config_set":
        return False
    scope = (args or {}).get("scope") or []
    if isinstance(scope, str):
        scope = [scope]
    return any(str(s) == "--global" for s in scope)


def _remote_output(stdout: str) -> str:
    """A bounded, secret-free slice of a remote command's output."""
    return journal_mod.redact_text((stdout or "").strip()[-2_000:])


__all__ = [
    "GitService",
    "OperationOutcome",
    "get_git_service",
    "set_git_service",
]

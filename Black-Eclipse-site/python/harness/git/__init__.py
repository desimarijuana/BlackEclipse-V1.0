"""The Git / Version-Control subsystem.

A production-grade Git engine for an agentic coding environment. It is NOT a
thin wrapper around `git status`/`commit`/`push`: it is a layered subsystem.

    Agent tools (`git/tools.py`)
        → Git service facade (`git/service.py`)
            → repository discovery, executor, parsers, safety, journal
                → `code/sandbox.py` (the ONE bounded process primitive)
        → VCS provider layer (`git/vcs/`) for GitHub/GitLab/Bitbucket

Design rules (non-negotiable, mirroring the rest of the harness):

  * Local Git and remote hosting are SEPARATE concerns. Git is the local VCS;
    GitHub/GitLab/Bitbucket are remote collaboration providers behind the VCS
    abstraction. Neither depends on the other.
  * Every git child process is ONE fixed argv with NO shell, built from a CLOSED
    operation table. The model never supplies an executable, a flag or a shell
    fragment. An unlisted subcommand or a forbidden flag is refused.
  * The environment is scrubbed (`policy.SECRET_ENV_ALLOWLIST`); credentials are
    never passed through the runtime and never logged.
  * Every mutating operation returns a deterministic structured result; every
    destructive operation is risk-classified and routed through authorization.
  * Important state transitions are recoverable (operation journal + state
    machine); a conflicted/rebasing/bisecting repository is detected, never
    silently abandoned.

Modules are deliberately small (under the harness size ceiling) and single
purpose. Nothing here imports `main`; shared service state is reached through
`harness.deps` at the route layer only.
"""

from __future__ import annotations

__all__ = ["GitService", "get_git_service", "set_git_service"]


def __getattr__(name: str):  # pragma: no cover - lazy re-export only
    if name in ("GitService", "get_git_service", "set_git_service"):
        from .service import GitService, get_git_service, set_git_service

        return {
            "GitService": GitService,
            "get_git_service": get_git_service,
            "set_git_service": set_git_service,
        }[name]
    raise AttributeError(name)

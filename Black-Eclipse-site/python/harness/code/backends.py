"""The execution-backend interface (Phase 11 §6.5).

Where a command actually runs. Each backend DECLARES its guarantees so the
user-facing answer can be honest about what was and was not contained. Nothing
about the *policy* changes: the class table, the protected paths and the approval
rules are the same wherever the command runs. A backend only names where the work
happens and what it can promise.

Three backends are declared:

  * ``local``     — the zero-config default. Process-level bounds only, enforced
                     by ``code/sandbox.py``: no network by policy, workspace-
                     confined paths, wall-clock and output caps. Its guarantees are
                     built from the EXISTING policy constants, so an upgrade cannot
                     silently restate a weaker guarantee as a stronger one.
  * ``container`` — a real filesystem boundary, an explicit network flag and
                     cpu/memory limits. OPTIONAL; detected, never installed.
  * ``remote``    — whatever the endpoint advertises, and nothing more. OPTIONAL;
                     off unless explicitly configured.

The honest-failure rule is absolute (README §3.5): an unavailable backend is
reported as unavailable, and a job that requires it REFUSES with
``SANDBOX_UNAVAILABLE``. It never degrades to ``local`` and never runs
unsandboxed. There is no ``except: backend = "local"`` anywhere in this module.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Protocol

from . import policy
from . import sandbox

# Stable, structured refusal code. Mirrors `sandbox.SandboxUnavailable.code` and
# the i18n key `refusal.SANDBOX_UNAVAILABLE`.
SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"

# The backends this module knows.
BACKEND_NAMES: tuple[str, ...] = ("local", "container", "remote")

# Environment knobs. A container runtime is DETECTED, never installed.
CONTAINER_BACKEND_ENV = "HARNESS_SANDBOX_CONTAINER"   # e.g. "docker" | "podman"
REMOTE_BACKEND_ENV = "HARNESS_SANDBOX_REMOTE_URL"
REMOTE_TOKEN_ENV = "HARNESS_SANDBOX_REMOTE_TOKEN"


def _plain_backend_reason(name: str) -> str:
    """ONE plain sentence for a missing backend, never a mechanism code."""
    return (
        "This job needs a way to run its work that isn't set up on this "
        "computer. I did not run it."
    )


@dataclass(frozen=True)
class SandboxGuarantees:
    """What a backend can actually promise. Quoted verbatim in a refusal."""

    filesystem: str                 # filesystem isolation
    network: str                    # network posture
    resources: str                  # cpu / memory limits
    wall_clock: str                 # lifetime bound
    process_tree: str               # how a runaway tree is stopped
    env: str                        # environment scrub posture
    output_cap: str                 # output bound

    def as_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}

    def summary(self) -> str:
        """A compact, honest, one-line summary of the declaration."""
        return (
            f"{self.filesystem}; {self.network}; {self.resources}; "
            f"{self.wall_clock}; {self.env}"
        )


class SandboxBackend(Protocol):
    """Where a command actually runs."""

    name: str
    guarantees: SandboxGuarantees
    available: bool

    def describe(self) -> dict[str, Any]: ...

    async def run(self, spec: sandbox.RunSpec) -> sandbox.RawResult: ...


@dataclass
class LocalBackend:
    """The zero-config default: `code/sandbox.py`'s process-level bounds.

    Its declared guarantees are DERIVED from the existing policy constants, so
    they cannot drift from what is enforced.
    """

    name: str = "local"
    guarantees: SandboxGuarantees = field(default_factory=lambda: _local_guarantees())
    available: bool = True

    def __post_init__(self) -> None:
        # `available` is real: probed, never assumed.
        try:
            sandbox.select_backend()
            self.available = True
        except sandbox.SandboxUnavailable:
            self.available = False

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "guarantees": self.guarantees.as_dict(),
        }

    async def run(self, spec: sandbox.RunSpec) -> sandbox.RawResult:
        return sandbox.run(spec)


def _local_guarantees() -> SandboxGuarantees:
    """Build the `local` declaration from the ENFORCED policy constants.

    G3b compares this against the constants directly: a change that weakens what
    is enforced changes the declaration with it, so the app can never claim a
    guarantee it does not hold.
    """
    network = (
        "network is denied by policy for analysis runs (blocked by construction: "
        "a fixed module list, restricted builtins, no URL literals); commands "
        "that declare network run with host network"
        if not policy.NETWORK_DEFAULT else "network policy allows it"
    )
    return SandboxGuarantees(
        filesystem=(
            "no OS-level filesystem isolation — a launched program can read the "
            "host as the user; write paths are confined to the task's own folder "
            f"by policy and {len(policy.PROTECTED_PATHS)} protected locations are "
            "never touched by the tools"
        ),
        network=network,
        resources=(
            "process-level bounds only for commands; the analysis profile sets "
            "cpu/memory/process limits per run"
        ),
        wall_clock="a wall-clock limit stops a run that takes too long",
        process_tree="the whole process tree is killed on timeout or cancel",
        env=(
            "a scrubbed environment; only "
            f"{len(policy.SECRET_ENV_ALLOWLIST)} named variables are copied"
        ),
        output_cap=f"{sandbox.MAX_OUTPUT_CAP_BYTES} byte output cap",
    )


@dataclass
class ContainerBackend:
    """A real filesystem boundary via a container runtime. OPTIONAL.

    Detected from the environment, never installed. Until a runtime is present the
    backend is UNAVAILABLE and a job that requires it refuses — it never degrades
    to `local`.
    """

    runtime: Optional[str] = None
    name: str = "container"

    def __post_init__(self) -> None:
        self.runtime = self.runtime or os.environ.get(CONTAINER_BACKEND_ENV) or None

    @property
    def available(self) -> bool:
        return bool(self.runtime) and shutil.which(str(self.runtime)) is not None

    @property
    def guarantees(self) -> SandboxGuarantees:
        if not self.available:
            return SandboxGuarantees(
                filesystem="not available",
                network="not available",
                resources="not available",
                wall_clock="not available",
                process_tree="not available",
                env="not available",
                output_cap="not available",
            )
        return SandboxGuarantees(
            filesystem="a real filesystem boundary; only the task's folder is mounted",
            network="network is off unless the job explicitly asks for it",
            resources="cpu and memory limits are set per run",
            wall_clock="a wall-clock limit stops a run that takes too long",
            process_tree="the container is torn down when the run ends",
            env="only an explicit, minimal environment is passed in",
            output_cap=f"{sandbox.MAX_OUTPUT_CAP_BYTES} byte output cap",
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "runtime": self.runtime,
            "guarantees": self.guarantees.as_dict(),
        }

    async def run(self, spec: sandbox.RunSpec) -> sandbox.RawResult:
        raise sandbox.SandboxUnavailable(
            _plain_backend_reason(self.name)
        )


@dataclass
class RemoteBackend:
    """Whatever the endpoint advertises, and nothing more. OPTIONAL, off by default."""

    url: Optional[str] = None
    name: str = "remote"

    def __post_init__(self) -> None:
        self.url = self.url or os.environ.get(REMOTE_BACKEND_ENV) or None

    @property
    def available(self) -> bool:
        return bool(self.url)

    @property
    def guarantees(self) -> SandboxGuarantees:
        if not self.available:
            return SandboxGuarantees(
                filesystem="not configured",
                network="not configured",
                resources="not configured",
                wall_clock="not configured",
                process_tree="not configured",
                env="not configured",
                output_cap="not configured",
            )
        return SandboxGuarantees(
            filesystem="whatever the configured endpoint advertises, and nothing more",
            network="whatever the configured endpoint advertises, and nothing more",
            resources="whatever the configured endpoint advertises, and nothing more",
            wall_clock="a wall-clock limit stops a run that takes too long",
            process_tree="whatever the configured endpoint advertises, and nothing more",
            env="a scrubbed environment; the endpoint never receives the runtime secret",
            output_cap=f"{sandbox.MAX_OUTPUT_CAP_BYTES} byte output cap",
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "configured": bool(self.url),
            "guarantees": self.guarantees.as_dict(),
        }

    async def run(self, spec: sandbox.RunSpec) -> sandbox.RawResult:
        raise sandbox.SandboxUnavailable(
            _plain_backend_reason(self.name)
        )


def available_backends() -> dict[str, SandboxBackend]:
    return {
        "local": LocalBackend(),
        "container": ContainerBackend(),
        "remote": RemoteBackend(),
    }


def select_backend(name: str = "local") -> SandboxBackend:
    """Return the named backend, or REFUSE with SANDBOX_UNAVAILABLE.

    Never degrades: an unavailable `container`/`remote` refuses; it is never
    substituted with `local`. An unknown name refuses too.
    """
    backends = available_backends()
    backend = backends.get(name)
    if backend is None:
        raise sandbox.SandboxUnavailable(f"no backend named {name!r}")
    if not backend.available:
        raise sandbox.SandboxUnavailable(
            f"{name} backend is not available: {_plain_backend_reason(name)}"
        )
    return backend


def describe_all() -> dict[str, Any]:
    """Honest state of every backend, for `doctor.js` and the UI."""
    out: dict[str, Any] = {}
    for name, backend in available_backends().items():
        out[name] = backend.describe()
    return out


__all__ = [
    "BACKEND_NAMES",
    "CONTAINER_BACKEND_ENV",
    "ContainerBackend",
    "LocalBackend",
    "REMOTE_BACKEND_ENV",
    "REMOTE_TOKEN_ENV",
    "RemoteBackend",
    "SANDBOX_UNAVAILABLE",
    "SandboxBackend",
    "SandboxGuarantees",
    "available_backends",
    "describe_all",
    "select_backend",
]

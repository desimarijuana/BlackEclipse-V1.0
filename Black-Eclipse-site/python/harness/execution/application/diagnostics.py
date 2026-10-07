"""Runtime diagnostics — classify a failure into a structured, actionable cause.

Never returns "command failed". Given the output/exit code of a failed step (or a
health check, a port conflict, a missing variable), it returns a
`RuntimeDiagnosis` with a category, a severity, evidence, suggested recovery
strategies and — crucially for autonomous debugging — a code location
(`{file,line,column}`) when the output names one. That location is what connects
runtime errors to the code-intelligence layer so the agent can read the source.

The parser rules are deterministic and reuse the execution layer's diagnostic
normalizer for the location, so there is ONE parser of compiler/runtime output.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..diagnostics import DiagnosticEngine
from .models import DiagnosticCategory, RecoveryStrategy, RuntimeDiagnosis


def _strategies(*items: RecoveryStrategy) -> list[RecoveryStrategy]:
    return list(items)


class RuntimeDiagnosticsEngine:
    """Classify a runtime failure into a structured diagnosis."""

    def __init__(self, diagnostics: Optional[DiagnosticEngine] = None) -> None:
        self._diag = diagnostics or DiagnosticEngine()

    def classify(
        self,
        *,
        output: str = "",
        exit_code: Optional[int] = None,
        step: str = "",
        language: str = "",
        missing_env: Optional[list[str]] = None,
        port_conflict: Optional[int] = None,
        health: Optional[dict[str, Any]] = None,
        reason: str = "",
        source: str = "",
    ) -> RuntimeDiagnosis:
        text = (output or "") + ("\n" + reason if reason else "")
        lowered = text.casefold()

        if port_conflict:
            return RuntimeDiagnosis(
                category=DiagnosticCategory.PORT_CONFLICT, severity="high",
                message=f"Port {port_conflict} is already in use.",
                evidence=[f"port {port_conflict} is occupied"],
                suggested_actions=_strategies(
                    RecoveryStrategy.SELECT_ALTERNATIVE_PORT, RecoveryStrategy.RETRY,
                ),
                recoverable=True, source=source or "port",
            )

        if missing_env:
            names = ", ".join(missing_env[:5])
            return RuntimeDiagnosis(
                category=DiagnosticCategory.ENVIRONMENT_MISSING, severity="high",
                message=f"Required environment value(s) are missing: {names}.",
                evidence=[f"missing: {n}" for n in missing_env[:10]],
                suggested_actions=_strategies(RecoveryStrategy.RELOAD_ENVIRONMENT),
                recoverable=True, source=source or "environment",
            )

        if health is not None and not health.get("ok", True):
            return RuntimeDiagnosis(
                category=DiagnosticCategory.CONTAINER_HEALTH_FAILURE
                if health.get("kind") == "container" else DiagnosticCategory.UNKNOWN,
                severity="high",
                message=str(health.get("detail") or "the health check did not pass."),
                evidence=[str(health.get("detail") or "")],
                suggested_actions=_strategies(RecoveryStrategy.RESTART, RecoveryStrategy.RETRY),
                recoverable=True, source=source or "health",
            )

        # Ordered, specific matchers (each a deterministic signal).
        checks: tuple[tuple[DiagnosticCategory, str, tuple[RecoveryStrategy, ...], str], ...] = (
            (DiagnosticCategory.COMMAND_NOT_FOUND,
             r"(not recognized as an internal|command not found|no such file or directory|"
             r"is not recognized|cannot find the file specified|executable file not found)",
             (RecoveryStrategy.REINSTALL_DEPENDENCIES, RecoveryStrategy.RETRY), "high"),
            (DiagnosticCategory.RUNTIME_MISSING,
             r"(runtime is not (available|installed)|no such runtime|interpreter .* not found|"
             r"python.* not found|node.* not found)",
             (RecoveryStrategy.RETRY,), "high"),
            (DiagnosticCategory.DEPENDENCY_CONFLICT,
             r"(peer dep|eresolve|conflicting peer|dependency resolution failed|"
             r"version conflict|incompatible|cannot satisfy)",
             (RecoveryStrategy.REINSTALL_DEPENDENCIES,), "high"),
            (DiagnosticCategory.DEPENDENCY_FAILURE,
             r"(npm err|pnpm err|yarn err|err_pnpm|err_npm|err_yarn|pip.* error|"
             r"could not resolve|unable to resolve|failed to (install|download|fetch)|"
             r"module not found|cannot find module|modulenotfounderror|importerror|"
             r"no_lockfile|lockfile.* not found|requires a .*lock)",
             (RecoveryStrategy.REINSTALL_DEPENDENCIES, RecoveryStrategy.RETRY), "high"),
            (DiagnosticCategory.PERMISSION_DENIED,
             r"(permission denied|eacces|eperm|access is denied|operation not permitted)",
             (RecoveryStrategy.NONE,), "high"),
            (DiagnosticCategory.ENVIRONMENT_INVALID,
             r"(invalid .*(env|value|format)|failed to parse .*env|malformed .*env)",
             (RecoveryStrategy.RELOAD_ENVIRONMENT,), "medium"),
            (DiagnosticCategory.DATABASE_UNAVAILABLE,
             r"(connection refused|could not connect to (server|database)|database .* does not exist|"
             r"econnrefused|can't connect to .*postgres|redis.* error|unable to connect)",
             (RecoveryStrategy.RESTART_DEPENDENCY, RecoveryStrategy.RETRY), "high"),
            (DiagnosticCategory.CONTAINER_CRASH,
             r"(container.* exited|container.* is not running|no such container|"
             r"oci runtime|container.* unhealthy)",
             (RecoveryStrategy.RECREATE_CONTAINER, RecoveryStrategy.RESTART), "high"),
            (DiagnosticCategory.NETWORK_FAILURE,
             r"(eai_again|enotfound|network is unreachable|getaddrinfo|"
             r"temporary failure in name resolution|socket hang up)",
             (RecoveryStrategy.RETRY,), "medium"),
            (DiagnosticCategory.BUILD_FAILURE,
             r"(build failed|compilation failed|error ts\d+|syntax error|"
             r"failed to compile|cmake error|cargo.* error\[)",
             (RecoveryStrategy.REBUILD,), "high"),
            (DiagnosticCategory.TIMEOUT,
             r"(timed out|timeout|deadline exceeded)",
             (RecoveryStrategy.RETRY, RecoveryStrategy.RESTART), "medium"),
            (DiagnosticCategory.PROCESS_CRASH,
             r"(process .* exited|segmentation fault|core dumped|panic:|killed)",
             (RecoveryStrategy.RESTART,), "high"),
        )

        severity = "medium"
        for category, pattern, strategies, sev in checks:
            if re.search(pattern, lowered):
                location = self._location(text, language=language)
                return RuntimeDiagnosis(
                    category=category, severity=sev,
                    message=self._message_for(category, output, exit_code),
                    evidence=self._evidence(text),
                    suggested_actions=_strategies(*strategies),
                    recoverable=(strategies != (RecoveryStrategy.NONE,)),
                    source=source or step or category.value,
                    location=location,
                )

        # A build/test step that failed with no recognized signature.
        if step in ("build", "BUILD") or exit_code not in (0, None):
            location = self._location(text, language=language)
            return RuntimeDiagnosis(
                category=DiagnosticCategory.BUILD_FAILURE if step in ("build", "BUILD") else DiagnosticCategory.UNKNOWN,
                severity=severity,
                message=self._message_for(DiagnosticCategory.UNKNOWN, output, exit_code),
                evidence=self._evidence(text),
                suggested_actions=_strategies(RecoveryStrategy.RETRY),
                recoverable=bool(step in ("build", "BUILD")),
                source=source or step,
                location=location,
            )

        return RuntimeDiagnosis(
            category=DiagnosticCategory.UNKNOWN, severity="medium",
            message=(reason or "the step failed for an unrecognized reason."),
            evidence=self._evidence(text), source=source or step,
            location=self._location(text, language=language),
        )

    def _message_for(self, category: DiagnosticCategory, output: str, exit_code: Optional[int]) -> str:
        base = {
            DiagnosticCategory.COMMAND_NOT_FOUND: "A required program is not installed.",
            DiagnosticCategory.RUNTIME_MISSING: "The runtime needed to run this application isn't available.",
            DiagnosticCategory.DEPENDENCY_FAILURE: "Installing or resolving the project's dependencies failed.",
            DiagnosticCategory.DEPENDENCY_CONFLICT: "Two dependencies require incompatible versions.",
            DiagnosticCategory.PERMISSION_DENIED: "The operation was refused for lack of permission.",
            DiagnosticCategory.ENVIRONMENT_INVALID: "One of the environment values has an invalid format.",
            DiagnosticCategory.DATABASE_UNAVAILABLE: "A database or cache service could not be reached.",
            DiagnosticCategory.CONTAINER_CRASH: "A container stopped unexpectedly.",
            DiagnosticCategory.NETWORK_FAILURE: "A network request failed.",
            DiagnosticCategory.BUILD_FAILURE: "The build failed.",
            DiagnosticCategory.TIMEOUT: "The step did not finish in time.",
            DiagnosticCategory.PROCESS_CRASH: "The process stopped unexpectedly.",
            DiagnosticCategory.UNKNOWN: f"The step failed with exit code {exit_code}." if exit_code is not None else "The step failed.",
        }.get(category, "The step failed.")
        first_line = _first_error_line(output)
        if first_line:
            return f"{base} {first_line}"
        return base

    def _evidence(self, text: str) -> list[str]:
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        return lines[:8]

    def _location(self, text: str, *, language: str) -> Optional[dict[str, Any]]:
        found = self._diag.normalize(text, language=language, source="runtime")
        for diag in found:
            if diag.file:
                return {"file": diag.file, "line": diag.line, "column": diag.column,
                        "message": diag.message, "code": diag.code}
        return None

    def from_exception(self, exc: BaseException, *, step: str = "") -> RuntimeDiagnosis:
        name = type(exc).__name__
        text = f"{name}: {exc}"
        lowered = text.casefold()
        if isinstance(exc, FileNotFoundError) or "no such file" in lowered or "not found" in lowered:
            return RuntimeDiagnosis(
                category=DiagnosticCategory.COMMAND_NOT_FOUND, severity="high",
                message="A required program is not installed.", evidence=[text],
                suggested_actions=_strategies(RecoveryStrategy.REINSTALL_DEPENDENCIES),
                recoverable=True, source=step,
            )
        if isinstance(exc, TimeoutError) or "timeout" in lowered:
            return RuntimeDiagnosis(
                category=DiagnosticCategory.TIMEOUT, severity="medium",
                message="The step did not finish in time.", evidence=[text],
                suggested_actions=_strategies(RecoveryStrategy.RETRY), recoverable=True, source=step,
            )
        if isinstance(exc, PermissionError) or "permission" in lowered:
            return RuntimeDiagnosis(
                category=DiagnosticCategory.PERMISSION_DENIED, severity="high",
                message="The operation was refused for lack of permission.", evidence=[text],
                recoverable=False, source=step,
            )
        return RuntimeDiagnosis(
            category=DiagnosticCategory.UNKNOWN, severity="medium",
            message=f"The step failed ({name}).", evidence=[text], source=step,
        )


def _first_error_line(output: str) -> str:
    for line in (output or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"(error|failed|exception|cannot|could not|refused)", stripped, re.I):
            return stripped[:240]
    return ""


__all__ = ["RuntimeDiagnosticsEngine"]

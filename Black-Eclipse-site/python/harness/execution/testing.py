"""The test engine — discover, plan, execute, normalize.

Results are normalized per framework where a machine-readable reporter exists
(vitest/jest JSON, pytest's summary) and, failing that, from the tool's summary
line. When nothing can be parsed the engine reports `parsed: false` with zero
counts — it NEVER reports a pass that it did not actually read. That is the
`NO FAKE SUCCESS` rule, enforced at the normalization boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..code import sandbox
from .diagnostics import DiagnosticEngine
from .models import TestResult, resource_run_kwargs


@dataclass
class TestDiscovery:
    """The discovered test surface of a project."""

    framework: str = ""
    tests: int = 0
    files: list[str] = field(default_factory=list)
    configuration: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework,
            "tests": self.tests,
            "files": self.files,
            "configuration": self.configuration,
        }


@dataclass
class TestRunResult:
    """The normalized outcome of one test run."""

    success: bool
    exit_code: Optional[int]
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: int = 0
    failures: list[TestResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    framework: str = ""
    parsed: bool = False
    note: str = ""
    backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success, "exitCode": self.exit_code,
            "passed": self.passed, "failed": self.failed, "skipped": self.skipped,
            "durationMs": self.duration_ms,
            "failures": [f.to_dict() for f in self.failures],
            "stdout": self.stdout, "stderr": self.stderr,
            "framework": self.framework, "parsed": self.parsed,
            "note": self.note, "backend": self.backend,
        }


# ── Summary parsers ──────────────────────────────────────────────────────────
#
# Each returns `(passed, failed, skipped, parsed)`. `parsed` is False when the
# parser found no recognizable summary — the caller must then report unparsed.

# Terminal color codes wrap the numbers (`\x1b[1m\x1b[32m2 passed`), so a summary
# can only be read after stripping ANSI. This is the SAME `strip_ansi` the
# terminal subsystem uses — one implementation, not a second one.
def _strip_ansi(text: str) -> str:
    try:
        from ...terminal.session import strip_ansi  # noqa: PLC0415

        return strip_ansi(text)
    except Exception:  # noqa: BLE001 - a missing helper must not break parsing
        return re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)

_VITEST_SUMMARY = re.compile(r"Tests\s+(?:(?P<failed>\d+)\s+failed\s*\|\s*)?(?P<passed>\d+)\s+passed", re.I)
_VITEST_SUMMARY_ALT = re.compile(r"Tests\s+(?P<passed>\d+)\s+passed(?:\s*\|\s*(?P<failed>\d+)\s+failed)?", re.I)
_JEST_SUMMARY = re.compile(r"Tests:\s*(?:(?P<failed>\d+)\s+failed,\s*)?(?P<passed>\d+)\s+passed(?:,\s*(?P<skipped>\d+)\s+skipped)?", re.I)
_PYTEST_SUMMARY = re.compile(r"(?P<count>\d+)\s+(?P<kind>passed|failed|skipped|error|errors|xpassed|xfailed)")
_GO_SUMMARY = re.compile(r"^(?:ok|FAIL|---)\s", re.M)


def _parse_summary(output: str, framework: str) -> tuple[int, int, int, bool]:
    text = _strip_ansi(output or "")
    if framework in ("vitest",):
        for pattern in (_VITEST_SUMMARY, _VITEST_SUMMARY_ALT):
            match = pattern.search(text)
            if match:
                return int(match.group("passed")), int(match.group("failed") or 0), 0, True
    if framework in ("jest",):
        match = _JEST_SUMMARY.search(text)
        if match:
            return int(match.group("passed")), int(match.group("failed") or 0), int(match.group("skipped") or 0), True
    if framework in ("pytest", "unittest"):
        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "errors": 0}
        found = False
        for match in _PYTEST_SUMMARY.finditer(text):
            kind = match.group("kind").casefold()
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
            found = True
        if found:
            return counts.get("passed", 0), counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0), counts.get("skipped", 0), True
    if framework in ("go-test",):
        if _GO_SUMMARY.search(text):
            passed = len(re.findall(r"^ok\s", text, re.M))
            failed = len(re.findall(r"^FAIL\s", text, re.M))
            return passed, failed, 0, True
    # A generic fallback: pytest-style / vitest-style counts appear in many runners.
    for pattern in (_VITEST_SUMMARY, _VITEST_SUMMARY_ALT):
        match = pattern.search(text)
        if match and ("Test Files" in text or "vitest" in text.casefold() or framework == "vitest"):
            return int(match.group("passed")), int(match.group("failed") or 0), 0, True
    if "passed" in text and ("failed" in text or "error" in text or "warning" in text):
        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "errors": 0}
        found = False
        for match in _PYTEST_SUMMARY.finditer(text):
            kind = match.group("kind").casefold()
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
            found = True
        if found:
            return counts.get("passed", 0), counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0), counts.get("skipped", 0), True
    return 0, 0, 0, False


def _parse_json_report(output: str) -> Optional[dict[str, Any]]:
    """Try to find a JSON reporter object with testResults in the output."""
    for candidate in _json_candidates(output):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and ("testResults" in data or "numTotalTests" in data):
            return data
    return None


def _json_candidates(output: str):
    text = output or ""
    start = text.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : index + 1]
                    break
        start = text.find("{", start + 1)
        if start > 20_000:
            break


class TestEngine:
    """Discover and run a project's tests in the sandbox."""

    def __init__(self, diagnostics: Optional[DiagnosticEngine] = None) -> None:
        self._diag = diagnostics or DiagnosticEngine()

    def discover(self, adapter: Any, root: Path, project: Any) -> TestDiscovery:
        framework = str(getattr(project, "test_framework", "") or "")
        files = adapter.discover_tests(root, project) if hasattr(adapter, "discover_tests") else []
        configuration = ""
        for candidate in ("vitest.config.ts", "vitest.config.js", "jest.config.js", "jest.config.ts",
                          "pytest.ini", "pyproject.toml", "tox.ini", "playwright.config.ts", "cypress.config.ts"):
            if (root / candidate).is_file():
                configuration = candidate
                break
        return TestDiscovery(framework=framework, tests=len(files), files=files, configuration=configuration)

    def run(
        self,
        adapter: Any,
        root: Path,
        project: Any,
        workdir: Path,
        *,
        test_policy: Optional[dict[str, Any]] = None,
        language: str = "",
        limits: Any = None,
        cancel_event: Optional[Any] = None,
    ) -> TestRunResult:
        policy = dict(test_policy or {})
        framework = str(policy.get("framework") or getattr(project, "test_framework", "") or "")
        policy.setdefault("framework", framework)
        prepared = adapter.test(root, project, policy, workdir)
        if prepared is None:
            return TestRunResult(
                success=False, exit_code=None, framework=framework,
                note="I couldn't find a test setup for this project", parsed=False,
            )
        env = sandbox.build_env(prepared.env or {})
        output_cap = getattr(limits, "max_stdout_bytes", 1_048_576) if limits else 1_048_576
        timeout_s = max(1, int((getattr(limits, "timeout_ms", 60_000) if limits else 60_000) // 1000))
        spec = sandbox.RunSpec(
            argv=list(prepared.argv), cwd=Path(prepared.cwd), env=env,
            timeout_s=timeout_s, output_cap_bytes=output_cap, network=bool(prepared.network),
            **(resource_run_kwargs(limits) if limits is not None else {}),
        )
        try:
            raw = sandbox.run(spec, cancel_event=cancel_event)
        except sandbox.SandboxUnavailable as exc:
            return TestRunResult(
                success=False, exit_code=None, framework=framework,
                note=f"tests couldn't run: {exc.reason}", parsed=False, backend="unavailable",
            )
        return self._normalize(raw, framework=framework, language=language)

    def _normalize(self, raw: Any, *, framework: str, language: str) -> TestRunResult:
        output = raw.output or ""
        passed, failed, skipped, parsed = _parse_summary(output, framework)
        failures: list[TestResult] = []
        report = _parse_json_report(output) if framework in ("vitest", "jest") else None
        if report is not None:
            parsed = True
            passed = failed = skipped = 0
            for suite in report.get("testResults", []) or []:
                for assertion in suite.get("assertionResults", []) or []:
                    status = str(assertion.get("status") or "").casefold()
                    title = str(assertion.get("title") or assertion.get("fullName") or "")
                    if status == "passed":
                        passed += 1
                    elif status == "pending" or status == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                        failures.append(TestResult(
                            suite=str(suite.get("name") or ""), test=title, status="FAILED",
                            error="; ".join(str(m) for m in (assertion.get("failureMessages") or [])),
                            file=str(suite.get("name") or ""),
                        ))
            if not report.get("testResults"):
                passed = int(report.get("numPassedTests") or 0)
                failed = int(report.get("numFailedTests") or 0)
                skipped = int(report.get("numPendingTests") or 0)
        if not failures and failed:
            # Derive failure entries from the diagnostics so the agent has file/line.
            for diag in self._diag.normalize(output, language=language, source="test"):
                failures.append(TestResult(
                    test=diag.message, status="FAILED", error=diag.message,
                    file=diag.file, line=diag.line, column=diag.column,
                ))
                if len(failures) >= failed and failed > 0:
                    break
        success = bool(raw.exit_code == 0 and not raw.timed_out and not raw.cancelled and parsed and failed == 0)
        note = ""
        if not parsed:
            note = "I couldn't read a test summary from the output"
        elif raw.timed_out:
            note = "the tests did not finish in time"
        return TestRunResult(
            success=success, exit_code=raw.exit_code, passed=passed, failed=failed,
            skipped=skipped, duration_ms=raw.duration_ms, failures=failures,
            stdout=output, framework=framework, parsed=parsed, note=note, backend=raw.backend,
        )


__all__ = ["TestDiscovery", "TestEngine", "TestRunResult"]

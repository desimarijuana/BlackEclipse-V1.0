"""Install and remove packages in the managed analysis environment.

This is a SEPARATE, approval-gated lane from generated-code execution: the
analysis sandbox has no network by construction, while a package install must
reach an index. The install runs as a controlled pip process with an absolute
interpreter path, an argv list (no shell), the scrubbed environment, a private
cache and a bounded lifetime. The package target is managed by Eclipse and only
that target is added to the analysis runner's `sys.path`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..code import sandbox
from .paths import (
    installed_packages,
    pip_cache,
    site_packages,
    write_lock,
)

_SPEC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.\-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!-]+)?$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DEFAULT_TIMEOUT_S = 600


@dataclass
class EnvResult:
    ok: bool
    code: str = "OK"
    reason: str = ""
    output: str = ""
    packages: list[dict[str, Any]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "reason": self.reason,
            "packages": self.packages,
            "removed": self.removed,
            "durationMs": self.duration_ms,
            "output": self.output[-8_000:],
        }


def normalize_specs(specs: list[Any]) -> tuple[list[str], str]:
    cleaned: list[str] = []
    for raw in specs or []:
        value = str(raw or "").strip()
        if not value:
            continue
        if not _SPEC.match(value):
            return [], f"{value!r} is not a plain package name with an optional version"
        cleaned.append(value)
    return list(dict.fromkeys(cleaned)), ""


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name or "")).casefold()


def _run_pip(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_s: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        shell=False,
        check=False,
    )


def install(
    specs: list[Any],
    *,
    interpreter: str,
    root: Optional[Path] = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> EnvResult:
    cleaned, error = normalize_specs(specs)
    if error:
        return EnvResult(ok=False, code="PACKAGE_SPEC_INVALID", reason=error)
    if not cleaned:
        return EnvResult(ok=False, code="PACKAGE_SPEC_REQUIRED", reason="no packages were named")
    if not interpreter:
        return EnvResult(ok=False, code="PYTHON_UNAVAILABLE", reason="the analysis interpreter is not installed")
    target = site_packages(root)
    cache = pip_cache(root)
    target.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    env = sandbox.build_env({
        "PIP_CACHE_DIR": str(cache),
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    argv = [
        interpreter, "-m", "pip", "install",
        "--target", str(target), "--upgrade",
        "--disable-pip-version-check", "--no-input",
        "--no-warn-script-location",
        *cleaned,
    ]
    started = time.monotonic()
    try:
        result = _run_pip(argv, cwd=target, env=env, timeout_s=max(1, int(timeout_s)))
    except subprocess.TimeoutExpired:
        return EnvResult(
            ok=False, code="PIP_TIMEOUT",
            reason=f"the install did not finish within {timeout_s}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except OSError as exc:
        return EnvResult(ok=False, code="PIP_UNAVAILABLE", reason=str(exc))
    duration_ms = int((time.monotonic() - started) * 1000)
    output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
    if result.returncode != 0:
        first = next((line for line in output.splitlines() if line.strip()), "pip failed")
        code = "PIP_UNAVAILABLE" if "No module named pip" in output else "PIP_FAILED"
        return EnvResult(ok=False, code=code, reason=first[:300], output=output, duration_ms=duration_ms)
    packages = installed_packages(root)
    write_lock(packages, root)
    return EnvResult(ok=True, packages=packages, output=output, duration_ms=duration_ms)


def remove(names: list[Any], *, root: Optional[Path] = None) -> EnvResult:
    target = site_packages(root)
    requested = [str(name or "").strip() for name in names or [] if str(name or "").strip()]
    if not requested:
        return EnvResult(ok=False, code="PACKAGE_SPEC_REQUIRED", reason="no packages were named")
    for name in requested:
        if not _NAME.match(name):
            return EnvResult(ok=False, code="PACKAGE_SPEC_INVALID", reason=f"{name!r} is not a package name")
    if not target.is_dir():
        return EnvResult(ok=False, code="PACKAGE_NOT_INSTALLED", reason="the managed environment is empty")
    try:
        from importlib.metadata import distributions  # noqa: PLC0415

        found = list(distributions(path=[str(target)]))
    except Exception:  # noqa: BLE001
        found = []
    wanted = {_canonical(name) for name in requested}
    removed: list[str] = []
    for dist in found:
        try:
            name = str(dist.metadata.get("Name") or "")
        except Exception:  # noqa: BLE001
            continue
        if _canonical(name) not in wanted:
            continue
        files = list(dist.files or [])
        if files:
            for file in files:
                path = (target / str(file)).resolve()
                try:
                    path.relative_to(target.resolve())
                except ValueError:
                    continue
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                except OSError:
                    continue
        else:
            try:
                from .paths import _modules  # noqa: PLC0415

                for module in _modules(dist):
                    path = (target / module).resolve()
                    try:
                        path.relative_to(target.resolve())
                    except ValueError:
                        continue
                    if path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                    elif path.is_file():
                        path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
        candidates: list[str] = []
        try:
            from .paths import _modules  # noqa: PLC0415

            candidates.extend(_modules(dist))
        except Exception:  # noqa: BLE001
            pass
        candidates.extend((name, name.replace("-", "_"), name.split(".")[0]))
        for module in dict.fromkeys(candidates):
            if not module:
                continue
            path = (target / module).resolve()
            try:
                path.relative_to(target.resolve())
            except ValueError:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
        dist_path = getattr(dist, "_path", None)
        if dist_path is not None:
            shutil.rmtree(Path(dist_path), ignore_errors=True)
        removed.append(name)
    remaining = installed_packages(root)
    write_lock(remaining, root)
    if not removed:
        return EnvResult(
            ok=False, code="PACKAGE_NOT_INSTALLED",
            reason=f"{', '.join(requested)} is not installed in the managed environment",
            packages=remaining,
        )
    return EnvResult(ok=True, removed=removed, packages=remaining)


__all__ = ["DEFAULT_TIMEOUT_S", "EnvResult", "install", "normalize_specs", "remove"]

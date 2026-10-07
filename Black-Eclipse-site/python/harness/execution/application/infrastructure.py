"""Terraform infrastructure adapter.

The `InfrastructureAdapter` implementation. It is a `CliAdapter` with a CLOSED
operation table, so the model never supplies an executable, a flag or a shell
fragment. Every call runs through the ONE sandbox.

`terraform apply` and `terraform destroy` are CRITICAL: they are removed at
`plan_only`, and the runtime policy additionally requires explicit
authorization. `init`/`validate`/`fmt`/`plan`/`output`/`show` are the read-only or
low-risk half and stay available for a question turn.

The working directory is always the project's own `terraform/` (or the root),
never a model-supplied absolute path outside it — the caller resolves and confines
it before the adapter runs.
"""

from __future__ import annotations

from typing import Any, Optional

from .cli_base import CliAdapter, CliOperation, is_safe_env_key, is_safe_value
from .registry import (
    CAP_TF_APPLY,
    CAP_TF_DESTROY,
    CAP_TF_FMT,
    CAP_TF_INIT,
    CAP_TF_OUTPUT,
    CAP_TF_PLAN,
    CAP_TF_STATE,
    CAP_TF_VALIDATE,
)


def _validate_dir(args: dict[str, Any]) -> Optional[tuple[str, str]]:
    for field_name in ("dir", "stateFile", "varFile", "target"):
        if args.get(field_name) is not None and not is_safe_value(str(args[field_name])):
            return ("INVALID_ARG", f"{field_name!r} contains an unsafe value")
    for key in (args.get("vars") or {}):
        if not is_safe_env_key(str(key)):
            return ("INVALID_ARG", "'vars' has an invalid key")
    return None


def _validate_destroy(args: dict[str, Any]) -> Optional[tuple[str, str]]:
    # `destroy` is only meaningful with an explicit confirmation flag; the runtime
    # policy still gates it. A target must be safe when present.
    refusal = _validate_dir(args)
    if refusal:
        return refusal
    return None


class TerraformAdapter(CliAdapter):
    """`terraform` with a closed operation table."""

    kind = "infrastructure"
    name = "terraform"
    binary = "terraform"
    aliases = ("tf",)
    capabilities = frozenset(
        {CAP_TF_INIT, CAP_TF_VALIDATE, CAP_TF_FMT, CAP_TF_PLAN, CAP_TF_APPLY,
         CAP_TF_DESTROY, CAP_TF_OUTPUT, CAP_TF_STATE}
    )

    def _chdir(self, args: dict[str, Any]) -> list[str]:
        directory = str(args.get("dir") or ".")
        # Terraform wants `-chdir=DIR` BEFORE the subcommand. The adapter builds
        # `[exe, *subcommand, *argv]`, so the subcommand is emitted from argv here
        # and the operation's `subcommand` stays empty.
        return ["-chdir", directory] if directory and directory != "." else []

    def _vars(self, args: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for key, value in (args.get("vars") or {}).items():
            out += ["-var", f"{key}={value}"]
        return out

    operations: dict[str, CliOperation] = {}

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # NOTE: every terraform operation carries its subcommand IN argv (not in
        # `subcommand`) so `-chdir` lands before it.
        self.operations = {
            "version": CliOperation(name="version", subcommand=("version",), risk="SAFE", timeout_s=15,
                                    json_output=("-json",), json_parse=True, read_only=True),
            "init": CliOperation(
                name="init",
                argv=lambda a: [*self._chdir(a), "init", "-input=false",
                                *(["-upgrade"] if a.get("upgrade") else []),
                                *(["-reconfigure"] if a.get("reconfigure") else [])],
                validator=_validate_dir, risk="MEDIUM", timeout_s=300,
            ),
            "validate": CliOperation(
                name="validate",
                argv=lambda a: [*self._chdir(a), "validate", "-json"],
                validator=_validate_dir, json_parse=True, risk="LOW", timeout_s=120, read_only=True,
            ),
            "fmt": CliOperation(
                name="fmt",
                argv=lambda a: [*self._chdir(a), "fmt",
                                *(["-check"] if a.get("check") else []),
                                *(["-recursive"] if a.get("recursive") else [])],
                validator=_validate_dir, risk="LOW", timeout_s=120,
            ),
            "plan": CliOperation(
                name="plan",
                argv=lambda a: [*self._chdir(a), "plan", "-input=false", "-no-color",
                                *(["-out", str(a["out"])] if a.get("out") else []),
                                *(["-destroy"] if a.get("destroy") else []),
                                *(["-target", str(a["target"])] if a.get("target") else []),
                                *self._vars(a)],
                validator=_validate_dir, risk="LOW", timeout_s=600, read_only=True,
            ),
            "apply": CliOperation(
                name="apply",
                argv=lambda a: [*self._chdir(a), "apply", "-input=false", "-no-color",
                                *(["-auto-approve"] if a.get("autoApprove") else []),
                                *([str(a["planFile"])] if a.get("planFile") else []),
                                *(["-target", str(a["target"])] if a.get("target") else []),
                                *self._vars(a)],
                validator=_validate_dir, risk="CRITICAL", timeout_s=3600,
            ),
            "destroy": CliOperation(
                name="destroy",
                argv=lambda a: [*self._chdir(a), "destroy", "-input=false", "-no-color",
                                *(["-auto-approve"] if a.get("autoApprove") else []),
                                *(["-target", str(a["target"])] if a.get("target") else []),
                                *self._vars(a)],
                validator=_validate_destroy, risk="CRITICAL", timeout_s=3600,
            ),
            "output": CliOperation(
                name="output",
                argv=lambda a: [*self._chdir(a), "output", "-json",
                                *([str(a["name"])] if a.get("name") else [])],
                validator=_validate_dir, json_parse=True, risk="LOW", timeout_s=60, read_only=True,
            ),
            "show": CliOperation(
                name="show",
                argv=lambda a: [*self._chdir(a), "show", "-json",
                                *([str(a["planFile"])] if a.get("planFile") else [])],
                validator=_validate_dir, json_parse=True, risk="LOW", timeout_s=60, read_only=True,
            ),
            "state": CliOperation(
                name="state",
                argv=lambda a: [*self._chdir(a), "state", "list"],
                validator=_validate_dir, risk="LOW", timeout_s=60, read_only=True,
            ),
        }


def build_infrastructure_adapters() -> list[CliAdapter]:
    return [TerraformAdapter()]


__all__ = ["TerraformAdapter", "build_infrastructure_adapters"]

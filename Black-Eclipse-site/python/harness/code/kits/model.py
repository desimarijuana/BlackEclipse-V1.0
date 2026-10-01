"""The kit contract (Phase 9 §6.1) — a small, validated, reviewable manifest.

Mirrors the discipline of `skills/manifest.py`: pydantic validation (already a
dependency via LangChain), a closed `produces` list, and a required acceptance
test. A kit without its acceptance test, or with an undeclared output, does not
load.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

InputKind = Literal["identifier", "text", "choice", "boolean", "integer"]

# A declared output path is a repo-relative POSIX path (it may carry a
# `{{placeholder}}` token substituted at render time). It may not be absolute and
# may not traverse.
_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/{}-]*$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class KitInput(BaseModel):
    """One thing the user answers to fill the kit. Carries a prompt_key (i18n)."""

    model_config = _CAMEL

    name: str = Field(..., min_length=1, max_length=64)
    kind: InputKind = "text"
    prompt_key: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    choices: list[str] = Field(default_factory=list)
    required: bool = True

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError("an input name must be a lowercase slug")
        return value

    @model_validator(mode="after")
    def _choices_for_choice(self) -> "KitInput":
        if self.kind == "choice" and not self.choices:
            raise ValueError(f"choice input {self.name!r} needs choices")
        return self


class KitCheck(BaseModel):
    """A check the generated instance must pass. A command CLASS, never a shell."""

    model_config = _CAMEL

    command_class: str = Field(..., min_length=1, max_length=64)  # noqa: N815
    args: dict[str, Any] = Field(default_factory=dict)


class KitManifest(BaseModel):
    """The kit manifest. Validated on load; a bad manifest is a load error."""

    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=64)
    version: str = Field("1.0.0", max_length=32)
    title: str = Field(..., min_length=1, max_length=200)
    summary_key: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    produces: list[str] = Field(..., min_length=1, max_length=64)
    requires_inputs: list[KitInput] = Field(default_factory=list)
    conventions: list[str] = Field(default_factory=list)
    # `checks` runs through the Phase 3 command broker AFTER scaffolding. A kit
    # whose verification is instead its shipped acceptance test (run by the test
    # suite) may declare none — the required `acceptance` string and the
    # acceptance-test file are the guarantee, not this list.
    checks: list[KitCheck] = Field(default_factory=list, max_length=16)
    acceptance: str = Field(..., min_length=1, max_length=2000)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError("a kit id must be a lowercase slug (letters, digits, _)")
        return value

    @field_validator("produces")
    @classmethod
    def _valid_produces(cls, value: list[str]) -> list[str]:
        for path in value:
            if path.startswith("/") or "\\" in path or ".." in path.split("/"):
                raise ValueError(f"a declared output {path!r} is not a safe relative path")
            if not _PATH_RE.match(path):
                raise ValueError(f"a declared output {path!r} is not a valid path")
        if len(set(value)) != len(value):
            raise ValueError("declared outputs must be unique")
        return value

    @property
    def inputs(self) -> list[KitInput]:
        return self.requires_inputs

    def public(self) -> dict[str, Any]:
        """The secret-free view for the API/UI (questions are i18n keys)."""
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "summaryKey": self.summary_key,
            "produces": list(self.produces),
            "inputs": [
                {
                    "name": i.name, "kind": i.kind, "promptKey": i.prompt_key,
                    "choices": list(i.choices), "required": i.required,
                }
                for i in self.requires_inputs
            ],
            "conventions": list(self.conventions),
            "checks": [c.model_dump(by_alias=True) for c in self.checks],
            "acceptance": self.acceptance,
        }


__all__ = ["KitCheck", "KitInput", "KitManifest", "InputKind"]

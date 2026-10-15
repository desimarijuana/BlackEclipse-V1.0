"""The chat command marker on RunRequest (`/eclipsesdk`).

A recognized chat command (`command="eclipsesdk"`) forces the run's profile at
the front door. The runtime accepts the marker (additive, optional) and never
treats a command turn as trivial. This is the contract test for the schema half.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.schemas import ModelSettings, RunInput, RunRequest


def _request(**overrides: object) -> RunRequest:
    base: dict[str, object] = {
        "runId": "run_cmd",
        "input": RunInput(query="create a page"),
        "agentId": "eclipse-agent",
        "autonomy": "edit_verify",
        "modelSettings": ModelSettings(
            provider="ollama", model="m", base_url="http://localhost:11434/v1",
        ),
        "callbackBaseUrl": "http://localhost:3000",
    }
    base.update(overrides)
    return RunRequest(**base)  # type: ignore[arg-type]


def test_command_is_accepted_and_optional() -> None:
    assert _request(command="eclipsesdk").command == "eclipsesdk"
    assert _request().command is None


def test_command_round_trips_through_a_dump() -> None:
    dumped = _request(command="eclipsesdk").model_dump()
    assert dumped["command"] == "eclipsesdk"
    assert RunRequest(**dumped).command == "eclipsesdk"


def test_a_non_string_command_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(command=123)


def test_the_front_door_may_omit_the_command_field_entirely() -> None:
    # An older client that never sends `command` must still validate.
    payload = _request().model_dump()
    payload.pop("command")
    assert RunRequest(**payload).command is None

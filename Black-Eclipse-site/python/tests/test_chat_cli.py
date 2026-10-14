"""Headless one-shot chat (`eclipse chat -z`) — wiring, not a live model."""

from __future__ import annotations

import json


class _Result:
    def model_dump(self) -> dict:
        return {"runId": "r-1", "status": "completed", "output": "Forty-two.", "error": None}


class _Failing:
    def model_dump(self) -> dict:
        return {"runId": "r-2", "status": "failed", "output": "", "error": "provider unreachable"}


class _Service:
    def __init__(self, result) -> None:
        self._result = result
        self.seen: list[dict] = []

    async def run(self, request):
        self.seen.append({"query": request.input.query, "agent": request.agentId})
        return self._result


def _patch(monkeypatch, service):
    monkeypatch.setattr("harness.deps.service", service, raising=False)


def test_run_once_uses_the_shared_runtime(monkeypatch):
    from harness import chat_cli

    service = _Service(_Result())
    _patch(monkeypatch, service)
    result = chat_cli._run_once("what is six times seven?", agent_id="eclipse-agent")
    assert result["success"] is True
    assert result["output"] == "Forty-two."
    assert service.seen == [{"query": "what is six times seven?", "agent": "eclipse-agent"}]


def test_run_cli_z_flag_prints_the_answer(monkeypatch, capsys):
    from harness import chat_cli

    _patch(monkeypatch, _Service(_Result()))
    assert chat_cli.run_cli(["-z", "hi"]) == 0
    assert "Forty-two." in capsys.readouterr().out


def test_run_cli_positional_and_json(monkeypatch, capsys):
    from harness import chat_cli

    _patch(monkeypatch, _Service(_Result()))
    assert chat_cli.run_cli(["hi", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["output"] == "Forty-two."


def test_run_cli_missing_question_and_failed_run(monkeypatch, capsys):
    from harness import chat_cli

    assert chat_cli.run_cli([]) == 2

    _patch(monkeypatch, _Service(_Failing()))
    assert chat_cli.run_cli(["-z", "hi"]) == 1
    assert "provider unreachable" in capsys.readouterr().err

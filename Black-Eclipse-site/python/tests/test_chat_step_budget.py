"""Chat step budget (QA Round 1, Q5).

8 model steps was too tight for a multi-tool navigation turn; the QA run hit the
cap mid-task. Ordinary chat now defaults to 12, an operator can set
`ECLIPSE_CHAT_MAX_STEPS` (1..32), and an explicit per-run agent config wins.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.agents import CODE_AGENT, ECLIPSE_AGENT
from harness.graph import chat_step_budget


def _req(explicit=None):
    return SimpleNamespace(agent=explicit)


def test_default_chat_budget_is_twelve(monkeypatch):
    monkeypatch.delenv("ECLIPSE_CHAT_MAX_STEPS", raising=False)
    assert chat_step_budget(ECLIPSE_AGENT, _req()) == 12


def test_env_override_and_clamp(monkeypatch):
    monkeypatch.setenv("ECLIPSE_CHAT_MAX_STEPS", "20")
    assert chat_step_budget(ECLIPSE_AGENT, _req()) == 20
    monkeypatch.setenv("ECLIPSE_CHAT_MAX_STEPS", "999")
    assert chat_step_budget(ECLIPSE_AGENT, _req()) == 32
    monkeypatch.setenv("ECLIPSE_CHAT_MAX_STEPS", "0")
    assert chat_step_budget(ECLIPSE_AGENT, _req()) == 1


def test_invalid_env_is_ignored(monkeypatch):
    monkeypatch.setenv("ECLIPSE_CHAT_MAX_STEPS", "not-a-number")
    assert chat_step_budget(ECLIPSE_AGENT, _req()) == 12


def test_explicit_agent_config_wins(monkeypatch):
    monkeypatch.setenv("ECLIPSE_CHAT_MAX_STEPS", "20")
    explicit = ECLIPSE_AGENT.model_copy(update={"maxSteps": 6})
    assert chat_step_budget(explicit, _req(explicit=explicit)) == 6


def test_other_agents_are_unchanged(monkeypatch):
    monkeypatch.setenv("ECLIPSE_CHAT_MAX_STEPS", "20")
    assert chat_step_budget(CODE_AGENT, _req()) == (CODE_AGENT.maxSteps or 8)

"""The surface-controlled context policy: skill manifest + memory blocks.

A surface may narrow how much CONTEXT the agent receives. It may never grant a
tool, a permission or an effect - these are injection bounds only.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness.graph_context import _memory_context, _skill_manifest_context
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest


class _FakeRegistry:
    def __init__(self, matches):
        self._matches = matches

    def discover(self, query="", include_non_executable=True, **kwargs):
        return self._matches


def _request(query: str = "anything") -> RunRequest:
    return RunRequest(
        runId="run-policy",
        input=RunInput(query=query),
        modelSettings=ModelSettings(provider="ollama", model="m"),
        callbackBaseUrl="http://localhost:3000",
    )


def _agent(**kwargs) -> AgentConfig:
    return AgentConfig(id="eclipse-agent", name="Eclipse", systemPrompt="p", **kwargs)


def _matches(count: int = 10):
    return [
        {"id": f"skill.{i}", "version": "1", "description": "d" * 40}
        for i in range(count)
    ]


def test_the_default_manifest_is_unchanged():
    content, version = asyncio.run(_skill_manifest_context(
        _request(), _FakeRegistry(_matches()),
    ))
    assert content
    assert version


def test_a_surface_can_narrow_the_manifest_to_three():
    content, _version = asyncio.run(_skill_manifest_context(
        _request(), _FakeRegistry(_matches()),
        agent=_agent(skillManifest="top3"),
    ))
    assert content.count("- skill.") == 3


def test_a_surface_can_switch_the_manifest_off():
    content, version = asyncio.run(_skill_manifest_context(
        _request(), _FakeRegistry(_matches()),
        agent=_agent(skillManifest="none"),
    ))
    assert content == ""
    assert version is None


class _FakeMemoryService:
    def __init__(self):
        self.retrieved = 0

    class _Policy:
        @staticmethod
        def get(_key):
            return None

        @staticmethod
        def get_all():
            return {"memory_enabled": True}

    policy = _Policy()

    def retrieve(self, **kwargs):
        self.retrieved += 1
        return SimpleNamespace(
            context="recalled memory",
            memories=[{"id": "m1"}],
            diagnostics={"selected": 1, "candidates": 1},
        )


class _Emitter:
    def __init__(self):
        self.events = []

    async def emit(self, kind, payload):
        self.events.append((kind, payload))


def test_a_surface_can_switch_recalled_memory_off():
    service = _FakeMemoryService()
    block = asyncio.run(_memory_context(
        _request(), service, _Emitter(), agent=_agent(memoryPolicy="off"),
    ))
    assert block == ""
    assert service.retrieved == 0


def test_a_surface_can_keep_the_profile_but_drop_recall():
    service = _FakeMemoryService()
    block = asyncio.run(_memory_context(
        _request(), service, _Emitter(), agent=_agent(memoryPolicy="profile_only"),
    ))
    assert block == ""
    assert service.retrieved == 0


def test_without_a_policy_memory_is_unchanged():
    service = _FakeMemoryService()
    block = asyncio.run(_memory_context(_request(), service, _Emitter()))
    assert block == "recalled memory"
    assert service.retrieved == 1

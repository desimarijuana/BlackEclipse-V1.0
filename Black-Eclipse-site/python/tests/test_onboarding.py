"""Cold-start onboarding (Phase 13): explains, writes nothing, starter content
has visible provenance."""

from __future__ import annotations

from harness.onboarding import ONBOARDING_VERSION, onboarding_content


def test_onboarding_explains_the_three_models():
    content = onboarding_content()
    ids = {step["id"] for step in content["steps"]}
    assert {"facts", "history", "skills"} <= ids
    assert content["version"] == ONBOARDING_VERSION
    assert "does not write memory" in content["note"]


def test_starter_skills_are_bundled_provenance():
    content = onboarding_content(starter_skills=[
        {"id": "research.planning", "name": "Planning", "description": "d", "category": "research"},
    ])
    assert content["starterSkills"][0]["provenance"] == "bundled"


def test_onboarding_does_not_write_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    from harness.eclipse_memory import EclipseMemoryService

    service = EclipseMemoryService()
    before = len(service.store.list_memories(limit=100))
    onboarding_content(starter_skills=[])
    after = len(service.store.list_memories(limit=100))
    assert before == after
    service.close()

"""Defect fix: a bundled kit can actually be PROMOTED.

Before, `registry.load_all` treated bundled skills as unmanaged, so an operator's
enable was silently reset to the manifest's `draft` on the next reload — the
drafting kits could never be promoted. This asserts the enable sticks.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.skills.registry import SkillRegistry

_KIT = "system.portfolio-analysis"


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def test_bundled_kit_promotion_persists_across_reload(service):
    reg = SkillRegistry(service.store)
    reg.load_all()
    manifest = reg.manifest(_KIT)
    assert manifest.status == "draft"

    # An operator promotion recorded in the store must survive a reload — this is
    # exactly what the registry previously walked back to `draft`.
    reg.store.set_version_status(_KIT, manifest.version, "enabled", "passed")

    reg2 = SkillRegistry(service.store)
    reg2.load_all()
    assert reg2.store.get_skill(_KIT)["status"] == "enabled"
    assert reg2.manifest(_KIT).status == "enabled"


def test_bundled_kit_manifest_stays_inert_until_promoted(service):
    # The shipped catalog is still draft by default (inert), independent of the
    # persistence fix.
    reg = SkillRegistry(service.store)
    reg.load_all()
    assert reg.manifest(_KIT).status == "draft"

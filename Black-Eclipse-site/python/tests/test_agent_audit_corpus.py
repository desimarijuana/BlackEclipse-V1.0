"""The versioned audit corpus manifest must stay valid and runnable."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # Black-Eclipse-site/
MANIFEST = ROOT / "python/harness/evaluation/corpus/agent_audit_v1.json"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_has_a_version_and_unique_checks():
    data = _manifest()
    assert data["id"] == "agent-audit"
    assert int(data["version"]) >= 1
    checks = data["checks"]
    ids = [check["id"] for check in checks]
    assert len(ids) == len(set(ids))
    assert len(checks) >= 9


def test_every_manifest_test_file_exists():
    data = _manifest()
    missing = [check["test"] for check in data["checks"] if not (ROOT / check["test"]).exists()]
    assert missing == []


def test_every_check_names_its_area_and_evidence():
    for check in _manifest()["checks"]:
        assert check.get("area")
        assert check.get("evidence")
        assert check["test"].endswith(".py")

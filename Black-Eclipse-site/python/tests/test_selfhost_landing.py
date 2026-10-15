"""Track B — self-hosting safety: classify a landing and guard it.

Pure and injectable: the runtime restart is a seam, so the apply → restart →
verify → rollback policy is tested without a live process.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.code import selfhost
from harness.code.selfhost import SelfHostError, classify_landing, guarded_land


# ── classification ────────────────────────────────────────────────────────────

def test_runtime_path_needs_a_restart() -> None:
    v = classify_landing(["python/harness/code/promotion.py"])
    assert v.restartRequired is True and v.buildRequired is False and not v.refused


def test_frontend_path_needs_a_build() -> None:
    v = classify_landing(["src/components/chat/chat-input.tsx"])
    assert v.buildRequired is True and v.restartRequired is False


def test_docs_path_needs_neither() -> None:
    v = classify_landing(["docs/CHANGELOG.md"])
    assert v.restartRequired is False and v.buildRequired is False and not v.refused


def test_an_authority_path_is_refused() -> None:
    v = classify_landing(["python/harness/code/authorizers.py"])
    assert v.refused is True
    assert "python/harness/code/authorizers.py" in v.authorities
    assert v.restartRequired is True  # it is also runtime code


def test_mixed_set_is_classified() -> None:
    v = classify_landing(["src/app/x/page.tsx", "python/harness/x.py", "docs/a.md"])
    assert v.restartRequired and v.buildRequired and not v.refused


def test_paths_are_normalized() -> None:
    assert classify_landing([".\\python\\harness\\x.py"]).restartRequired is True
    assert classify_landing(["./src/x.ts"]).buildRequired is True


def test_verdict_to_dict_is_the_wire_shape() -> None:
    d = classify_landing(["python/harness/code/policy.py"]).to_dict()
    assert d["restartRequired"] is True and d["buildRequired"] is False
    assert d["authorities"] == ["python/harness/code/policy.py"]


# ── guarded_land ──────────────────────────────────────────────────────────────

def _preview(paths: list[str]) -> dict[str, Any]:
    return {"files": [{"path": p, "op": "overwrite"} for p in paths],
            "previewDigest": "digest1", "workspaceId": "ws1"}


class _Fakes:
    def __init__(self, *, healthy: bool = True, rollback_id: str = "rb1", verify_raises: bool = False) -> None:
        self.applied: list[dict[str, Any]] = []
        self.restarted = 0
        self.rolled_back: list[str] = []
        self.verified = 0
        self._healthy = healthy
        self._rollback_id = rollback_id
        self._verify_raises = verify_raises

    def apply(self, preview: dict[str, Any]) -> dict[str, Any]:
        self.applied.append(preview)
        return {"ok": True, "filesChanged": len(preview["files"]), "rollbackId": self._rollback_id}

    def rollback(self, rollback_id: str) -> dict[str, Any]:
        self.rolled_back.append(rollback_id)
        return {"ok": True}

    def restart(self) -> None:
        self.restarted += 1

    def verify(self) -> bool:
        self.verified += 1
        if self._verify_raises:
            raise RuntimeError("probe down")
        return self._healthy


def test_a_non_runtime_change_is_a_plain_apply() -> None:
    f = _Fakes()
    out = guarded_land(_preview(["docs/a.md"]), apply=f.apply, restart=f.restart)
    assert out["ok"] is True and out["restartRequired"] is False and out["verified"] is False
    assert f.restarted == 0 and len(f.applied) == 1


def test_a_runtime_change_restarts_then_verifies() -> None:
    f = _Fakes(healthy=True)
    out = guarded_land(_preview(["python/harness/x.py"]), apply=f.apply, restart=f.restart, verify=f.verify)
    assert out["ok"] is True and out["restartRequired"] is True
    assert f.restarted == 1 and f.verified == 1 and f.rolled_back == []


def test_an_unhealthy_boot_rolls_back_and_refuses() -> None:
    f = _Fakes(healthy=False)
    with pytest.raises(SelfHostError) as exc:
        guarded_land(_preview(["python/harness/x.py"]),
                     apply=f.apply, restart=f.restart, verify=f.verify, rollback=f.rollback)
    assert exc.value.code == "SELFHOST_VERIFY_FAILED"
    assert f.rolled_back == ["rb1"]


def test_a_raising_probe_is_a_failed_verification() -> None:
    f = _Fakes(verify_raises=True)
    with pytest.raises(SelfHostError) as exc:
        guarded_land(_preview(["python/harness/x.py"]),
                     apply=f.apply, restart=f.restart, verify=f.verify, rollback=f.rollback)
    assert exc.value.code == "SELFHOST_VERIFY_FAILED"
    assert f.rolled_back == ["rb1"]


def test_an_authority_change_is_refused_and_never_applied() -> None:
    f = _Fakes()
    with pytest.raises(SelfHostError) as exc:
        guarded_land(_preview(["python/harness/code/authorizers.py"]),
                     apply=f.apply, restart=f.restart, verify=f.verify)
    assert exc.value.code == "SELFHOST_AUTHORITY_REFUSED"
    assert f.applied == [] and f.restarted == 0


def test_an_unhealthy_boot_with_no_rollback_id_still_refuses() -> None:
    f = _Fakes(healthy=False, rollback_id="")
    with pytest.raises(SelfHostError):
        guarded_land(_preview(["python/harness/x.py"]), apply=f.apply, restart=f.restart, verify=f.verify)
    assert f.rolled_back == []


def test_a_frontend_change_can_be_build_verified() -> None:
    f = _Fakes(healthy=True)
    out = guarded_land(_preview(["src/app/page.tsx"]), apply=f.apply, verify=f.verify)
    assert out["buildRequired"] is True and out["verified"] is True
    assert f.restarted == 0  # a frontend change does not restart the Python runtime

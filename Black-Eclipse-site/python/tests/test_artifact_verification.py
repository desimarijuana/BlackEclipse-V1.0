"""Phase 19 G2 — artifact checks are real observations, never claims."""

from __future__ import annotations

import hashlib

from harness.code.execution import ArtifactRef
from harness.code.verify import verify_artifacts


def _ref(path, name: str, media_type: str = "text/csv") -> ArtifactRef:
    data = path.read_bytes() if path.exists() else b""
    return ArtifactRef(
        name=name, path=str(path), sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data), media_type=media_type,
    )


def _checks(records) -> dict[str, bool]:
    return {r.check: r.passed for r in records}


def test_a_clean_artifact_passes_every_check(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("symbol,close\nAAPL,1\nMSFT,2\n", encoding="utf-8")

    records = verify_artifacts([_ref(path, "data.csv")], tmp_path, {"data.csv": {"rows": 2}})
    checks = _checks(records)
    assert checks == {
        "artifact_exists": True, "artifact_digest": True, "artifact_size": True,
        "artifact_readable": True, "figure_inputs_match": True,
    }
    readable = next(r for r in records if r.check == "artifact_readable")
    assert readable.observed.get("rows") == 2


def test_a_missing_file_fails_every_check_with_its_reason(tmp_path):
    missing = ArtifactRef(
        name="gone.csv", path=str(tmp_path / "gone.csv"), sha256="0" * 64,
        bytes=10, media_type="text/csv",
    )
    records = verify_artifacts([missing], tmp_path, None)
    checks = _checks(records)
    assert checks["artifact_exists"] is False
    assert checks["artifact_digest"] is False
    assert checks["artifact_size"] is False
    assert checks["artifact_readable"] is False
    # Every failed record states its reason; the follow-up checks say the file is
    # missing (an omission would be a fabricated pass).
    failed = [r for r in records if not r.passed]
    assert all(r.detail for r in failed)
    assert all("missing" in r.detail for r in failed if r.check != "artifact_exists")


def test_a_changed_digest_fails_the_digest_check(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a\n1\n", encoding="utf-8")
    ref = ArtifactRef(name="data.csv", path=str(path), sha256="f" * 64, bytes=4, media_type="text/csv")
    records = verify_artifacts([ref], tmp_path, None)
    digest = next(r for r in records if r.check == "artifact_digest")
    assert digest.passed is False
    assert "does not match" in digest.detail


def test_a_zero_byte_file_fails_the_size_and_readable_checks(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    records = verify_artifacts([_ref(path, "empty.csv")], tmp_path, None)
    checks = _checks(records)
    assert checks["artifact_size"] is False
    assert checks["artifact_readable"] is False


def test_a_fake_image_fails_the_readable_check(tmp_path):
    path = tmp_path / "chart.png"
    path.write_text("this is not a png", encoding="utf-8")
    records = verify_artifacts([_ref(path, "chart.png", "image/png")], tmp_path, None)
    readable = next(r for r in records if r.check == "artifact_readable")
    assert readable.passed is False
    assert "image" in readable.detail


def test_a_real_png_signature_passes(tmp_path):
    path = tmp_path / "chart.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    records = verify_artifacts([_ref(path, "chart.png", "image/png")], tmp_path, None)
    assert _checks(records)["artifact_readable"] is True


def test_a_series_mismatch_fails_the_inputs_check(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("symbol,close\nAAPL,1\nMSFT,2\n", encoding="utf-8")
    records = verify_artifacts([_ref(path, "data.csv")], tmp_path, {"data.csv": {"rows": 3}})
    match = next(r for r in records if r.check == "figure_inputs_match")
    assert match.passed is False
    assert "3" in match.detail and "2" in match.detail


def test_an_untracked_figure_is_a_failed_check_never_an_absence(tmp_path):
    path = tmp_path / "chart.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    records = verify_artifacts([_ref(path, "chart.png", "image/png")], tmp_path, {})
    match = next(r for r in records if r.check == "figure_inputs_match")
    assert match.passed is False
    assert "not recorded" in match.detail

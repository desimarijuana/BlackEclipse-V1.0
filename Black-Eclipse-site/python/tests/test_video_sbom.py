"""Phase 8 SBOM: the committed bill of materials tracks Cargo.lock EXACTLY.

A dependency bump that forgets to regenerate the SBOM fails here, so the
committed file can never silently describe a different graph than the worker
actually builds. The fframes pin is asserted end-to-end (Cargo.toml pin ==
locked version == SBOM pin).
"""

from __future__ import annotations

import json

import pytest

from harness.video import sbom


def test_committed_sbom_matches_the_lock():
    committed = json.loads(sbom.sbom_path().read_text(encoding="utf-8"))
    regenerated = sbom.generate_from_worker_dir()
    assert committed == regenerated, (
        "SBOM.json is stale — regenerate with `python -m harness.video.sbom`"
    )


def test_fframes_is_exactly_pinned_and_locked():
    toml = (sbom.worker_dir() / "Cargo.toml").read_text(encoding="utf-8")
    assert sbom.parse_fframes_pin(toml) == "=1.2.0"
    document = sbom.generate_from_worker_dir()
    fframes = [package for package in document["packages"] if package["name"] == "fframes"]
    assert len(fframes) == 1
    assert fframes[0]["version"] == "1.2.0"
    assert fframes[0]["checksum"] == "004b1d0fec651ea8c5f62aa5be88696ffeeb6dcf37b194ce5c13b68b188f1016"


def test_every_registry_package_carries_a_checksum():
    for package in sbom.generate_from_worker_dir()["packages"]:
        if str(package.get("source", "")).startswith("registry+"):
            assert package.get("checksum"), package


def test_a_loose_fframes_pin_is_refused():
    with pytest.raises(ValueError, match="exact"):
        sbom.build_sbom("", 'fframes = "1.2.0"\n')


def test_a_pin_that_disagrees_with_the_lock_is_refused():
    toml = (sbom.worker_dir() / "Cargo.toml").read_text(encoding="utf-8")
    lock = (sbom.worker_dir() / "Cargo.lock").read_text(encoding="utf-8")
    tampered = toml.replace('version = "=1.2.0"', 'version = "=9.9.9"')
    assert tampered != toml
    with pytest.raises(ValueError, match="does not match"):
        sbom.build_sbom(lock, tampered)


def test_write_sbom_round_trips_to_an_explicit_path(tmp_path):
    target = sbom.write_sbom(path=tmp_path / "SBOM.json")
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["kind"] == "native-video-worker"
    assert document["packageCount"] == len(document["packages"])
    assert document["worker"]["fframesPin"] == "=1.2.0"
    assert "GPL" in document["licenses"]["ffmpeg"]

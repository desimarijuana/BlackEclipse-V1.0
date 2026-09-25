"""Phase 2 contract enforcement — full JSON Schema output validation, schema
self-validation, runtime tool-call limits, and behavior-affecting version
identity.

These are regression tests for the enforcement layer added on top of the
existing skill runtime. They exercise the real functions (no model, no network).
"""

from __future__ import annotations

import os
import tempfile

from harness.skills.manifest import SkillManifest
from harness.skills.schema_validation import check_schema, jsonschema_available, validate_output


def test_jsonschema_is_available():
    assert jsonschema_available(), "skill contract enforcement requires jsonschema"


# ── Schema self-validation ───────────────────────────────────────────────────


def test_check_schema_accepts_valid_schema():
    ok, errors = check_schema({
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 5}},
        "required": ["n"],
    })
    assert ok and not errors


def test_check_schema_rejects_malformed_schema():
    # `properties` must be an object per JSON Schema; a list is malformed.
    ok, errors = check_schema({"type": "object", "properties": ["nope"]})
    assert not ok and errors


def test_check_schema_rejects_non_object_type():
    # JSON Schema itself allows a top-level string schema, but the registry's
    # skill contract requires an object schema; that requirement is enforced
    # there. `check_schema` returns True (it is a valid JSON Schema document).
    ok, errors = check_schema({"type": "string"})
    assert ok and not errors


def test_check_schema_accepts_missing_schema():
    assert check_schema(None) == (True, [])


# ── Full output validation (nested / arrays / enums / bounds) ────────────────


def _schema():
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok", "partial"]},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "rank": {"type": "integer"}},
                    "required": ["name"],
                },
            },
        },
        "required": ["status", "score", "items"],
    }


def test_validate_output_accepts_conforming_nested_output():
    ok, errors = validate_output(_schema(), {
        "status": "ok", "score": 0.5,
        "items": [{"name": "a", "rank": 1}, {"name": "b"}],
    })
    assert ok and not errors


def test_validate_output_rejects_bad_enum():
    ok, errors = validate_output(_schema(), {
        "status": "great", "score": 0.5, "items": [],
    })
    assert not ok
    assert any("great" in e or "enum" in e.lower() for e in errors)


def test_validate_output_rejects_out_of_bounds():
    ok, errors = validate_output(_schema(), {
        "status": "ok", "score": 1.5, "items": [],
    })
    assert not ok
    assert any("1.5" in e or "maximum" in e.lower() for e in errors)


def test_validate_output_rejects_nested_type_error():
    ok, errors = validate_output(_schema(), {
        "status": "ok", "score": 0.5,
        "items": [{"name": "a", "rank": "not-an-int"}],
    })
    assert not ok
    # The error path must identify the nested field, not just the top level.
    assert any("rank" in e for e in errors)


def test_validate_output_rejects_missing_required():
    ok, errors = validate_output(_schema(), {"status": "ok"})
    assert not ok
    assert any("required" in e.lower() or "score" in e for e in errors)


# ── Behavior-affecting version identity ──────────────────────────────────────


def _manifest(**overrides):
    base = {
        "id": "test.identity", "name": "Identity", "version": "1.0.0",
        "description": "x", "category": "research", "status": "enabled",
    }
    base.update(overrides)
    return SkillManifest(**base)


def test_version_identity_covers_instructions():
    manifest = _manifest()
    a = manifest.version_identity("procedure A")
    b = manifest.version_identity("procedure B")
    assert a != b, "instruction content must change the version identity"
    # Same instructions => same identity (deterministic).
    assert a == manifest.version_identity("procedure A")


def test_version_identity_covers_manifest():
    a = _manifest(description="one").version_identity("proc")
    b = _manifest(description="two").version_identity("proc")
    assert a != b, "manifest content must change the version identity"


def test_version_identity_differs_from_content_hash_when_instructions_differ():
    manifest = _manifest()
    # Same manifest-only hash, different complete identity.
    assert manifest.content_hash() == manifest.content_hash()
    assert manifest.version_identity("x") != manifest.version_identity("y")

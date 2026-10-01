"""Phase 6 G4 — save-time guardrails refuse over-reaching jobs in code.

Every rule is enforced BEFORE persistence. Refusals name the exact cause.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from harness.jobs.guardrails import (
    EXTERNAL_NOT_ALLOWED,
    JobValidationError,
    SKILL_NOT_FOUND,
    SKILL_VERSION_NOT_FOUND,
    UNKNOWN_ADAPTER,
    WATCH_PATH_REFUSED,
    WORKSPACE_REQUIRED,
    validate_job,
)
from harness.jobs.model import JobDefinition, JobDelivery, JobTarget, _CAMEL  # noqa: F401
from harness.persistence import now_iso


class _Manifest:
    def __init__(self, permissions):
        self.permissions = permissions


class _Registry:
    """A stub skill registry. `research.planning` lacks all code permissions."""

    def manifest(self, skill_id):
        if skill_id == "research.planning":
            return _Manifest(["data.read", "research.read", "analysis.execute"])
        return None

    def resolve_version(self, skill_id, version=None):
        if skill_id != "research.planning":
            return None
        if version and version != "1.0.0":
            return None
        return "1.0.0"


def _job(**overrides) -> JobDefinition:
    now = now_iso()
    base = dict(
        id="job_test",
        name="Test job",
        kind="manual",
        target=JobTarget(kind="objective", objective="do a thing"),
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return JobDefinition(**base)


def test_skill_job_without_required_permission_is_refused_naming_it():
    job = _job(
        kind="manual",
        target=JobTarget(
            kind="skill", skill_id="research.planning",
            workspace_root=os.getcwd(), autonomy="edit_verify",
        ),
    )
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == "PERMISSION_NOT_HELD"
    # The named missing permission is one of the profile's code grants.
    assert info.value.missing in ("code.read", "code.write", "code.execute",
                                  "command.execute", "git.read")


def test_code_job_without_workspace_is_refused():
    job = _job(target=JobTarget(kind="objective", objective="x", autonomy="edit_verify"))
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == WORKSPACE_REQUIRED


def test_approve_external_refused_without_operator_flag():
    job = _job(
        target=JobTarget(
            kind="objective", objective="x",
            workspace_root=os.getcwd(), autonomy="approve_external",
        ),
    )
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == EXTERNAL_NOT_ALLOWED


def test_approve_external_allowed_with_operator_flag():
    job = _job(
        target=JobTarget(
            kind="objective", objective="x",
            workspace_root=os.getcwd(), autonomy="approve_external",
        ),
    )
    validated = validate_job(job, skill_registry=_Registry(), allow_external=True)
    assert validated.target.autonomy == "approve_external"


def test_watch_path_outside_workspace_is_refused(tmp_workspace):
    job = _job(
        kind="file_watch",
        watch_path="../../../etc/passwd",
        target=JobTarget(kind="objective", objective="x", workspace_root=str(tmp_workspace)),
    )
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == WATCH_PATH_REFUSED


def test_unknown_delivery_adapter_is_refused():
    # Bypass the Literal so the GUARDRAIL (not pydantic) is what refuses.
    job = _job(delivery=JobDelivery.model_construct(adapter="messaging", title=None))
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == UNKNOWN_ADAPTER


def test_unknown_skill_is_refused():
    job = _job(target=JobTarget(kind="skill", skill_id="nope.missing"))
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == SKILL_NOT_FOUND


def test_unknown_skill_version_is_refused():
    job = _job(
        target=JobTarget(kind="skill", skill_id="research.planning", skill_version="9.9.9")
    )
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == SKILL_VERSION_NOT_FOUND


def test_skill_version_is_pinned_when_absent():
    job = _job(target=JobTarget(kind="skill", skill_id="research.planning"))
    validated = validate_job(job, skill_registry=_Registry())
    assert validated.target.skill_version == "1.0.0"


def test_objective_job_without_objective_is_refused():
    job = _job(target=JobTarget(kind="objective", objective="  "))
    with pytest.raises(JobValidationError) as info:
        validate_job(job, skill_registry=_Registry())
    assert info.value.code == "TARGET_INVALID"

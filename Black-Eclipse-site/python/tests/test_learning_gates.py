"""Phase 3: the learning loop's approval gates are still structurally present."""

from __future__ import annotations

from harness.capabilities.tools import _TOOL_NAMES as CAPABILITY_TOOLS
from harness.skills.lifecycle_tools import (
    LIFECYCLE_TOOLS,
    make_skill_lifecycle_authorizer,
)
from harness.skills.manage_tools import (
    MANAGE_TOOLS,
    make_skill_manage_authorizer,
)


def test_skill_authoring_tools_are_in_the_approval_sets():
    assert {"skill_create", "skill_update", "skill_delete"} <= set(MANAGE_TOOLS)
    assert callable(make_skill_manage_authorizer)


def test_skill_lifecycle_writes_are_in_the_approval_set():
    assert "skill_learning_set" in LIFECYCLE_TOOLS
    assert "skill_version_evaluate" in LIFECYCLE_TOOLS
    assert "skill_version_activate" in LIFECYCLE_TOOLS
    assert callable(make_skill_lifecycle_authorizer)


def test_effectful_capability_activation_requires_operator():
    assert "capability_activate" in CAPABILITY_TOOLS
    import inspect

    from harness.capabilities import builder

    source = inspect.getsource(builder.activate)
    assert "if not operator" in source
    assert "approval_required" in source

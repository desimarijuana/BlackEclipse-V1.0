"""Phase 0 — the code policy is a deliberate, tested decision.

Two things are proven here:

1. The default (and operator) actor is still incapable of every code verb, and
   a workspace-bound actor only holds the verbs its autonomy profile allows.
2. Every policy refusal is path-safe (real-path comparison, symlink escapes
   refused) and every refusal sentence is plain: one sentence, no mechanism
   word from ``PLAIN_LANGUAGE_DENYLIST``, ending in a full stop.

No tool, route or UI is exercised — Phase 0 ships none.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from harness.code.policy import (
    COMMAND_CLASSES,
    PLAIN_LANGUAGE_DENYLIST,
    PROTECTED_PATHS,
    PolicyDecision,
    PolicyDenial,
    WorkspaceBinding,
    code_grants,
    decide_command,
    decide_write,
    is_ignored,
    is_protected,
    resolve_within,
)
from harness.skills.manifest import CODE_PERMISSIONS, FORBIDDEN_PERMISSIONS
from harness.skills.permissions import DEFAULT_ACTOR, OPERATOR_ACTOR, Actor

CODE_VERBS = ("code.read", "code.write", "code.execute",
              "git.read", "git.write", "workspace.admin", "command.execute")


def _binding(root) -> WorkspaceBinding:
    return WorkspaceBinding(id="ws-1", root=root, base_revision="deadbeef", strategy="worktree")


def _actor(autonomy: str | None) -> Actor:
    return Actor(id="coder", operator=False, workspace_id="ws-1", autonomy=autonomy)


# ── The frozen manifest surface ─────────────────────────────────────────────


def test_forbidden_permissions_are_trade_broker_production_only():
    assert set(FORBIDDEN_PERMISSIONS) == {"trade.execute", "broker.modify", "production.modify"}


def test_code_permissions_are_the_seven_declared_nouns():
    assert set(CODE_PERMISSIONS) == set(CODE_VERBS)


# ── The default actor is still denied every code verb ───────────────────────


def test_default_actor_holds_no_code_verb():
    granted = DEFAULT_ACTOR.granted()
    assert not (granted & set(CODE_VERBS))


def test_operator_actor_holds_no_code_verb():
    granted = OPERATOR_ACTOR.granted()
    assert not (granted & set(CODE_VERBS))


def test_workspace_binding_and_autonomy_are_both_required():
    # A workspace alone, or an autonomy alone, is not enough.
    assert not (Actor(id="a", workspace_id="ws-1").granted() & set(CODE_VERBS))
    assert not (Actor(id="a", autonomy="edit_verify").granted() & set(CODE_VERBS))


def test_plan_only_reads_but_never_writes_or_executes():
    granted = _actor("plan_only").granted()
    assert "code.read" in granted and "git.read" in granted
    assert "code.write" not in granted
    assert "code.execute" not in granted
    assert "command.execute" not in granted


def test_edit_verify_can_write_and_execute_but_not_git_write():
    granted = _actor("edit_verify").granted()
    assert {"code.read", "code.write", "code.execute", "command.execute"} <= granted
    assert "git.write" not in granted
    assert "workspace.admin" not in granted


def test_approve_external_holds_git_write_and_workspace_admin():
    granted = _actor("approve_external").granted()
    assert {"git.write", "workspace.admin"} <= granted


def test_unknown_autonomy_grants_nothing():
    assert code_grants("wat") == frozenset()
    assert not (_actor("wat").granted() & set(CODE_VERBS))


def test_operator_cannot_widen_into_code_verbs():
    assert not (Actor(id="op", operator=True, grants=frozenset(CODE_VERBS)).granted() & set(CODE_VERBS))


# ── Protected and ignored paths ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel",
    ["jdds.db", "prisma/migrations/x.sql", ".env", "python/harness/code/policy.py"],
)
def test_is_protected_refuses_the_frozen_paths(rel):
    assert is_protected(rel)


def test_protected_paths_cannot_be_written_even_under_a_workspace(tmp_path):
    binding = _binding(tmp_path)
    for rel in ("jdds.db", "prisma/migrations/001.sql", ".env",
                "python/harness/code/policy.py"):
        decision = decide_write(_actor("approve_external"), binding, rel)
        assert not decision.allowed
        assert decision.code == "PROTECTED_PATH"


def test_is_ignored_refuses_generated_and_generated_dirs():
    assert is_ignored("node_modules/react/index.js")
    assert is_ignored("src/generated/client.ts")
    assert is_ignored("build/app.zip")


def test_decide_write_refuses_an_ignored_path(tmp_path):
    decision = decide_write(_actor("edit_verify"), _binding(tmp_path), "node_modules/x.js")
    assert not decision.allowed


# ── resolve_within: real-path safety ────────────────────────────────────────


def test_resolve_within_returns_real_path_for_a_legal_nested_file(tmp_path):
    nested = tmp_path / "src" / "nested"
    nested.mkdir(parents=True)
    target = nested / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    resolved = resolve_within(tmp_path, "src/nested/app.py")
    assert resolved == target.resolve()
    assert os.path.realpath(resolved) == os.path.realpath(target)


def test_resolve_within_refuses_traversal(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(PolicyDenial) as exc:
        resolve_within(root, "../outside.txt")
    assert exc.value.code == "PATH_TRAVERSAL"


def test_resolve_within_refuses_an_absolute_path_outside_the_root(tmp_path):
    outside = tmp_path / "other" / "file.txt"
    outside.parent.mkdir()
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(PolicyDenial) as exc:
        resolve_within(root, str(outside))
    assert exc.value.code == "PATH_OUTSIDE_WORKSPACE"


def _make_escape_link(link, target) -> bool:
    """Create a directory link at ``link`` → ``target``. A symlink where the
    host allows it, else a Windows junction (no special privilege needed).
    Returns False when the host allows neither."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    return False


def test_resolve_within_refuses_a_link_escape(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("secret", encoding="utf-8")
    root = tmp_path / "ws"
    root.mkdir()
    link = root / "link"
    if not _make_escape_link(link, outside_dir):
        pytest.skip("this host allows neither symlinks nor junctions")
    with pytest.raises(PolicyDenial) as exc:
        resolve_within(root, "link/secret.txt")
    assert exc.value.code == "SYMLINK_ESCAPE"


def test_resolve_within_refuses_a_protected_file(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    with pytest.raises(PolicyDenial) as exc:
        resolve_within(tmp_path, ".env")
    assert exc.value.code == "PROTECTED_PATH"


# ── decide_command: the closed vocabulary ───────────────────────────────────


def test_decide_command_refuses_rm_rf(tmp_path):
    decision = decide_command(_actor("edit_verify"), _binding(tmp_path), "build", ["rm", "-rf", "/"])
    assert not decision.allowed
    assert decision.code == "COMMAND_NOT_ALLOWLISTED"


def test_decide_command_refuses_curl(tmp_path):
    decision = decide_command(_actor("edit_verify"), _binding(tmp_path), "build", ["curl", "http://x"])
    assert not decision.allowed


def test_decide_command_refuses_powershell(tmp_path):
    decision = decide_command(_actor("edit_verify"), _binding(tmp_path), "build", ["powershell", "-c", "whoami"])
    assert not decision.allowed


def test_decide_command_refuses_an_unlisted_class(tmp_path):
    decision = decide_command(_actor("edit_verify"), _binding(tmp_path), "rm_rf", ["npm", "run", "x"])
    assert not decision.allowed
    assert decision.code == "COMMAND_NOT_ALLOWLISTED"


def test_decide_command_allows_typecheck(tmp_path):
    decision = decide_command(_actor("edit_verify"), _binding(tmp_path), "typecheck", ["npm", "run", "typecheck"])
    assert decision.allowed
    assert decision.code == "OK"


def test_decide_command_refuses_without_a_binding(tmp_path):
    decision = decide_command(_actor("edit_verify"), None, "typecheck", ["npm", "run", "typecheck"])
    assert not decision.allowed
    assert decision.code == "SANDBOX_UNAVAILABLE"


def test_decide_command_refuses_a_plan_only_profile(tmp_path):
    decision = decide_command(_actor("plan_only"), _binding(tmp_path), "typecheck", ["npm", "run", "typecheck"])
    assert not decision.allowed
    assert decision.code == "PROFILE_DENIED"


def test_command_classes_are_a_closed_tuple():
    assert isinstance(COMMAND_CLASSES, tuple)
    assert "typecheck" in COMMAND_CLASSES


# ── Plain-language gate (the seed later phases extend) ───────────────────────

_WORD = re.compile(r"[a-z0-9 ]+")
_DENY_WORDS = {term.casefold() for term in PLAIN_LANGUAGE_DENYLIST}


def _refusal_reasons(tmp_path) -> list[str]:
    binding = _binding(tmp_path)
    reasons: list[str] = []
    reasons.append(decide_write(DEFAULT_ACTOR, binding, "src/app.py").reason)
    reasons.append(decide_write(OPERATOR_ACTOR, binding, "src/app.py").reason)
    reasons.append(decide_write(_actor("plan_only"), binding, "src/app.py").reason)
    reasons.append(decide_write(_actor("edit_verify"), binding, "jdds.db").reason)
    reasons.append(decide_write(_actor("edit_verify"), binding, "node_modules/x.js").reason)
    reasons.append(decide_write(_actor("edit_verify"), None, "src/app.py").reason)
    reasons.append(decide_write(_actor("wat"), binding, "src/app.py").reason)
    reasons.append(decide_command(_actor("edit_verify"), binding, "build", ["rm", "-rf", "/"]).reason)
    reasons.append(decide_command(_actor("edit_verify"), binding, "rm_rf", ["npm"]).reason)
    reasons.append(decide_command(_actor("edit_verify"), None, "typecheck", ["npm"]).reason)
    return reasons


def test_plain_language_every_refusal_reason_is_one_sentence(tmp_path):
    for reason in _refusal_reasons(tmp_path):
        assert reason.endswith("."), reason
        # A single sentence: no interior sentence break (a full stop not at end).
        assert "." not in reason[:-1], reason


def test_plain_language_every_refusal_reason_avoids_the_mechanism_denylist(tmp_path):
    for reason in _refusal_reasons(tmp_path):
        words = set(_WORD.findall(reason.casefold()))
        leaked = words & _DENY_WORDS
        # Words of one token are checked directly; multi-word terms are checked
        # as substrings too (e.g. "policy engine").
        assert not leaked, f"{reason!r} leaks {leaked}"
        for term in _DENY_WORDS:
            if " " in term:
                assert term not in reason.casefold(), reason


def test_plain_language_allowed_decision_reasons_are_also_clear(tmp_path):
    binding = _binding(tmp_path)
    for decision in (
        decide_write(_actor("edit_verify"), binding, "src/app.py"),
        decide_command(_actor("edit_verify"), binding, "typecheck", ["npm", "run", "typecheck"]),
    ):
        assert isinstance(decision, PolicyDecision)
        assert decision.allowed and decision.reason.endswith(".")

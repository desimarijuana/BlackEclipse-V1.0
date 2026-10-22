"""Round 3 / W9 (ADR-H297) - the shell sees no secret, and the network is refused.

The defect this file is the gate for: `code/shell.py` handed the real host
shell `dict(os.environ)` - the FULL environment. A single `shell_run` could
read a provider key, the callback token or the vault, and print it into the
conversation, the run blob and the ledger. The sandboxed command path had
been scrubbed since Phase 1; the shell path had not.

The rules this file asserts:

1. A shell sees the SAME environment a sandboxed command sees: the allowlist
   ONLY. The provider keys, the callback token and the vault are absent BY
   CONSTRUCTION - there is nothing to print.
2. Command and shell OUTPUT is redacted before it reaches the model.
3. A network-capable spec is REFUSED by the local tier, by name.
4. The container tier is the only one that CONTAINS the network, and that
   difference is published rather than assumed.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "python"))

SECRETS = (
    "HARNESS_CALLBACK_TOKEN", "CRON_SECRET", "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY", "HARNESS_AUTH_SECRET",
)


def test_the_shell_environment_is_the_allowlist_only() -> None:
    from harness.code.shell import _scrubbed_env

    secret = "super-secret-value-do-not-leak"
    for name in SECRETS:
        os.environ[name] = secret
    try:
        env = _scrubbed_env()
    finally:
        for name in SECRETS:
            os.environ.pop(name, None)
    joined = " ".join(f"{k}={v}" for k, v in env.items())
    assert secret not in joined, "a secret reached the shell's environment"
    for name in SECRETS:
        assert name not in env, f"{name} reached the shell's environment"
    # The environment a shell NEEDS is still there.
    assert "PATH" in env


def test_the_shell_and_a_sandboxed_command_see_the_same_world() -> None:
    from harness.code.sandbox import build_env
    from harness.code.shell import _scrubbed_env

    assert set(_scrubbed_env()) == set(build_env())


def test_command_output_is_redacted_before_it_reaches_the_model() -> None:
    from harness.code.events import redact_output

    text = "fine\napi_key = sk-abcdefghijklmnop12345\npassword: hunter2\n"
    clean, count = redact_output(text)
    assert count == 2, f"expected two redacted lines, got {count}"
    assert "sk-abcdefghijklmnop12345" not in clean
    assert "hunter2" not in clean
    assert "fine" in clean


def test_a_network_capable_spec_is_refused_by_name() -> None:
    from harness.code.sandbox import RunSpec, SandboxUnavailable, run

    with tempfile.TemporaryDirectory(prefix="be-net-") as root:
        spec = RunSpec(
            argv=["echo", "hello"], cwd=__import__("pathlib").Path(root), env={},
            timeout_s=5, output_cap_bytes=1024, network=True,
        )
        with pytest.raises(SandboxUnavailable) as excinfo:
            run(spec)
    assert getattr(excinfo.value, "code", "") == "NETWORK_DENIED"


def test_the_network_refusal_is_distinct_from_a_missing_sandbox() -> None:
    """A caller must be able to tell the two apart."""
    from harness.code.sandbox import SandboxUnavailable

    plain = SandboxUnavailable("no sandbox primitive here")
    named = SandboxUnavailable("the local runner cannot keep a network-capable kernel contained",
                               code="NETWORK_DENIED")
    assert plain.code == "SANDBOX_UNAVAILABLE"
    assert named.code == "NETWORK_DENIED"
    assert plain.code != named.code


def test_the_new_safety_cases_are_attacked_against_the_real_modules() -> None:
    from harness.code.eval.safety import run_case
    from harness.code.eval.safety_cases import EXPECTED_CODES, case as get_case

    for case_id in ("S15-network-enforced", "S16-shell-env-scrubbed"):
        result = run_case(get_case(case_id))
        assert result.passed, f"{case_id} did not hold: {result.detail}"
        assert result.code == EXPECTED_CODES[case_id]

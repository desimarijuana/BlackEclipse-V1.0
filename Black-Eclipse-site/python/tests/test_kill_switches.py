"""W0: every feature flag must have a resolvable kill switch.

This is a contract test, not a path test: W1–W7 add the path assertions as the
features land. It prevents a flag from being introduced with only an "on"
value and no way back.
"""

from __future__ import annotations

import pytest

from harness.config import flags


BOOL_FLAGS = [name for name, spec in flags.FLAG_SPECS.items() if spec.kind == "bool"]
ENUM_FLAGS = [name for name, spec in flags.FLAG_SPECS.items() if spec.kind == "enum"]


@pytest.mark.parametrize("name", BOOL_FLAGS)
def test_boolean_flag_has_off_kill_switch(name):
    assert flags.get_bool(name, environ={name: "off"}) is False


@pytest.mark.parametrize("name", ENUM_FLAGS)
def test_enum_flag_has_off_or_explicit_kill_switch(name):
    spec = flags.FLAG_SPECS[name]
    assert "off" in spec.values or "dry_run" in spec.values


def test_int_flags_are_bounded_so_1_is_a_serial_or_minimum_switch():
    for name, spec in flags.FLAG_SPECS.items():
        if spec.kind != "int":
            continue
        assert spec.minimum is not None
        assert spec.maximum is not None
        assert flags.get_int(name, environ={name: str(spec.minimum)}) == spec.minimum


def test_there_is_no_flag_with_a_secret_like_default():
    for name, spec in flags.FLAG_SPECS.items():
        assert len(spec.default) <= 64, name
        assert "sk-" not in spec.default.lower(), name
        assert "bearer " not in spec.default.lower(), name

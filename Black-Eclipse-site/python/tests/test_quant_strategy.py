"""Unit tests for the strategy contract: parsing, validation, versioning."""

from __future__ import annotations

import pytest

from harness.quant import strategy as S

MISSION_YAML = """
strategy:
  id: blackastro_sd_v1
  name: BlackAstro Supply Demand
  version: 1.0.0
universe:
  asset_classes: [crypto]
  symbols: [BTC-USD, ETH-USD]
timeframes:
  primary: 1m
  confirmation: [5m, 15m]
indicators:
  ema:
    - period: 50
    - period: 200
  atr:
    - period: 14
rules:
  entry:
    long:
      - left: {ref: close}
        op: ">"
        right: {ref: ema_50}
      - left: {ref: ema_50}
        op: ">"
        right: {ref: ema_200}
  exit:
    stop_loss: {type: atr, value: 2}
    take_profit: {type: risk_reward, value: 2.0}
risk:
  position_sizing: {type: percent_equity, value: 1}
"""


def test_parse_mission_shorthand():
    spec = S.parse_strategy(MISSION_YAML)
    assert spec.id == "blackastro_sd_v1"
    assert spec.universe.symbols == ["BTC-USD", "ETH-USD"]
    assert [d.type for d in spec.indicators] == ["ema", "ema", "atr"]
    assert spec.position_sizing.type == "percent_equity"
    assert S.errors_only(S.validate_strategy(spec)) == []


def test_validation_unknown_reference():
    spec = S.parse_strategy({
        "id": "x", "name": "x", "universe": {"symbols": ["A"]},
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "nope"}, "op": ">", "right": {"value": 1}}]}}},
    })
    codes = {i.code for i in S.validate_strategy(spec)}
    assert "UNKNOWN_REFERENCE" in codes


def test_validation_no_entry_rules():
    spec = S.parse_strategy({"id": "x", "name": "x", "universe": {"symbols": ["A"]},
                             "rules": {"exit": {}}})
    codes = {i.code for i in S.validate_strategy(spec)}
    assert "NO_ENTRY_RULES" in codes


def test_validation_require_stop():
    spec = S.parse_strategy({
        "id": "x", "name": "x", "universe": {"symbols": ["A"]},
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"value": 1}}]}}},
        "risk": {"require_stop": True},
    })
    codes = {i.code for i in S.validate_strategy(spec)}
    assert "STOP_REQUIRED" in codes


def test_validation_confirmation_must_be_higher():
    spec = S.parse_strategy({
        "id": "x", "name": "x", "universe": {"symbols": ["A"]},
        "timeframes": {"primary": "1h", "confirmation": ["5m"]},
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"value": 1}}]}}},
    })
    codes = {i.code for i in S.validate_strategy(spec)}
    assert "CONFIRMATION_NOT_HIGHER" in codes


def test_semver_bump():
    assert S.bump_version("1.2.3", "patch") == "1.2.4"
    assert S.bump_version("1.2.3", "minor") == "1.3.0"
    assert S.bump_version("1.2.3", "major") == "2.0.0"


def test_roundtrip_serialization():
    spec = S.parse_strategy(MISSION_YAML)
    restored = S.parse_strategy(spec.to_json())
    assert restored.to_dict() == spec.to_dict()
    assert S.parse_strategy(spec.to_yaml()).id == spec.id

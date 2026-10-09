"""Audit anchoring — append-only JSONL sink with an HMAC-signed head."""

from __future__ import annotations

import json
import os
import tempfile

from harness.security.audit import AuditSink


def _sink():
    path = os.path.join(tempfile.mkdtemp(prefix="be-sec-sink-"), "audit.log")
    return AuditSink(path, key="test-key")


def test_sink_grows_and_verifies():
    sink = _sink()
    assert sink.verify()["valid"] is True
    for i in range(5):
        sink.append({"id": f"e{i}", "decision": "allow", "action": "filesystem.read"})
    result = sink.verify()
    assert result["valid"] is True
    assert result["checked"] == 5


def test_sink_detects_tampering_with_a_line():
    sink = _sink()
    for i in range(4):
        sink.append({"id": f"e{i}", "decision": "deny"})
    # Out-of-band edit of the log file breaks the signed head.
    with open(sink.path, "r+", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
        lines[1] = lines[1].replace('"deny"', '"allow"')
        handle.seek(0)
        handle.write("\n".join(lines) + "\n")
        handle.truncate()
    assert sink.verify()["valid"] is False


def test_sink_head_is_signed():
    sink = _sink()
    sink.append({"id": "x", "decision": "allow"})
    with open(sink.head_path, encoding="utf-8") as handle:
        head = json.load(handle)
    assert head["count"] == 1
    assert len(head["sig"]) == 64

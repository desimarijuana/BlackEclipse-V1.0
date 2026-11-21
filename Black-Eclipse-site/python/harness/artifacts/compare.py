"""Deterministic comparison between two immutable artifact revisions.

`artifacts` already stores every revision (`ArtifactVersion`) with a checksum,
size, metadata and provenance. What was missing is the *question a reader
actually asks*: "what changed between these two?" This module answers it from
the stored records only — it never recomputes a metric and never pretends to
diff bytes it did not read.

Scope, stated honestly:

  * Bytes are compared by **checksum and size**, not by content. A checksum
    change means "the bytes differ"; it does not say how. Reading and diffing
    the stored blob is deliberately out of scope (a URL/PDF/binary has no
    meaningful line diff, and the blob may be large).
  * Provenance (`created_by`, `agent_id`, `task_id`, `run_id`), `change_note`
    and `mime_type` are compared as scalar fields.
  * `metadata` is compared key-by-key into added / removed / changed.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

#: Metadata keys whose values may be long; the report keeps them bounded.
MAX_VALUE_CHARS = 300


def _get(version: Any, name: str) -> Any:
    if isinstance(version, Mapping):
        for key in (name, _camel(name)):
            if key in version:
                return version[key]
        return None
    return getattr(version, name, None)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _bound(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if len(text) <= MAX_VALUE_CHARS:
        return text
    marker = "..."
    return text[: MAX_VALUE_CHARS - len(marker)] + marker


def compare_versions(left: Any, right: Any) -> dict[str, Any]:
    """A deterministic report of what changed from `left` to `right`.

    Accepts `ArtifactVersion` models or their dict forms, so a caller can diff a
    stored revision against a payload without a database round-trip.
    """
    left_meta = dict(_get(left, "metadata") or {})
    right_meta = dict(_get(right, "metadata") or {})
    added = sorted(set(right_meta) - set(left_meta))
    removed = sorted(set(left_meta) - set(right_meta))
    changed = sorted(
        key for key in set(left_meta) & set(right_meta)
        if left_meta[key] != right_meta[key]
    )

    def scalar(name: str) -> dict[str, Any]:
        before, after = _get(left, name), _get(right, name)
        return {"from": _bound(before), "to": _bound(after), "changed": before != after}

    left_size = _get(left, "size_bytes")
    right_size = _get(right, "size_bytes")
    size_delta = None
    if isinstance(left_size, int) and isinstance(right_size, int):
        size_delta = right_size - left_size

    left_sha = _get(left, "checksum")
    right_sha = _get(right, "checksum")
    checksum_changed = left_sha != right_sha

    provenance = {
        name: scalar(name)
        for name in ("created_by", "agent_id", "task_id", "run_id")
    }
    fields = {
        name: scalar(name)
        for name in ("mime_type", "change_note")
    }

    any_change = bool(
        checksum_changed
        or size_delta not in (None, 0)
        or added or removed or changed
        or any(item["changed"] for item in provenance.values())
        or any(item["changed"] for item in fields.values())
    )

    return {
        "artifactId": _get(left, "artifact_id") or _get(right, "artifact_id"),
        "fromVersion": _get(left, "version_number"),
        "toVersion": _get(right, "version_number"),
        "changed": any_change,
        "bytes": {
            "checksumChanged": checksum_changed,
            "sizeDeltaBytes": size_delta,
        },
        "provenance": provenance,
        "fields": fields,
        "metadata": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "addedValues": {key: _bound(right_meta[key]) for key in added},
            "removedValues": {key: _bound(left_meta[key]) for key in removed},
            "changedValues": {
                key: {"from": _bound(left_meta[key]), "to": _bound(right_meta[key])}
                for key in changed
            },
        },
    }


def compare_revisions(
    store: Any, artifact_id: str, from_version: int, to_version: int,
) -> Optional[dict[str, Any]]:
    """Diff two stored revisions. `None` when either one does not exist."""
    left = store.get_version(artifact_id, int(from_version))
    right = store.get_version(artifact_id, int(to_version))
    if left is None or right is None:
        return None
    return compare_versions(left, right)


def to_markdown(report: Mapping[str, Any]) -> str:
    """A compact, deterministic Markdown rendering of a comparison report."""
    lines = [
        f"# Artifact {report.get('artifactId')} — version "
        f"{report.get('fromVersion')} → {report.get('toVersion')}",
        "",
        f"- Changed: **{str(bool(report.get('changed'))).lower()}**",
    ]
    bytes_info = report.get("bytes") or {}
    if bytes_info.get("checksumChanged"):
        lines.append("- Bytes: checksum changed")
    delta = bytes_info.get("sizeDeltaBytes")
    if delta is not None:
        lines.append(f"- Size: {delta:+d} bytes" if delta else "- Size: unchanged")
    for group in ("provenance", "fields"):
        for name, item in (report.get(group) or {}).items():
            if item.get("changed"):
                lines.append(f"- {name}: `{item.get('from')}` → `{item.get('to')}`")
    meta = report.get("metadata") or {}
    if meta.get("added"):
        lines.append(f"- Metadata added: {', '.join(meta['added'])}")
    if meta.get("removed"):
        lines.append(f"- Metadata removed: {', '.join(meta['removed'])}")
    if meta.get("changed"):
        lines.append(f"- Metadata changed: {', '.join(meta['changed'])}")
    if not report.get("changed"):
        lines.append("- No difference in the stored record.")
    return "\n".join(lines) + "\n"


__all__ = ["compare_revisions", "compare_versions", "to_markdown"]

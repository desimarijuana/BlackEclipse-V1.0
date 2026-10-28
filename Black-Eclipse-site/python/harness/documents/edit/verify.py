"""Proof that an edit preserved the package.

The report is not decorative: a publish is refused when an untouched part
changed, a part disappeared, a relationship points at nothing, or an expected
edit is missing from the output.
"""

from __future__ import annotations

from typing import Any, Optional

from .package import OoxmlPackage, sha256_hex
from .xmlutil import attr, iter_local, local, parse

CONTENT_TYPES = "[Content_Types].xml"


def _resolve(base_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    directory = base_part.rpartition("/")[0]
    stack = directory.split("/") if directory else []
    for piece in target.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if stack:
                stack.pop()
        else:
            stack.append(piece)
    return "/".join(stack)


def _content_types(package: OoxmlPackage) -> tuple[set[str], set[str]]:
    raw = package.read(CONTENT_TYPES)
    if raw is None:
        return set(), set()
    root = parse(raw)
    defaults = {
        attr(element, "Extension").casefold()
        for element in iter_local(root, "Default")
        if attr(element, "Extension")
    }
    overrides = {
        attr(element, "PartName").lstrip("/").casefold()
        for element in iter_local(root, "Override")
        if attr(element, "PartName")
    }
    return defaults, overrides


def _relationship_gaps(package: OoxmlPackage) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for name in package.names:
        if not name.endswith(".rels"):
            continue
        root = parse(package.require(name))
        base = name.replace("_rels/", "").removesuffix(".rels")
        for relation in iter_local(root, "Relationship"):
            if attr(relation, "TargetMode").casefold() == "external":
                continue
            target = attr(relation, "Target")
            if not target:
                continue
            resolved = _resolve(base, target)
            if not package.has(resolved):
                gaps.append({"part": name, "target": target, "resolved": resolved})
    return gaps


def verify_ooxml(
    source_hashes: dict[str, str],
    output: OoxmlPackage,
    targeted: set[str],
    *,
    expected: Optional[dict[str, list[str]]] = None,
    allowed_removals: Optional[set[str]] = None,
) -> dict[str, Any]:
    output_hashes = output.part_hashes()
    source_parts = set(source_hashes)
    output_parts = set(output_hashes)
    removals = set(allowed_removals or set())

    removed_parts = sorted(source_parts - output_parts)
    missing_parts = sorted(source_parts - output_parts - removals)
    new_parts = sorted(output_parts - source_parts)
    unchanged = source_parts & output_parts
    changed = sorted(name for name in unchanged if source_hashes[name] != output_hashes[name])
    untouched_changed = sorted(name for name in changed if name not in targeted)
    missing_targets = sorted(name for name in targeted if name not in output_parts and name not in removals)
    unexpected_new = sorted(name for name in new_parts if name not in targeted)

    xml_errors: list[dict[str, str]] = []
    for name in output.names:
        if not (name.endswith(".xml") or name.endswith(".rels")):
            continue
        try:
            parse(output.require(name))
        except Exception as exc:  # noqa: BLE001
            xml_errors.append({"part": name, "error": str(exc)})

    relationship_gaps = _relationship_gaps(output)
    defaults, overrides = _content_types(output)
    content_gaps: list[str] = []
    for name in output.names:
        if name == CONTENT_TYPES or name.endswith(".rels"):
            continue
        if name.casefold() in overrides:
            continue
        extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
        if extension and extension not in defaults:
            content_gaps.append(name)

    expected_missing: list[dict[str, str]] = []
    for name, needles in (expected or {}).items():
        raw = output.read(name)
        if raw is None:
            expected_missing.append({"part": name, "needle": "<part missing>"})
            continue
        text = raw.decode("utf-8", errors="replace")
        for needle in needles:
            if needle and needle not in text:
                expected_missing.append({"part": name, "needle": needle})

    ok = not (
        missing_parts
        or untouched_changed
        or missing_targets
        or unexpected_new
        or xml_errors
        or relationship_gaps
        or expected_missing
    )
    return {
        "ok": ok,
        "preservationMode": "content",
        "sourceParts": len(source_parts),
        "outputParts": len(output_parts),
        "targetedParts": sorted(targeted),
        "unchangedParts": len(unchanged) - len(changed),
        "changedParts": changed,
        "missingParts": missing_parts,
        "removedParts": removed_parts,
        "newParts": new_parts,
        "untouchedChangedParts": untouched_changed,
        "missingTargets": missing_targets,
        "missingRelationships": relationship_gaps,
        "contentTypeGaps": content_gaps,
        "xmlErrors": xml_errors,
        "expectedMissing": expected_missing,
        "sourceSha256": sha256_hex(b"".join(source_hashes[name].encode() for name in sorted(source_hashes))),
        "outputSha256": sha256_hex(b"".join(output_hashes[name].encode() for name in sorted(output_hashes))),
        "warnings": [],
    }


__all__ = ["verify_ooxml"]

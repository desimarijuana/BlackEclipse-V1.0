"""PresentationML edits that preserve masters, layouts, charts and media."""

from __future__ import annotations

import posixpath
import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

from .package import OoxmlPackage
from .plan import EditError
from .xmlutil import attr, direct_children, find_local, iter_local, local, parse, q, serialize

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"


def _relationships(package: OoxmlPackage, part: str) -> dict[str, str]:
    directory, _, base = part.rpartition("/")
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    raw = package.read(rels_name)
    if raw is None:
        return {}
    root = parse(raw)
    out: dict[str, str] = {}
    for relation in iter_local(root, "Relationship"):
        rid = attr(relation, "Id")
        target = attr(relation, "Target")
        if rid and target:
            out[rid] = target
    return out


def _resolve_target(base_part: str, target: str) -> str:
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


def _slide_parts(package: OoxmlPackage) -> list[str]:
    raw = package.read("ppt/presentation.xml")
    if raw is not None:
        root = parse(raw)
        relations = _relationships(package, "ppt/presentation.xml")
        parts: list[str] = []
        for element in iter_local(root, "sldId"):
            rid = ""
            for key, value in element.attrib.items():
                if local(key) == "id" and "}" in key:
                    rid = value
                    break
            target = relations.get(rid)
            if target:
                parts.append(_resolve_target("ppt/presentation.xml", target))
        if parts:
            return parts
    return sorted(
        (name for name in package.names if re.match(r"ppt/slides/slide\d+\.xml$", name)),
        key=lambda value: int(re.search(r"(\d+)\.xml$", value).group(1)),
    )


def _slide_part(package: OoxmlPackage, slide: int) -> str:
    parts = _slide_parts(package)
    if slide < 1 or slide > len(parts):
        raise EditError("EDIT_TARGET_NOT_FOUND", f"slide {slide} does not exist (the deck has {len(parts)})")
    return parts[slide - 1]


def _text_nodes(paragraph: ET.Element) -> list[ET.Element]:
    return [node for node in iter_local(paragraph, "t")]


def _replace_at_nodes(nodes: list[ET.Element], find: str, replace: str, start_at: int) -> tuple[bool, int]:
    texts = [node.text or "" for node in nodes]
    combined = "".join(texts)
    index = combined.find(find, start_at)
    if index < 0:
        return False, start_at
    end = index + len(find)
    starts: list[int] = []
    cursor = 0
    for text in texts:
        starts.append(cursor)
        cursor += len(text)
    start_node = max(i for i, value in enumerate(starts) if value <= index)
    end_node = max(i for i, value in enumerate(starts) if value < end)
    start_offset = index - starts[start_node]
    end_offset = end - starts[end_node]
    prefix = texts[start_node][:start_offset]
    suffix = texts[end_node][end_offset:]
    if start_node == end_node:
        nodes[start_node].text = prefix + replace + suffix
    else:
        nodes[start_node].text = prefix + replace
        for i in range(start_node + 1, end_node):
            nodes[i].text = ""
        nodes[end_node].text = suffix
    return True, index + len(replace)


def _replace_in_paragraph(paragraph: ET.Element, find: str, replace: str, *, match: str) -> int:
    nodes = _text_nodes(paragraph)
    if not nodes:
        return 0
    count = 0
    offset = 0
    while offset <= sum(len(node.text or "") for node in nodes):
        if match == "first" and count:
            break
        changed, offset = _replace_at_nodes(nodes, find, replace, offset)
        if not changed:
            break
        count += 1
        if count > 10_000:
            break
    return count


def _set_text_frame(frame: ET.Element, value: str) -> None:
    paragraphs = direct_children(frame, "p")
    if not paragraphs:
        paragraph = ET.SubElement(frame, q(A, "p"))
        paragraphs = [paragraph]
    paragraph = paragraphs[0]
    runs = [child for child in list(paragraph) if local(child.tag) == "r"]
    if runs:
        texts = _text_nodes(runs[0])
        if texts:
            texts[0].text = value
            for node in texts[1:]:
                node.text = ""
        else:
            ET.SubElement(runs[0], q(A, "t")).text = value
        for run in runs[1:]:
            paragraph.remove(run)
    else:
        run = ET.SubElement(paragraph, q(A, "r"))
        ET.SubElement(run, q(A, "t")).text = value
    for extra in paragraphs[1:]:
        frame.remove(extra)


def _placeholder(element: ET.Element) -> tuple[str, str]:
    placeholder = find_local(element, "ph")
    if placeholder is None:
        return "", ""
    return attr(placeholder, "type"), attr(placeholder, "idx")


def _shape_with_placeholder(root: ET.Element, *, types: tuple[str, ...], idx: tuple[str, ...]) -> Optional[ET.Element]:
    for shape in iter_local(root, "sp"):
        kind, index = _placeholder(shape)
        if kind in types or index in idx:
            return shape
    return None


def set_slide_title(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _slide_part(package, edit["slide"])
    root = parse(package.require(part))
    shape = _shape_with_placeholder(root, types=("title", "ctrTitle"), idx=("0",))
    if shape is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", f"slide {edit['slide']} has no title placeholder")
    frame = find_local(shape, "txBody")
    if frame is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", f"slide {edit['slide']} title has no text body")
    _set_text_frame(frame, edit["text"])
    package.write(part, serialize(root))
    return {part}


def set_notes(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    slide_part = _slide_part(package, edit["slide"])
    relations = _relationships(package, slide_part)
    notes_part = ""
    for target in relations.values():
        if "notesslide" in target.casefold():
            notes_part = _resolve_target(slide_part, target)
            break
    if not notes_part or not package.has(notes_part):
        raise EditError("EDIT_TARGET_NOT_FOUND", f"slide {edit['slide']} has no notes slide")
    root = parse(package.require(notes_part))
    shape = _shape_with_placeholder(root, types=("body",), idx=("1",))
    if shape is None:
        shape = next(iter_local(root, "sp"), None)
    if shape is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", f"slide {edit['slide']} notes have no text body")
    frame = find_local(shape, "txBody")
    if frame is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", f"slide {edit['slide']} notes have no text body")
    _set_text_frame(frame, edit["text"])
    package.write(notes_part, serialize(root))
    return {notes_part}


def set_shape_text(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _slide_part(package, edit["slide"])
    root = parse(package.require(part))
    shapes = list(iter_local(root, "sp"))
    index = edit["shape"]
    if index >= len(shapes):
        raise EditError("EDIT_TARGET_NOT_FOUND", f"shape {index} does not exist on slide {edit['slide']}")
    frame = find_local(shapes[index], "txBody")
    if frame is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", "the selected shape has no text body")
    _set_text_frame(frame, edit["text"])
    package.write(part, serialize(root))
    return {part}


def replace_text(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    requested = edit.get("parts")
    parts = requested or _slide_parts(package)
    if not requested and edit.get("include_notes"):
        parts = list(parts) + [
            name for name in package.names
            if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", name)
        ]
    if not requested and edit.get("include_diagrams", True):
        parts = list(parts) + [
            name for name in package.names
            if re.match(r"ppt/diagrams/data\d+\.xml$", name)
        ]
    touched: set[str] = set()
    total = 0
    for part in parts:
        raw = package.read(part)
        if raw is None or not part.startswith("ppt/"):
            continue
        root = parse(raw)
        changed = 0
        for paragraph in iter_local(root, "p"):
            changed += _replace_in_paragraph(paragraph, edit["find"], edit["replace"], match=edit.get("match") or "all")
        if changed:
            package.write(part, serialize(root))
            touched.add(part)
            total += changed
    if total == 0:
        raise EditError("EDIT_TARGET_NOT_FOUND", f"the text {edit['find']!r} was not found in the presentation")
    return touched


def _presentation(package: OoxmlPackage) -> tuple[ET.Element, dict[str, str]]:
    root = parse(package.require("ppt/presentation.xml"))
    return root, _relationships(package, "ppt/presentation.xml")


def _sld_ids(root: ET.Element) -> list[ET.Element]:
    listing = find_local(root, "sldIdLst")
    return direct_children(listing, "sldId") if listing is not None else []


def _rel_id(element: ET.Element) -> str:
    for key, value in element.attrib.items():
        if local(key) == "id" and "}" in key:
            return value
    return ""


def _content_types_add(package: OoxmlPackage, entries: dict[str, str]) -> set[str]:
    raw = package.read("[Content_Types].xml")
    if raw is None:
        return set()
    root = parse(raw)
    namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
    existing = {attr(item, "PartName").casefold() for item in iter_local(root, "Override")}
    for part_name, content_type in entries.items():
        if f"/{part_name}".casefold() in existing:
            continue
        ET.SubElement(root, q(namespace, "Override"), {
            "PartName": f"/{part_name}",
            "ContentType": content_type,
        })
    package.write("[Content_Types].xml", serialize(root))
    return {"[Content_Types].xml"}


def _content_types_remove(package: OoxmlPackage, part_names: set[str]) -> set[str]:
    raw = package.read("[Content_Types].xml")
    if raw is None:
        return set()
    root = parse(raw)
    targets = {f"/{name}".casefold() for name in part_names}
    for item in list(iter_local(root, "Override")):
        if attr(item, "PartName").casefold() in targets:
            for parent in root.iter():
                if item in list(parent):
                    parent.remove(item)
                    break
    package.write("[Content_Types].xml", serialize(root))
    return {"[Content_Types].xml"}


def _presentation_rel_add(package: OoxmlPackage, target: str, relation_type: str) -> tuple[str, str]:
    rels_name = "ppt/_rels/presentation.xml.rels"
    root = parse(package.require(rels_name))
    used = {attr(item, "Id") for item in iter_local(root, "Relationship")}
    number = 1
    while f"rId{number}" in used:
        number += 1
    rid = f"rId{number}"
    ET.SubElement(root, q("http://schemas.openxmlformats.org/package/2006/relationships", "Relationship"), {
        "Id": rid,
        "Type": relation_type,
        "Target": target,
    })
    package.write(rels_name, serialize(root))
    return rid, rels_name


def _presentation_rel_remove(package: OoxmlPackage, part_name: str) -> set[str]:
    rels_name = "ppt/_rels/presentation.xml.rels"
    raw = package.read(rels_name)
    if raw is None:
        return set()
    root = parse(raw)
    for relation in list(iter_local(root, "Relationship")):
        target = attr(relation, "Target")
        if target and _resolve_target("ppt/presentation.xml", target) == part_name:
            for parent in root.iter():
                if relation in list(parent):
                    parent.remove(relation)
                    break
    package.write(rels_name, serialize(root))
    return {rels_name}


def delete_slide(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    slide_part = _slide_part(package, edit["slide"])
    if len(_slide_parts(package)) <= 1:
        raise EditError("EDIT_LAST_SLIDE", "a presentation must keep at least one slide")
    touched: set[str] = set()
    relations = _relationships(package, slide_part)
    notes_parts = [
        _resolve_target(slide_part, target)
        for target in relations.values()
        if "notesslide" in target.casefold()
    ]
    root, _ = _presentation(package)
    listing = find_local(root, "sldIdLst")
    for element in list(_sld_ids(root)):
        rid = _rel_id(element)
        if rid and _resolve_target("ppt/presentation.xml", _relationships(package, "ppt/presentation.xml").get(rid, "")) == slide_part:
            listing.remove(element)
    package.write("ppt/presentation.xml", serialize(root))
    touched.update(_presentation_rel_remove(package, slide_part))
    touched.add("ppt/presentation.xml")
    slide_rels = slide_part.replace("slides/", "slides/_rels/") + ".rels"
    removed = {slide_part, slide_rels, *notes_parts}
    for notes in notes_parts:
        removed.add(notes.replace("notesSlides/", "notesSlides/_rels/") + ".rels")
    for name in removed:
        package.remove(name)
    touched.update(_content_types_remove(package, removed))
    return touched


def duplicate_slide(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    source = _slide_part(package, edit["slide"])
    slides = _slide_parts(package)
    numbers = [int(value.rsplit("slide", 1)[1].split(".")[0]) for value in slides if value.rsplit("slide", 1)[1].split(".")[0].isdigit()]
    next_number = (max(numbers) + 1) if numbers else 1
    target = f"ppt/slides/slide{next_number}.xml"
    package.write(target, package.require(source))
    touched = {target}

    source_rels = source.replace("slides/", "slides/_rels/") + ".rels"
    target_rels = target.replace("slides/", "slides/_rels/") + ".rels"
    raw = package.read(source_rels)
    notes_target = None
    if raw is not None:
        root = parse(raw)
        for relation in iter_local(root, "Relationship"):
            if "notesslide" in attr(relation, "Type").casefold():
                notes_target = _resolve_target(source, attr(relation, "Target"))
        package.write(target_rels, raw)
        touched.add(target_rels)
    if notes_target and package.has(notes_target):
        notes_numbers = [int(re.search(r"(\d+)\.xml$", name).group(1)) for name in package.names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", name)]
        notes_next = (max(notes_numbers) + 1) if notes_numbers else 1
        new_notes = f"ppt/notesSlides/notesSlide{notes_next}.xml"
        package.write(new_notes, package.require(notes_target))
        notes_rels = notes_target.replace("notesSlides/", "notesSlides/_rels/") + ".rels"
        new_notes_rels = new_notes.replace("notesSlides/", "notesSlides/_rels/") + ".rels"
        raw_notes_rels = package.read(notes_rels)
        if raw_notes_rels is not None:
            root = parse(raw_notes_rels)
            for relation in iter_local(root, "Relationship"):
                if "slide" in attr(relation, "Type").casefold() and "notesSlide" not in attr(relation, "Type"):
                    relation.set("Target", f"../slides/slide{next_number}.xml")
            package.write(new_notes_rels, serialize(root))
            touched.add(new_notes_rels)
        root = parse(package.require(target_rels))
        for relation in iter_local(root, "Relationship"):
            if "notesslide" in attr(relation, "Type").casefold():
                relation.set("Target", f"../notesSlides/notesSlide{notes_next}.xml")
        package.write(target_rels, serialize(root))
        touched.update({new_notes, target_rels})
        touched.update(_content_types_add(package, {
            new_notes: "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml",
        }))
    touched.update(_content_types_add(package, {
        target: "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
    }))

    rid, rels_name = _presentation_rel_add(
        package, f"slides/slide{next_number}.xml",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
    )
    root, _ = _presentation(package)
    listing = find_local(root, "sldIdLst")
    if listing is None:
        listing = ET.SubElement(root, q(P, "sldIdLst"))
    ids = [int(attr(element, "id") or 0) for element in _sld_ids(root)]
    new_id = max(ids + [255]) + 1
    ET.SubElement(listing, q(P, "sldId"), {q(R, "id"): rid, "id": str(new_id)})
    package.write("ppt/presentation.xml", serialize(root))
    touched.update({rels_name, "ppt/presentation.xml"})
    return touched


def _rels_entries(package: OoxmlPackage, part: str) -> list[dict[str, str]]:
    directory, _, base = part.rpartition("/")
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    raw = package.read(rels_name)
    if raw is None:
        return []
    root = parse(raw)
    return [
        {"id": attr(item, "Id"), "type": attr(item, "Type"), "target": attr(item, "Target")}
        for item in iter_local(root, "Relationship")
        if attr(item, "Id") and attr(item, "Target")
    ]


def _diagram_parts(package: OoxmlPackage, slide_part: str) -> list[str]:
    parts = [
        _resolve_target(slide_part, entry["target"])
        for entry in _rels_entries(package, slide_part)
        if entry["type"].casefold().endswith("/diagramdata")
    ]
    if parts:
        return parts
    return sorted(
        name for name in package.names if re.match(r"ppt/diagrams/data\d+\.xml$", name)
    )


def _diagram_part(package: OoxmlPackage, slide: int, index: int) -> str:
    slide_part = _slide_part(package, slide)
    parts = _diagram_parts(package, slide_part)
    if index < 0 or index >= len(parts):
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", f"slide {slide} has no SmartArt diagram at index {index}")
    return parts[index]


def _diagram_nodes(root: ET.Element) -> list[ET.Element]:
    listing = find_local(root, "ptLst")
    return direct_children(listing, "pt") if listing is not None else []


def _node_id(node: ET.Element) -> str:
    return attr(node, "modelId")


def _text_run(node: ET.Element) -> ET.Element:
    body = find_local(node, "t")
    if body is None or body.tag != q(DGM, "t"):
        body = ET.SubElement(node, q(DGM, "t"))
        paragraph = ET.SubElement(body, q(A, "p"))
        run = ET.SubElement(paragraph, q(A, "r"))
        return ET.SubElement(run, q(A, "t"))
    for child in body.iter():
        if child is not body and local(child.tag) == "t":
            return child
    paragraph = ET.SubElement(body, q(A, "p"))
    run = ET.SubElement(paragraph, q(A, "r"))
    return ET.SubElement(run, q(A, "t"))


def _set_node_text(node: ET.Element, text: str) -> None:
    _text_run(node).text = text


def add_smartart_node(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _diagram_part(package, edit["slide"], edit.get("diagram", 0))
    root = parse(package.require(part))
    nodes = _diagram_nodes(root)
    if not nodes:
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", "the diagram has no nodes")
    parent = None
    if edit.get("parent"):
        parent = next((node for node in nodes if _node_id(node) == edit["parent"]), None)
    elif edit.get("parentIndex") is not None:
        index = edit["parentIndex"]
        parent = nodes[index] if 0 <= index < len(nodes) else None
    else:
        parent = next((node for node in nodes if attr(node, "type") == "doc"), nodes[0])
    if parent is None:
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", "the parent node was not found")
    used = {_node_id(node) for node in nodes}
    number = len(nodes) + 1
    while f"eclipse_dgm_{number}" in used:
        number += 1
    model_id = f"eclipse_dgm_{number}"
    node = ET.SubElement(find_local(root, "ptLst"), q(DGM, "pt"), {
        "modelId": model_id, "type": "node",
    })
    _set_node_text(node, edit.get("text") or "")

    connections = find_local(root, "cxnLst")
    if connections is None:
        connections = ET.SubElement(root, q(DGM, "cxnLst"))
    missing = [attr(connection, "modelId") for connection in direct_children(connections, "cxn")]
    connection_number = len(missing) + 1
    while f"eclipse_cxn_{connection_number}" in missing:
        connection_number += 1
    order = sum(
        1 for connection in direct_children(connections, "cxn")
        if attr(connection, "srcId") == _node_id(parent)
    )
    ET.SubElement(connections, q(DGM, "cxn"), {
        "modelId": f"eclipse_cxn_{connection_number}",
        "srcId": _node_id(parent),
        "destId": model_id,
        "type": "parOf",
        "srcOrd": str(order),
    })
    package.write(part, serialize(root))
    return {part}


def remove_smartart_node(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _diagram_part(package, edit["slide"], edit.get("diagram", 0))
    root = parse(package.require(part))
    nodes = _diagram_nodes(root)
    if not nodes:
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", "the diagram has no nodes")
    root_node = next((node for node in nodes if attr(node, "type") == "doc"), nodes[0])
    target = next((node for node in nodes if _node_id(node) == edit["node"]), None)
    if target is None:
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", f"diagram node {edit['node']!r} was not found")
    if _node_id(target) == _node_id(root_node):
        raise EditError("EDIT_DIAGRAM_ROOT", "the root SmartArt node cannot be removed")
    connections = find_local(root, "cxnLst")
    children: dict[str, list[str]] = {}
    if connections is not None:
        for connection in direct_children(connections, "cxn"):
            children.setdefault(attr(connection, "srcId"), []).append(attr(connection, "destId"))
    doomed: set[str] = set()
    queue = [_node_id(target)]
    while queue:
        current = queue.pop()
        if current in doomed:
            continue
        doomed.add(current)
        queue.extend(children.get(current, []))
    listing = find_local(root, "ptLst")
    for node in list(direct_children(listing, "pt")):
        if _node_id(node) in doomed:
            listing.remove(node)
    if connections is not None:
        for connection in list(direct_children(connections, "cxn")):
            if attr(connection, "srcId") in doomed or attr(connection, "destId") in doomed:
                connections.remove(connection)
    package.write(part, serialize(root))
    return {part}


def set_smartart_node_text(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _diagram_part(package, edit["slide"], edit.get("diagram", 0))
    root = parse(package.require(part))
    node = next((item for item in _diagram_nodes(root) if _node_id(item) == edit["node"]), None)
    if node is None:
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", f"diagram node {edit['node']!r} was not found")
    _set_node_text(node, edit.get("text") or "")
    package.write(part, serialize(root))
    return {part}


def _slide_rels_name(part: str) -> str:
    directory, _, base = part.rpartition("/")
    return f"{directory}/_rels/{base}.rels"


def _diagram_relation_ids(package: OoxmlPackage, slide_part: str, index: int) -> tuple[dict[str, str], list[dict[str, str]]]:
    parts = _diagram_parts(package, slide_part)
    if index < 0 or index >= len(parts):
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", f"the slide has no SmartArt diagram at index {index}")
    data_part = parts[index]
    entries = _rels_entries(package, slide_part)
    data_id = next(
        (entry["id"] for entry in entries
         if entry["type"].casefold().endswith("/diagramdata")
         and _resolve_target(slide_part, entry["target"]) == data_part),
        None,
    )
    if data_id is None:
        raise EditError("EDIT_DIAGRAM_NOT_FOUND", "the diagram data relationship was not found")
    root = parse(package.require(slide_part))
    for rel_ids in iter_local(root, "relIds"):
        if attr(rel_ids, "dm") == data_id:
            return {
                "dm": data_id,
                "lo": attr(rel_ids, "lo"),
                "qs": attr(rel_ids, "qs"),
                "cs": attr(rel_ids, "cs"),
            }, entries
    raise EditError("EDIT_DIAGRAM_NOT_FOUND", "the diagram has no relIds mapping")


def set_smartart_layout(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    target_slide = _slide_part(package, edit["slide"])
    donor_slide = _slide_part(package, edit["fromSlide"])
    target_ids, _ = _diagram_relation_ids(package, target_slide, edit.get("diagram", 0))
    donor_ids, donor_entries = _diagram_relation_ids(package, donor_slide, edit.get("fromDiagram", 0))
    donor_by_id = {entry["id"]: entry for entry in donor_entries}
    rels_name = _slide_rels_name(target_slide)
    rels_root = parse(package.require(rels_name))
    changed = False
    for key, relationship_type in (("lo", "diagramLayout"), ("qs", "diagramQuickStyle"), ("cs", "diagramColors")):
        target_rid = target_ids.get(key)
        donor_rid = donor_ids.get(key)
        donor_entry = donor_by_id.get(donor_rid) if donor_rid else None
        if not target_rid or donor_entry is None:
            raise EditError("EDIT_DIAGRAM_LAYOUT_MISSING", f"the {relationship_type} relationship is missing")
        donor_part = _resolve_target(donor_slide, donor_entry["target"])
        if not package.has(donor_part):
            raise EditError("EDIT_DIAGRAM_LAYOUT_MISSING", f"the donor {relationship_type} part is missing")
        relative = posixpath.relpath(donor_part, start=posixpath.dirname(target_slide))
        for relation in iter_local(rels_root, "Relationship"):
            if attr(relation, "Id") == target_rid:
                if attr(relation, "Target") != relative:
                    relation.set("Target", relative)
                    changed = True
                break
        else:
            raise EditError("EDIT_DIAGRAM_LAYOUT_MISSING", f"the target {relationship_type} relationship is missing")
    if changed:
        package.write(rels_name, serialize(rels_root))
    return {rels_name}


def _chart_parts(package: OoxmlPackage, slide_part: str) -> list[str]:
    root = parse(package.require(slide_part))
    relations = _relationships(package, slide_part)
    parts: list[str] = []
    for chart_element in iter_local(root, "chart"):
        rid = _rel_id(chart_element)
        target = relations.get(rid)
        if target:
            parts.append(_resolve_target(slide_part, target))
    return parts


def _set_cache(parent: ET.Element, values: list[str], *, numeric: bool) -> None:
    ref_tag = "numRef" if numeric else "strRef"
    cache_tag = "numCache" if numeric else "strCache"
    reference = find_local(parent, ref_tag)
    if reference is None:
        reference = ET.SubElement(parent, q(C, ref_tag))
    for formula in list(iter_local(reference, "f")):
        parent_of_formula = None
        for candidate in reference.iter():
            if formula in list(candidate):
                parent_of_formula = candidate
                break
        if parent_of_formula is not None:
            parent_of_formula.remove(formula)
    cache = find_local(reference, cache_tag)
    if cache is None:
        cache = ET.SubElement(reference, q(C, cache_tag))
    for point in list(iter_local(cache, "pt")):
        for candidate in cache.iter():
            if point in list(candidate):
                candidate.remove(point)
                break
    count = find_local(cache, "ptCount")
    if count is None:
        count = ET.Element(q(C, "ptCount"))
        cache.append(count)
    count.set("val", str(len(values)))
    for index, value in enumerate(values):
        point = ET.SubElement(cache, q(C, "pt"), {"idx": str(index)})
        ET.SubElement(point, q(C, "v")).text = value


def replace_chart_data(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    slide_part = _slide_part(package, edit["slide"])
    charts = _chart_parts(package, slide_part)
    index = edit.get("chart", 0)
    if index >= len(charts):
        raise EditError("EDIT_CHART_NOT_FOUND", f"slide {edit['slide']} has no chart at index {index}")
    chart_part = charts[index]
    root = parse(package.require(chart_part))
    plot_area = find_local(root, "plotArea")
    if plot_area is None:
        raise EditError("EDIT_CHART_NOT_FOUND", "the chart has no plot area")
    series: list[ET.Element] = []
    for child in list(plot_area):
        if local(child.tag).endswith("Chart"):
            series.extend(direct_children(child, "ser"))
    if not series:
        raise EditError("EDIT_CHART_NOT_FOUND", "the chart has no series")
    if len(edit["series"]) != len(series):
        raise EditError(
            "EDIT_CHART_SERIES_MISMATCH",
            f"the chart has {len(series)} series; the plan must supply exactly that many",
        )
    for series_element, supplied in zip(series, edit["series"]):
        name = supplied.get("name")
        if name is not None:
            tx = find_local(series_element, "tx")
            literal = find_local(tx, "v") if tx is not None else None
            if literal is not None:
                literal.text = name
        category = find_local(series_element, "cat")
        if category is None:
            category = ET.SubElement(series_element, q(C, "cat"))
        _set_cache(category, edit["categories"], numeric=False)
        value = find_local(series_element, "val")
        if value is None:
            value = ET.SubElement(series_element, q(C, "val"))
        _set_cache(value, [str(item) for item in supplied["values"]], numeric=True)
    package.write(chart_part, serialize(root))
    return {chart_part}


__all__ = [
    "add_smartart_node",
    "delete_slide",
    "duplicate_slide",
    "remove_smartart_node",
    "replace_chart_data",
    "replace_text",
    "set_notes",
    "set_shape_text",
    "set_slide_title",
    "set_smartart_node_text",
]

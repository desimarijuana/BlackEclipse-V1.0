"""WordprocessingML edits that preserve every other package part."""

from __future__ import annotations

import base64
from typing import Any, Optional
from xml.etree import ElementTree as ET

from .package import OoxmlPackage
from .plan import EditError
from .xmlutil import (
    attr,
    direct_children,
    find_local,
    iter_local,
    local,
    parse,
    q,
    serialize,
    text_of,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
DC = "http://purl.org/dc/elements/1.1/"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"

_WORD_PART_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)


def _default_parts(package: OoxmlPackage) -> list[str]:
    return [
        name for name in package.names
        if name == "word/document.xml"
        or name.startswith("word/header")
        or name.startswith("word/footer")
        or name in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
    ]


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
    for n in nodes:
        if n.text and (n.text.startswith(" ") or n.text.endswith(" ")):
            n.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
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


def replace_text(
    package: OoxmlPackage,
    edit: dict[str, Any],
) -> set[str]:
    find = edit["find"]
    replace = edit["replace"]
    match = edit.get("match") or "all"
    requested = edit.get("parts")
    parts = requested or _default_parts(package)
    touched: set[str] = set()
    total = 0
    for part in parts:
        raw = package.read(part)
        if raw is None:
            continue
        if not (part == "word/document.xml" or part.startswith(_WORD_PART_PREFIXES)):
            continue
        root = parse(raw)
        changed = 0
        for paragraph in iter_local(root, "p"):
            changed += _replace_in_paragraph(paragraph, find, replace, match=match)
        if changed:
            package.write(part, serialize(root))
            touched.add(part)
            total += changed
    if total == 0:
        raise EditError("EDIT_TARGET_NOT_FOUND", f"the text {find!r} was not found in the document")
    return touched


def _paragraph_text_nodes(paragraph: ET.Element) -> list[ET.Element]:
    return _text_nodes(paragraph)


def _set_paragraph_runs(paragraph: ET.Element, value: str) -> None:
    nodes = _paragraph_text_nodes(paragraph)
    if nodes:
        nodes[0].text = value
        if value.startswith(" ") or value.endswith(" "):
            nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for node in nodes[1:]:
            node.text = ""
        return
    run = ET.SubElement(paragraph, q(W, "r"))
    node = ET.SubElement(run, q(W, "t"))
    node.text = value
    if value.startswith(" ") or value.endswith(" "):
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def set_paragraph_text(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = edit.get("part") or "word/document.xml"
    raw = package.require(part)
    root = parse(raw)
    body = find_local(root, "body")
    if body is None:
        body = root
    paragraphs = direct_children(body, "p")
    index = edit["index"]
    if index >= len(paragraphs):
        raise EditError(
            "EDIT_TARGET_NOT_FOUND",
            f"paragraph {index} does not exist (the part has {len(paragraphs)} top-level paragraphs)",
        )
    _set_paragraph_runs(paragraphs[index], edit["text"])
    package.write(part, serialize(root))
    return {part}


def set_table_cell(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = edit.get("part") or "word/document.xml"
    raw = package.require(part)
    root = parse(raw)
    body = find_local(root, "body")
    if body is None:
        body = root
    tables = list(iter_local(body, "tbl"))
    table_index = edit["table"]
    if table_index >= len(tables):
        raise EditError("EDIT_TARGET_NOT_FOUND", f"table {table_index} does not exist")
    rows = direct_children(tables[table_index], "tr")
    if edit["row"] >= len(rows):
        raise EditError("EDIT_TARGET_NOT_FOUND", f"row {edit['row']} does not exist in table {table_index}")
    cells = direct_children(rows[edit["row"]], "tc")
    if edit["col"] >= len(cells):
        raise EditError("EDIT_TARGET_NOT_FOUND", f"column {edit['col']} does not exist in that row")
    cell = cells[edit["col"]]
    paragraphs = direct_children(cell, "p")
    if not paragraphs:
        paragraph = ET.SubElement(cell, q(W, "p"))
        paragraphs = [paragraph]
    _set_paragraph_runs(paragraphs[0], edit["text"])
    for extra in paragraphs[1:]:
        cell.remove(extra)
    package.write(part, serialize(root))
    return {part}


def set_core_property(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = "docProps/core.xml"
    raw = package.read(part)
    if raw is None:
        raise EditError("EDIT_PART_MISSING", "the package has no docProps/core.xml")
    root = parse(raw)
    name = edit["name"]
    namespace = CP if name in ("keywords", "lastModifiedBy") else DC
    element = find_local(root, name)
    if element is None:
        element = ET.SubElement(root, q(namespace, name))
    element.text = edit["value"]
    package.write(part, serialize(root))
    return {part}


def _parent_of(root: ET.Element, target: ET.Element) -> Optional[ET.Element]:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def _image_extension(data: bytes, declared: str) -> str:
    if declared:
        return "jpg" if declared in ("jpg", "jpeg") else declared
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data.startswith(b"GIF8"):
        return "gif"
    raise EditError("EDIT_IMAGE_INVALID", "the image is not a PNG, JPEG or GIF")


def _image_size(data: bytes) -> Optional[tuple[int, int]]:
    try:
        from PIL import Image  # noqa: PLC0415

        with Image.open(__import__("io").BytesIO(data)) as image:
            return image.size
    except Exception:  # noqa: BLE001 - a missing Pillow degrades to the requested width
        return None


def _ensure_image_content_type(package: OoxmlPackage, extension: str) -> None:
    raw = package.read("[Content_Types].xml")
    if raw is None:
        return
    root = parse(raw)
    for element in iter_local(root, "Default"):
        if attr(element, "Extension").casefold() == extension:
            return
    mime = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif"}[extension]
    ET.SubElement(root, q(CT, "Default"), {"Extension": extension, "ContentType": mime})
    package.write("[Content_Types].xml", serialize(root))


def _add_image_relationship(package: OoxmlPackage, target: str) -> str:
    rels_name = "word/_rels/document.xml.rels"
    raw = package.read(rels_name)
    if raw is None:
        root = ET.Element(q("http://schemas.openxmlformats.org/package/2006/relationships", "Relationships"))
    else:
        root = parse(raw)
    used = [attr(item, "Id") for item in iter_local(root, "Relationship")]
    number = 1
    while f"rId{number}" in used:
        number += 1
    rid = f"rId{number}"
    ET.SubElement(root, q("http://schemas.openxmlformats.org/package/2006/relationships", "Relationship"), {
        "Id": rid,
        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        "Target": target,
    })
    package.write(rels_name, serialize(root))
    return rid


def insert_image(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    try:
        data = base64.b64decode(edit["imageBase64"], validate=True)
    except Exception as exc:  # noqa: BLE001
        raise EditError("EDIT_IMAGE_INVALID", "imageBase64 is not valid base64") from exc
    if not data:
        raise EditError("EDIT_IMAGE_INVALID", "the image is empty")
    extension = _image_extension(data, edit.get("extension") or "")
    existing = [
        name for name in package.names
        if name.startswith("word/media/") and name.rsplit(".", 1)[-1].casefold() in ("png", "jpg", "jpeg", "gif")
    ]
    index = 1
    while package.has(f"word/media/eclipse_image{index}.{extension}"):
        index += 1
    media_name = f"word/media/eclipse_image{index}.{extension}"
    package.write(media_name, data)
    _ensure_image_content_type(package, extension)
    rid = _add_image_relationship(package, f"media/eclipse_image{index}.{extension}")

    width_inches = float(edit.get("widthInches") or 4.0)
    height_inches = edit.get("heightInches")
    if height_inches is None:
        size = _image_size(data)
        height_inches = width_inches * (size[1] / size[0]) if size and size[0] else width_inches * 0.75
    cx = int(width_inches * 914400)
    cy = int(float(height_inches) * 914400)

    root = parse(package.require("word/document.xml"))
    body = find_local(root, "body")
    if body is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", "the document has no body")
    paragraph = ET.Element(q(W, "p"))
    run = ET.SubElement(paragraph, q(W, "r"))
    drawing = ET.SubElement(run, q(W, "drawing"))
    inline = ET.SubElement(drawing, q(WP, "inline"), {
        "distT": "0", "distB": "0", "distL": "0", "distR": "0",
    })
    ET.SubElement(inline, q(WP, "extent"), {"cx": str(cx), "cy": str(cy)})
    ET.SubElement(inline, q(WP, "docPr"), {"id": str(index), "name": edit.get("altText") or "Inserted image"})
    graphic = ET.SubElement(inline, q(A, "graphic"))
    graphic_data = ET.SubElement(graphic, q(A, "graphicData"), {"uri": PIC})
    picture = ET.SubElement(graphic_data, q(PIC, "pic"))
    nv = ET.SubElement(picture, q(PIC, "nvPicPr"))
    ET.SubElement(nv, q(PIC, "cNvPr"), {"id": str(index), "name": edit.get("altText") or "Inserted image"})
    ET.SubElement(nv, q(PIC, "cNvPicPr"))
    blip_fill = ET.SubElement(picture, q(PIC, "blipFill"))
    ET.SubElement(blip_fill, q(A, "blip"), {q(R, "embed"): rid})
    stretch = ET.SubElement(blip_fill, q(A, "stretch"))
    ET.SubElement(stretch, q(A, "fillRect"))
    shape_properties = ET.SubElement(picture, q(PIC, "spPr"))
    transform = ET.SubElement(shape_properties, q(A, "xfrm"))
    ET.SubElement(transform, q(A, "off"), {"x": "0", "y": "0"})
    ET.SubElement(transform, q(A, "ext"), {"cx": str(cx), "cy": str(cy)})
    geometry = ET.SubElement(shape_properties, q(A, "prstGeom"), {"prst": "rect"})
    ET.SubElement(geometry, q(A, "avLst"))

    paragraphs = direct_children(body, "p")
    after = edit.get("afterParagraph")
    if after is None:
        body.append(paragraph)
    elif after >= len(paragraphs):
        body.append(paragraph)
    else:
        body.insert(list(body).index(paragraphs[after]) + 1, paragraph)
    package.write("word/document.xml", serialize(root))
    return {"word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml", media_name}


def _word_parts_for(package: OoxmlPackage, requested: Optional[list[str]]) -> list[str]:
    return requested or _default_parts(package)


def _revisions(package: OoxmlPackage, edit: dict[str, Any], *, accept: bool) -> set[str]:
    touched: set[str] = set()
    total = 0
    for part in _word_parts_for(package, edit.get("parts")):
        raw = package.read(part)
        if raw is None:
            continue
        root = parse(raw)
        changed = 0
        for _ in range(12):
            pass_changed = 0
            if accept:
                for tag, action in (("ins", "unwrap"), ("moveTo", "unwrap"), ("del", "remove"), ("moveFrom", "remove")):
                    for element in list(iter_local(root, tag)):
                        parent = _parent_of(root, element)
                        if parent is None:
                            continue
                        if action == "remove":
                            parent.remove(element)
                        else:
                            position = list(parent).index(element)
                            parent.remove(element)
                            for offset, child in enumerate(list(element)):
                                parent.insert(position + offset, child)
                        pass_changed += 1
            else:
                for tag, action in (("ins", "remove"), ("moveTo", "remove"), ("del", "unwrap"), ("moveFrom", "unwrap")):
                    for element in list(iter_local(root, tag)):
                        parent = _parent_of(root, element)
                        if parent is None:
                            continue
                        if action == "remove":
                            parent.remove(element)
                        else:
                            if tag == "del":
                                for node in iter_local(element, "delText"):
                                    node.tag = q(W, "t")
                            position = list(parent).index(element)
                            parent.remove(element)
                            for offset, child in enumerate(list(element)):
                                parent.insert(position + offset, child)
                        pass_changed += 1
            changed += pass_changed
            if not pass_changed:
                break
        if changed:
            package.write(part, serialize(root))
            touched.add(part)
            total += changed
    if total == 0:
        raise EditError("EDIT_NO_REVISIONS", "no tracked revisions were found in the requested parts")
    return touched


def accept_revisions(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    return _revisions(package, edit, accept=True)


def reject_revisions(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    return _revisions(package, edit, accept=False)


def list_editable_parts(package: OoxmlPackage) -> list[str]:
    return _default_parts(package)


__all__ = [
    "accept_revisions",
    "insert_image",
    "list_editable_parts",
    "reject_revisions",
    "replace_text",
    "set_core_property",
    "set_paragraph_text",
    "set_table_cell",
]

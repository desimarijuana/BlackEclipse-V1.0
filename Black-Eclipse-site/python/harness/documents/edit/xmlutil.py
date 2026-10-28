"""Small XML helpers for targeted OOXML edits.

ElementTree is used because it is already the read path's parser. Namespaces are
re-registered from the source document so an edited part keeps its familiar
prefixes instead of gaining ``ns0``-style names.
"""

from __future__ import annotations

import io
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from .package import OoxmlError

DEFAULT_NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def parse(data: bytes) -> ET.Element:
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise OoxmlError(
            "EDIT_XML_UNSAFE",
            "XML DTD/entity declarations are not accepted in an Office package part",
        )
    namespaces: dict[str, str] = dict(DEFAULT_NAMESPACES)
    for _event, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        if prefix and prefix not in namespaces:
            namespaces[prefix] = uri
    for prefix, uri in namespaces.items():
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            continue
    return ET.fromstring(data)


def serialize(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def iter_local(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for element in root.iter():
        if local(element.tag) == name:
            yield element


def find_local(root: ET.Element, name: str) -> Any:
    for element in iter_local(root, name):
        return element
    return None


def attr(element: Any, name: str, default: str = "") -> str:
    if element is None:
        return default
    for key, value in element.attrib.items():
        if local(key) == name:
            return value
    return default


def set_attr(element: ET.Element, namespace: str, name: str, value: str) -> None:
    element.set(q(namespace, name), value)


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in iter_local(element, "t"))


def set_text_of(element: ET.Element, value: str) -> None:
    nodes = list(iter_local(element, "t"))
    if not nodes:
        return
    nodes[0].text = value
    if value.startswith(" ") or value.endswith(" "):
        nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for node in nodes[1:]:
        node.text = ""


def direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local(child.tag) == name]


__all__ = [
    "DEFAULT_NAMESPACES",
    "attr",
    "direct_children",
    "find_local",
    "iter_local",
    "local",
    "parse",
    "q",
    "serialize",
    "set_attr",
    "set_text_of",
    "text_of",
]

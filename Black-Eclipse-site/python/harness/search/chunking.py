"""Reusable chunking engine.

Four strategies, all deterministic and dependency-free:

  * ``fixed``      — hard split every ``target_chars`` (fast baseline).
  * ``sliding``    — sliding window with overlap (recall-oriented).
  * ``structural`` — split on document structure (headings, paragraphs, table
                     rows) and pack units up to ``target_chars``. Tables -
                     including financial statement tables - are never split
                     across a row boundary. This is the default for financial
                     documents because it preserves table/section structure.
  * ``semantic``   — group adjacent sentences by lexical cohesion so a chunk
                     holds one coherent idea. Deterministic (no model); see
                     ``docs/harness/search-retrieval.md`` for the honest scope.

The chunker operates on plain text (callers that already have a parsed DocumentIR
should feed its section/paragraph text here). A hierarchy of
``heading -> subsection -> paragraph`` is preserved as a ``section_path`` on each
chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .contracts import ChunkRecord

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
_NUMBERED_RE = re.compile(r"^\s{0,3}(\d+(?:\.\d+)*)[.)]?\s+(\S.*)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])|(?<=[.!?])\s+$|\n{2,}")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]*")

_TABLE_HINT = re.compile(r"(\|.*\|)|(\t.*\t)|(\S\s+\|\s+\S)")


@dataclass
class TextSection:
    """A structural unit: a heading plus its body lines."""

    heading: str = ""
    level: int = 0
    body: str = ""
    page: Optional[int] = None
    section_path: str = ""
    kind: str = "paragraph"
    metadata: dict = field(default_factory=dict)


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("|") and stripped.endswith("|"):
        return True
    if stripped.count("|") >= 2:
        return True
    if stripped.count("\t") >= 2:
        return True
    return False


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_RE.split(text or "") if p and p.strip()]
    return parts


def detect_sections(text: str, *, page: Optional[int] = None) -> list[TextSection]:
    """Split text into structural units using markdown/numbered headings.

    Consecutive non-heading lines become a single section body. A pure-text
    document yields exactly one section.
    """
    lines = (text or "").splitlines()
    sections: list[TextSection] = []
    stack: list[tuple[int, str]] = []
    current = TextSection(page=page)
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current.heading or body:
            current.body = "\n".join(body).strip()
            sections.append(current)
        current = TextSection(page=page)
        body = []

    for line in lines:
        heading = _HEADING_RE.match(line)
        numbered = _NUMBERED_RE.match(line) if not heading else None
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            stack = [(lvl, name) for lvl, name in stack if lvl < level]
            stack.append((level, title))
            current = TextSection(heading=title, level=level, page=page,
                                  section_path=" › ".join(name for _, name in stack))
        elif numbered and len(numbered.group(1)) <= 6 and len(line.strip()) < 160:
            flush()
            title = line.strip()
            depth = numbered.group(1).count(".") + 1
            stack = [(lvl, name) for lvl, name in stack if lvl < depth]
            stack.append((depth, title))
            current = TextSection(heading=title, level=depth, page=page,
                                  section_path=" › ".join(name for _, name in stack))
        else:
            body.append(line)
    flush()
    if not sections and text:
        sections = [TextSection(body=text.strip(), page=page)]
    return sections


def _flush_chunk(buffer: list[str], out: list[str], *, kind: str) -> None:
    text = "\n".join(buffer).strip()
    if text:
        out.append(text)


def _pack_units(units: list[tuple[str, str]], target: int, overlap: int, min_chars: int) -> list[str]:
    """Pack (kind, text) units into chunks of ~target chars, never splitting a unit."""
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for kind, text in units:
        text = text.strip()
        if not text:
            continue
        unit_len = len(text)
        if not buffer:
            buffer = [text]
            size = unit_len
            continue
        if size + unit_len + 1 > target and size >= min_chars:
            chunks.append("\n".join(buffer))
            # Sliding overlap: retain the tail of the previous chunk.
            tail = _tail_chars(buffer, overlap)
            buffer = ([tail] if tail else []) + [text]
            size = len(tail) + unit_len + 1 if tail else unit_len
        else:
            buffer.append(text)
            size += unit_len + 1
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks


def _tail_chars(buffer: list[str], overlap: int) -> str:
    if overlap <= 0:
        return ""
    joined = "\n".join(buffer)
    if len(joined) <= overlap:
        return joined
    return joined[-overlap:]


def chunk_text(
    text: str,
    *,
    document_id: str = "",
    strategy: str = "structural",
    target_chars: int = 1_200,
    overlap_chars: int = 150,
    min_chars: int = 80,
    max_chars: int = 8_000,
    content_type: str = "text",
    sections: Optional[list[TextSection]] = None,
    semantic_vectors: Optional[list[list[float]]] = None,
) -> list[ChunkRecord]:
    """Chunk plain text into ``ChunkRecord``s. Order is preserved.

    ``semantic_vectors`` (one per ``split_sentences(text)`` entry) makes the
    ``semantic`` strategy split on real embedding similarity; absent, it uses
    deterministic lexical cohesion.
    """
    text = text or ""
    target = max(200, min(target_chars, max_chars))
    overlap = max(0, min(overlap_chars, target // 2))
    strategy = (strategy or "structural").lower()

    if not text.strip():
        return []

    if strategy == "fixed":
        pieces = _fixed_split(text, target, max_chars)
    elif strategy == "sliding":
        pieces = _sliding_split(text, target, overlap or target // 4, max_chars)
    elif strategy == "semantic":
        pieces = _semantic_split(text, target, min_chars, max_chars, vectors=semantic_vectors)
    else:
        pieces = _structural_split(text, target, overlap, min_chars, max_chars, sections=sections)

    records: list[ChunkRecord] = []
    for ordinal, piece in enumerate(pieces):
        content = piece.strip()
        if not content:
            continue
        records.append(
            ChunkRecord(
                chunk_id=f"{document_id}:{ordinal}" if document_id else f"chunk-{ordinal}",
                content=content,
                document_id=document_id,
                ordinal=ordinal,
                kind="table" if _looks_like_table(content) else "paragraph",
                token_count=max(1, len(content) // 4),
                metadata={"strategy": strategy, "contentType": content_type},
            )
        )
    return records


def _fixed_split(text: str, target: int, max_chars: int) -> list[str]:
    return [text[i : i + target] for i in range(0, len(text), target)]


def _sliding_split(text: str, target: int, overlap: int, max_chars: int) -> list[str]:
    step = max(1, target - overlap)
    return [text[i : i + target] for i in range(0, len(text), step)]


def _structural_split(
    text: str,
    target: int,
    overlap: int,
    min_chars: int,
    max_chars: int,
    *,
    sections: Optional[list[TextSection]],
) -> list[str]:
    sections = sections if sections is not None else detect_sections(text)
    units: list[tuple[str, str]] = []
    for section in sections:
        for block in _section_blocks(section):
            units.append(block)
    packed = _pack_units(units, target, overlap, min_chars)
    return _enforce_max(packed, max_chars)


def _section_blocks(section: TextSection) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    heading = section.section_path or section.heading
    body = section.body or ""
    table_buffer: list[str] = []
    para_buffer: list[str] = []

    def flush_table() -> None:
        if table_buffer:
            blocks.append(("table", "\n".join(table_buffer)))
            table_buffer.clear()

    def flush_para() -> None:
        if para_buffer:
            text = "\n".join(para_buffer).strip()
            if text:
                prefix = f"{heading}\n" if heading and not blocks else ""
                blocks.append(("paragraph", f"{prefix}{text}"))
            para_buffer.clear()

    for line in body.splitlines():
        if _is_table_line(line) or _is_table_separator(line):
            flush_para()
            table_buffer.append(line)
        elif not line.strip():
            flush_table()
            flush_para()
        else:
            flush_table()
            para_buffer.append(line)
    flush_table()
    flush_para()
    return blocks


def _semantic_split(
    text: str, target: int, min_chars: int, max_chars: int,
    *, vectors: Optional[list[list[float]]] = None,
) -> list[str]:
    """Group adjacent sentences by semantic similarity.

    With ``vectors`` (one per sentence) the boundary is an embedding cosine
    below a threshold; without them it is deterministic lexical cohesion (no
    model). Either way the split is bounded by ``target``.
    """
    sentences = split_sentences(text)
    if not sentences:
        return [text] if text.strip() else []

    use_vectors = vectors is not None and len(vectors) == len(sentences)

    groups: list[str] = []
    current: list[str] = []
    current_terms: set[str] = set()
    size = 0
    for index, sentence in enumerate(sentences):
        if use_vectors:
            similar = index > 0 and _cosine(vectors[index], vectors[index - 1]) >= _SEMANTIC_SIM_THRESHOLD
        else:
            terms = {w.lower() for w in _WORD_RE.findall(sentence) if len(w) > 2}
            overlap = (
                len(terms & current_terms) / max(1, min(len(terms), len(current_terms))) if current else 1.0
            )
            similar = (not current) or overlap >= 0.12
        too_long = size + len(sentence) > target and size >= min_chars
        if current and (too_long or not similar):
            groups.append(" ".join(current))
            current = []
            current_terms = set()
            size = 0
        current.append(sentence)
        if not use_vectors:
            current_terms |= {w.lower() for w in _WORD_RE.findall(sentence) if len(w) > 2}
        size += len(sentence) + 1
    if current:
        groups.append(" ".join(current))
    return _enforce_max(groups, max_chars)


_SEMANTIC_SIM_THRESHOLD = 0.35


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _enforce_max(chunks: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            out.append(chunk)
        else:
            out.extend(_fixed_split(chunk, max_chars, max_chars))
    return out


def _looks_like_table(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    table_lines = sum(1 for line in lines if _is_table_line(line) or _is_table_separator(line))
    return table_lines >= max(2, len(lines) // 2)


__all__ = [
    "TextSection",
    "chunk_text",
    "detect_sections",
    "split_sentences",
]

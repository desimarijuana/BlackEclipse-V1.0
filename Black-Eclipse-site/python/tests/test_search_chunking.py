"""Chunking engine tests."""

from __future__ import annotations

from harness.search.chunking import chunk_text, detect_sections, split_sentences


def test_fixed_split_respects_target():
    text = "a" * 2_500
    chunks = chunk_text(text, document_id="d", strategy="fixed", target_chars=1_000, max_chars=2_000)
    assert len(chunks) >= 3
    assert all(len(c.content) <= 2_000 for c in chunks)
    assert "".join(c.content for c in chunks) == text


def test_sliding_split_overlaps():
    text = "".join(f"word{i}. " for i in range(200))
    chunks = chunk_text(text, document_id="d", strategy="sliding", target_chars=300, overlap_chars=100)
    assert len(chunks) > 1


def test_structural_preserves_headings_and_tables():
    text = (
        "# Financials\n\n"
        "Revenue grew strongly.\n\n"
        "| metric | 2024 | 2025 |\n| --- | --- | --- |\n| revenue | 10 | 20 |\n"
        "# Risk Factors\n\n"
        "Margins may compress.\n"
    )
    chunks = chunk_text(text, document_id="d", strategy="structural", target_chars=400)
    joined = "\n".join(c.content for c in chunks)
    assert "Financials" in joined
    assert "| revenue | 10 | 20 |" in joined
    assert "Risk Factors" in joined
    # The markdown table must not be split across a row boundary.
    table_chunks = [c for c in chunks if "| revenue |" in c.content]
    assert len(table_chunks) == 1


def test_semantic_groups_related_sentences():
    text = (
        "Nvidia data center revenue grew. Nvidia AI demand accelerated. "
        "Tesla margins fell. Tesla pricing pressure increased. "
        "Apple launched a new phone."
    )
    chunks = chunk_text(text, document_id="d", strategy="semantic", target_chars=120, min_chars=20)
    assert len(chunks) >= 2


def test_detect_sections_hierarchy():
    sections = detect_sections("# A\nbody\n## B\nmore\n### C\ndeep")
    paths = [s.section_path for s in sections]
    assert "A" in paths[0]
    assert any("A › B" in p for p in paths)


def test_empty_text_yields_no_chunks():
    assert chunk_text("", document_id="d") == []
    assert chunk_text("   ", document_id="d") == []


def test_split_sentences():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]

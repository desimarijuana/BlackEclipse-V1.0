"""RingBuffer + model truncation — the bounded output store."""

from __future__ import annotations

from harness.terminal.buffer import RingBuffer, truncate_for_model


def test_sequence_is_monotonic_and_cursor_never_repeats():
    buf = RingBuffer(max_lines=1000)
    for i in range(5):
        buf.append("stdout", f"line{i}\n", "t")
    first = buf.read()
    assert first["count"] == 5
    assert [c["sequence"] for c in first["chunks"]] == [1, 2, 3, 4, 5]
    # Reading since the last cursor returns nothing until new output arrives.
    again = buf.read(since_sequence=first["nextSequence"])
    assert again["count"] == 0
    buf.append("stdout", "new\n", "t")
    delta = buf.read(since_sequence=first["nextSequence"])
    assert delta["count"] == 1
    assert delta["text"] == "new\n"


def test_stdout_and_stderr_are_never_merged():
    buf = RingBuffer()
    buf.append("stdout", "out\n", "t")
    buf.append("stderr", "err\n", "t")
    assert buf.read(stream="stdout")["text"] == "out\n"
    assert buf.read(stream="stderr")["text"] == "err\n"
    # Unfiltered read preserves both, with their stream labels.
    streams = [c["stream"] for c in buf.read()["chunks"]]
    assert streams == ["stdout", "stderr"]


def test_line_bound_drops_oldest_and_reports_it():
    buf = RingBuffer(max_lines=3)
    for i in range(6):
        buf.append("stdout", f"l{i}\n", "t")
    snap = buf.read()
    assert snap["count"] == 3
    assert snap["droppedLines"] == 3
    assert snap["totalLines"] == 6
    assert snap["text"] == "l3\nl4\nl5\n"


def test_tail_and_byte_limit():
    buf = RingBuffer()
    for i in range(10):
        buf.append("stdout", f"l{i}\n", "t")
    assert buf.read(tail=2)["text"] == "l8\nl9\n"
    # "l0\n" is 3 bytes; "l1\n" would push the total to 6, past the 4-byte cap.
    limited = buf.read(tail=10, byte_limit=4)
    assert limited["text"] == "l0\n"


def test_truncate_for_model_keeps_head_and_tail_with_a_non_json_marker():
    text = "\n".join(f"line {i}" for i in range(1000))
    rendered, truncated = truncate_for_model(text, head=5, tail=5, max_chars=10_000)
    assert truncated is True
    assert "OUTPUT TRUNCATED" in rendered
    assert rendered.startswith("line\n0"[:4]) or "line 0" in rendered
    assert "line 999" in rendered
    # The marker cannot parse as JSON.
    import json

    try:
        json.loads(rendered)
        parsed = True
    except ValueError:
        parsed = False
    assert parsed is False


def test_small_text_is_returned_untouched():
    text = "hello\nworld\n"
    rendered, truncated = truncate_for_model(text)
    assert rendered == text
    assert truncated is False


def test_a_very_long_single_line_is_clamped():
    buf = RingBuffer()
    buf.append("stdout", "x" * 100_000, "t")
    snap = buf.read()
    assert snap["count"] == 1
    assert len(snap["text"]) <= 16_384

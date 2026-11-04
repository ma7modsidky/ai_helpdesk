"""Chunking: deterministic, bounded, and readable across a split (T7.2)."""

from __future__ import annotations

from apps.knowledge.chunking import CHUNK_CHARS, CHUNK_OVERLAP_CHARS, split_body


def test_a_short_body_is_one_chunk() -> None:
    chunks = split_body("Refunds take five days.\n\nContact us if it is urgent.")

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert "five days" in chunks[0].content


def test_paragraphs_beyond_the_limit_become_separate_chunks() -> None:
    paragraph = " ".join(["word"] * 400)  # ~2,000 characters: over the limit on its own
    chunks = split_body(f"{paragraph}\n\n{paragraph}")

    assert len(chunks) >= 3
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.content) <= CHUNK_CHARS + CHUNK_OVERLAP_CHARS + 1 for chunk in chunks)


def test_chunks_overlap_so_a_split_sentence_stays_readable() -> None:
    first = "A" * CHUNK_CHARS
    second = "B" * CHUNK_CHARS
    chunks = split_body(f"{first}\n\n{second}")

    assert len(chunks) == 2
    # The tail of the first chunk is repeated at the head of the second.
    assert chunks[1].content.startswith("A" * 50)
    assert chunks[1].content.endswith("B" * 50)


def test_the_split_is_deterministic() -> None:
    body = "\n\n".join(f"Paragraph {index} " + "text " * 120 for index in range(6))

    assert split_body(body) == split_body(body)


def test_line_endings_and_runs_of_whitespace_are_normalized() -> None:
    chunks = split_body("First   line\r\nsecond line\r\n\r\nSecond paragraph")

    assert chunks[0].content == "First line second line\n\nSecond paragraph"


def test_a_blank_body_has_no_chunks() -> None:
    assert split_body("   \n\n  ") == []


def test_a_single_unbroken_token_is_cut_rather_than_looping() -> None:
    chunks = split_body("x" * (CHUNK_CHARS * 2 + 50))

    assert len(chunks) >= 3
    assert all(chunk.content for chunk in chunks)

"""Splitting an article body into retrievable chunks (T7.2, 05 §4).

Chunking is deterministic: the same body always produces the same chunks, so a reindex of an
unchanged article rewrites identical rows and a test can assert the split rather than describe
it. That property is what makes ``(article, version, chunk_index)`` a stable identity.

The rules are deliberately simple — the shape of the corpus, not a model, decides them:

- Paragraphs are the unit. A blank line is an author's own signal that the topic changed.
- Chunks are bounded by characters rather than tokens: a token count needs the provider's
  tokenizer, and being approximately right is enough to bound cost (05 §6).
- Consecutive chunks share a short overlap, so a sentence split across the boundary is still
  readable in one of them.
- A paragraph longer than the limit (a pasted log, a table) is split at whitespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Roughly 150 words: enough context for a policy paragraph, small enough that five chunks fit
# in a prompt beside the ticket without spending the output allowance.
CHUNK_CHARS = 900
CHUNK_OVERLAP_CHARS = 120

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    """One piece of a body, with the index that identifies it within its version."""

    index: int
    content: str


def split_body(body: str) -> list[Chunk]:
    """Split ``body`` into ordered chunks, or ``[]`` when there is nothing to index."""
    paragraphs = _paragraphs(body)
    if not paragraphs:
        return []

    texts = _pack(paragraphs)
    return [Chunk(index=index, content=_with_overlap(texts, index)) for index in range(len(texts))]


def _paragraphs(body: str) -> list[str]:
    """Normalize line endings and whitespace, then split on blank lines."""
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = (" ".join(block.split()) for block in _PARAGRAPH_BREAK.split(normalized))
    return [paragraph for paragraph in paragraphs if paragraph]


def _pack(paragraphs: list[str]) -> list[str]:
    """Group paragraphs into chunks no longer than :data:`CHUNK_CHARS` where possible."""
    pieces: list[str] = []
    for paragraph in paragraphs:
        pieces.extend(_split_long(paragraph))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + len(piece) + 2 <= CHUNK_CHARS:
            current = f"{current}\n\n{piece}"
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _split_long(paragraph: str) -> list[str]:
    """Break one over-long paragraph at whitespace, keeping every piece within the bound."""
    if len(paragraph) <= CHUNK_CHARS:
        return [paragraph]

    pieces: list[str] = []
    remaining = paragraph
    while len(remaining) > CHUNK_CHARS:
        window = remaining[:CHUNK_CHARS]
        cut = window.rfind(" ")
        # No space at all (a single token): cut hard rather than loop forever.
        cut = cut if cut > 0 else CHUNK_CHARS
        pieces.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _with_overlap(texts: list[str], index: int) -> str:
    """Prepend the tail of the previous chunk, so a split sentence survives in one piece."""
    if index == 0:
        return texts[0]
    previous = texts[index - 1][-CHUNK_OVERLAP_CHARS:].lstrip()
    return f"{previous} {texts[index]}".strip()

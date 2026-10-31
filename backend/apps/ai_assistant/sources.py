"""Where a draft's sources come from (T6.3, T7.2).

The draft task needs one thing from retrieval: a bounded set of published articles that belong
to the same workspace, with stable identifiers, so every citation the model returns can be
checked against what was actually offered. That seam lives here rather than inside the task so
the knowledge base (T7.1/T7.2) can fill it in without the prompt, the schema, or the endpoint
changing shape.

Until the knowledge base exists there are no published articles, and
:func:`candidates_for` returns nothing. That is not a stub to be removed later: it is the MVP's
honest answer today, and the prompt is told "no sources are available" so the draft asks for the
missing information instead of inventing policy (05 §3, FR-035).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.tickets.models import Ticket

# Retrieval stays small and predictable: the model sees a handful of articles, not a corpus
# pasted into a prompt, and the bill has a ceiling (05 §6).
MAX_SOURCES = 5


@dataclass(frozen=True)
class Source:
    """One retrieved article, as both the prompt and the response refer to it.

    ``id`` is what the model must cite and what the validator checks, so it is opaque to the
    model and stable across a reindex.
    """

    id: str
    title: str
    body: str


def candidates_for(*, ticket: Ticket) -> list[Source]:
    """Published articles in the ticket's workspace that may support a reply.

    An empty list means there is nothing to ground a draft in. The caller must not treat that as
    an error: it is the case where a cautious acknowledgement is the right answer.
    """
    # Phase 7 replaces this with a tenant-scoped query over published, current article chunks.
    # It stays a function rather than an inline empty list so the call site is already correct.
    return []

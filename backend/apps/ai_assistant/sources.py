"""Where a draft's sources come from (T6.3, T7.2, T7.4).

The draft task needs one thing from retrieval: a bounded set of published chunks that belong to
the same workspace, with stable identifiers, so every citation the model returns can be checked
against what was actually offered.

Two properties of the query below are the security boundary, not an optimisation:

- **The workspace filter is applied to the chunk rows themselves**, in the same statement that
  ranks them. Nothing from another tenant is ever selected, let alone assembled into a prompt,
  so a prompt-injection attempt in a ticket cannot reach a neighbour's article either (05 §5).
- **Only published, currently indexed text is a candidate.** A draft article, an archived one,
  and a chunk written from an older version are all invisible, which is what FR-032 and the
  version stamp on each chunk exist for.

When nothing matches, the answer is an empty list. That is not an error: the prompt is told
"no sources are available" and the model is required to ask for what it needs instead of
inventing a policy (FR-035).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F

from apps.knowledge.models import SEARCH_CONFIG, ArticleStatus, KnowledgeChunk
from apps.tickets.models import Ticket

# Retrieval stays small and predictable: the model sees a handful of chunks, not a corpus
# pasted into a prompt, and the bill has a ceiling (05 §6).
MAX_SOURCES = 5

# A ticket can be long; the query is only a bag of words for ranking, and a bounded one keeps
# the search fast and the parameter small.
MAX_QUERY_CHARS = 1_000
# More terms than this stops ranking meaningfully and starts matching everything.
MAX_QUERY_TERMS = 24

# Only these characters survive into the query. The ticket is untrusted text, and PostgreSQL's
# query syntax has operators of its own, so the words are extracted rather than escaped.
_TERM = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Source:
    """One retrieved chunk, as both the prompt and the response refer to it.

    ``id`` is the chunk, which is what the model must cite and what the validator checks: it is
    opaque, stable for one article version, and cannot be guessed into another workspace's row.

    ``article_id`` is what a citation resolves to on screen, and ``title`` is what the reader
    sees beside it. Both come from the row that was actually retrieved, never from model output.
    """

    id: str
    title: str
    body: str
    article_id: str = ""


def candidates_for(*, ticket: Ticket) -> list[Source]:
    """Published chunks in the ticket's workspace that may support a reply.

    An empty list means there is nothing to ground a draft in. The caller must not treat that as
    an error: it is the case where a cautious acknowledgement is the right answer.
    """
    text = " ".join(f"{ticket.subject} {ticket.description}".split())[:MAX_QUERY_CHARS]
    if not text:
        return []

    # Any term may match: a ticket that mentions a refund should find the refund policy even if
    # it also says "duplicate" and "twice", which the article never repeats. `plain` would AND
    # every word and find nothing; `raw` is used with terms that have already been reduced to
    # letters and digits, so no query operator can be injected.
    terms = list(dict.fromkeys(_TERM.findall(text.lower())))[:MAX_QUERY_TERMS]
    if not terms:
        return []
    query = SearchQuery(" | ".join(terms), config=SEARCH_CONFIG, search_type="raw")
    rows = (
        KnowledgeChunk.objects.filter(
            workspace_id=ticket.workspace_id,
            article__status=ArticleStatus.PUBLISHED,
            # The chunk must describe the text that is live now, not an earlier edit.
            article_version=F("article__version"),
            search_vector=query,
        )
        .annotate(rank=SearchRank(F("search_vector"), query))
        .order_by("-rank", "article_id", "chunk_index")
        .values("id", "content", "article_id", "article__title")[:MAX_SOURCES]
    )

    return [
        Source(
            id=str(row["id"]),
            article_id=str(row["article_id"]),
            title=str(row["article__title"]),
            body=str(row["content"]),
        )
        for row in rows
    ]

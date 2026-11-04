"""The indexing task (T7.2, FR-033).

Chunking is queued rather than done in the request that published the article: it walks the
whole body, writes rows, and can be retried, which is work a request should not hold a
connection for.

There is no automatic retry. Unlike a provider call there is no transient failure to absorb
here — a failure means a bug or an unavailable database — and a silent retry loop would hide
it. A failed job is visible on the article, and the editor offers a reindex button.
"""

from __future__ import annotations

import logging

from celery import shared_task

from .indexing import claim, clear_chunks, fail, is_published, replace_chunks, succeed

logger = logging.getLogger(__name__)


@shared_task
def index_article(article_id: str) -> str:
    """Build (or clear) an article's chunks and record the outcome on the article."""
    article = claim(article_id)
    if article is None:
        logger.info("Task index_article skipped: a worker already claimed this article.")
        return "skipped"

    try:
        if not is_published(article):
            clear_chunks(article)
            succeed(article, chunks=0)
            logger.info("Task index_article cleared chunks for unpublished article.")
            return "cleared"

        chunks = replace_chunks(article)
    except Exception as exc:
        # Recorded by class only, then surfaced: an unexpected failure here is not something
        # the queue should quietly retry (see the module docstring).
        fail(article, exc)
        raise

    succeed(article, chunks=chunks)
    return "succeeded"

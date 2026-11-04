"""Domain failures for the knowledge base, translated to HTTP by the views."""

from __future__ import annotations


class KnowledgeError(Exception):
    """Base class, so a handler can refuse to swallow an unrelated exception."""


class ArticleNotFound(KnowledgeError):
    """An article id that this workspace cannot see, or that does not exist.

    Unknown and foreign are the same failure on purpose: the contract treats a cross-tenant
    id as ``404`` and never as ``403`` (04 §Error behavior).
    """


class ArticleStateConflict(KnowledgeError):
    """A lifecycle command the article's current state does not allow.

    Today that is archiving an archived article and publishing an archived one: an archived
    article is reopened by editing it back into a draft, not by publishing it again.
    """

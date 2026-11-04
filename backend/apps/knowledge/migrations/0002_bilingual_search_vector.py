"""Rebuild the stored search vectors for every configured language (ADR-039).

The vector is derived data, so it is rebuilt here rather than left to a background reindex: a
migration cannot queue work, and until that work ran, articles already in the database would stay
unmatchable in Arabic. One statement per chunk keeps this file independent of the application
code, which will keep changing while this migration stays fixed.
"""

from __future__ import annotations

import operator
from functools import reduce
from typing import Any

from django.contrib.postgres.search import SearchVector
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps
from django.db.models import Value

# The configurations in use when this migration was written. Pinned here rather than imported:
# a migration has to describe the state it produced, not the state of the code today.
CONFIGS = ("english", "arabic")


def rebuild_vectors(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    chunk_model = apps.get_model("knowledge", "KnowledgeChunk")
    for chunk in chunk_model.objects.select_related("article").iterator(chunk_size=500):
        parts: list[Any] = [
            SearchVector(
                Value(chunk.article.title), Value(" "), "content", config=config
            )
            for config in CONFIGS
        ]
        chunk_model.objects.filter(pk=chunk.pk).update(
            search_vector=reduce(operator.add, parts)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(rebuild_vectors, migrations.RunPython.noop),
    ]

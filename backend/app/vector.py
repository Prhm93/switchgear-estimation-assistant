"""A column type for embeddings: pgvector's ``vector`` on PostgreSQL, JSON on SQLite (the fast test suite).

No extra library is needed: the pgvector extension (enabled by migration 0001) reads and writes vectors as text
such as ``[0.1,0.2,0.3]``. The column has no fixed size, so vectors of different embedders can be stored; a search
always filters on the embedder's name, so it never compares vectors of different sizes.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator, UserDefinedType


class PgVector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector"

    def bind_processor(self, dialect: Any):  # noqa: ANN201 - SQLAlchemy hook
        def process(value: list[float] | None) -> str | None:
            return None if value is None else "[" + ",".join(f"{float(x):.7g}" for x in value) + "]"
        return process

    def result_processor(self, dialect: Any, coltype: Any):  # noqa: ANN201 - SQLAlchemy hook
        def process(value: Any) -> list[float] | None:
            if value is None or isinstance(value, list):
                return value
            return [float(x) for x in json.loads(str(value))]
        return process


class Embedding(TypeDecorator):
    """``vector`` on PostgreSQL, JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any):  # noqa: ANN201 - SQLAlchemy hook
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PgVector())
        return dialect.type_descriptor(JSON())


def vector_literal(values: list[float]) -> str:
    """The text form pgvector reads, for a query parameter cast with ``CAST(:q AS vector)``."""
    return "[" + ",".join(f"{float(x):.7g}" for x in values) + "]"

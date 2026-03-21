# -*- coding: utf-8 -*-
"""PgVector store implementation using PostgreSQL + pgvector extension."""
import json
from typing import Any, Literal

from ._store_base import VDBStoreBase
from .._reader import Document
from .._document import DocMetadata
from ..._utils._common import _map_text_to_uuid
from ...types import Embedding


class PgVectorStore(VDBStoreBase):
    """Vector store backed by PostgreSQL with the pgvector extension.

    Each collection maps to a table. The table is auto-created on first
    ``add`` call if it does not exist.

    Requires:
        - PostgreSQL with ``CREATE EXTENSION vector`` enabled
        - ``asyncpg`` Python package
    """

    def __init__(
        self,
        connection_string: str,
        collection_name: str,
        dimensions: int,
        distance: Literal["cosine", "l2", "ip"] = "cosine",
    ) -> None:
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', collection_name):
            raise ValueError(
                f"Invalid collection_name: {collection_name!r}. "
                "Must be a valid SQL identifier.",
            )
        self.connection_string = connection_string
        self.collection_name = collection_name
        self.dimensions = dimensions
        self.distance = distance
        self._pool = None

    async def _ensure_pool(self):
        """Lazily create connection pool."""
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=1,
                max_size=5,
            )
        return self._pool

    async def _ensure_table(self) -> None:
        """Create the table and index if they do not exist."""
        pool = await self._ensure_pool()
        tbl = self.collection_name

        # Ensure pgvector extension is available
        async with pool.acquire() as conn:
            await conn.execute(
                "CREATE EXTENSION IF NOT EXISTS vector",
            )

        # Choose the index operator class based on distance metric
        ops_map = {
            "cosine": "vector_cosine_ops",
            "l2": "vector_l2_ops",
            "ip": "vector_ip_ops",
        }
        ops = ops_map.get(self.distance, "vector_cosine_ops")

        async with pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{tbl}" (
                    id          TEXT PRIMARY KEY,
                    doc_id      TEXT NOT NULL,
                    chunk_id    INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL DEFAULT 1,
                    content     JSONB NOT NULL,
                    embedding   vector({self.dimensions}) NOT NULL
                )
            """)
            # HNSW index supports max 2000 dimensions in pgvector.
            # Skip index creation for higher dimensions (uses sequential
            # scan, which is fine for small-to-medium datasets).
            if self.dimensions <= 2000:
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS "idx_{tbl}_hnsw"
                    ON "{tbl}" USING hnsw (embedding {ops})
                """)

    async def add(self, documents: list[Document], **kwargs: Any) -> None:
        """Upsert documents into the pgvector table.

        Args:
            documents (`list[Document]`):
                A list of documents with embeddings to store.
        """
        await self._ensure_table()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            for doc in documents:
                point_id = _map_text_to_uuid(
                    json.dumps(
                        {
                            "doc_id": doc.metadata.doc_id,
                            "chunk_id": doc.metadata.chunk_id,
                            "content": doc.metadata.content,
                        },
                        ensure_ascii=False,
                    ),
                )
                emb_str = (
                    "[" + ",".join(str(x) for x in doc.embedding) + "]"
                )
                await conn.execute(
                    f"""
                    INSERT INTO "{self.collection_name}"
                        (id, doc_id, chunk_id, total_chunks, content,
                         embedding)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6::vector)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                    """,
                    point_id,
                    doc.metadata.doc_id,
                    doc.metadata.chunk_id,
                    doc.metadata.total_chunks,
                    json.dumps(doc.metadata.content, ensure_ascii=False),
                    emb_str,
                )

    async def search(
        self,
        query_embedding: Embedding,
        limit: int,
        score_threshold: float | None = None,
        **kwargs: Any,
    ) -> list[Document]:
        """Search by vector similarity. Returns Documents sorted by score
        descending.

        Args:
            query_embedding (`Embedding`):
                The embedding of the query text.
            limit (`int`):
                The number of relevant documents to retrieve.
            score_threshold (`float | None`, optional):
                The threshold of the score to filter the results.
            **kwargs (`Any`):
                Other keyword arguments (unused, reserved for compatibility).
        """
        await self._ensure_table()
        pool = await self._ensure_pool()

        emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Distance operator per metric.
        # NOTE: score = 1 - distance is only a true cosine similarity for
        # the "cosine" metric.  For "l2" and "ip" the raw value is still
        # useful for ranking but not a normalised similarity.
        dist_op = {"cosine": "<=>", "l2": "<->", "ip": "<#>"}
        op = dist_op.get(self.distance, "<=>")

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, doc_id, chunk_id, total_chunks, content,
                       1 - (embedding {op} $1::vector) AS score
                FROM "{self.collection_name}"
                ORDER BY embedding {op} $1::vector
                LIMIT $2
                """,
                emb_str,
                limit,
            )

        results = []
        for row in rows:
            score = float(row["score"])
            if score_threshold is not None and score < score_threshold:
                continue
            content = row["content"]
            if isinstance(content, str):
                content = json.loads(content)
            results.append(
                Document(
                    id=row["id"],
                    score=score,
                    metadata=DocMetadata(
                        content=content,
                        doc_id=row["doc_id"],
                        chunk_id=row["chunk_id"],
                        total_chunks=row["total_chunks"],
                    ),
                ),
            )
        return results

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        """Delete documents by doc_id.

        Args:
            doc_id (str): If provided as first positional arg or kwarg,
                deletes all chunks with this doc_id.
        """
        doc_id = args[0] if args else kwargs.get("doc_id")
        if doc_id is None:
            raise ValueError("doc_id is required for delete")

        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f'DELETE FROM "{self.collection_name}" WHERE doc_id = $1',
                doc_id,
            )

    def get_client(self):
        """Return the asyncpg connection pool."""
        return self._pool

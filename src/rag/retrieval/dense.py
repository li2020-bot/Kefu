"""Dense vector retrieval using pgvector cosine similarity."""

import asyncio

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from sqlalchemy import text

from src.core.config import settings
from src.rag.ingestion.embedder import get_embedding_model



class DenseRetriever:
    """Retrieve documents using dense vector similarity (pgvector <=> operator)."""

    def __init__(self, top_k: int | None = None):
        self.top_k = top_k or settings.retrieval_top_k * 5  # Retrieve more for fusion

    async def retrieve(
        self,
        query: str,
        collection: str = "kefu_knowledge",
        namespace: str | None = None,
    ) -> list[dict]:
        """Retrieve top-k similar documents by cosine similarity.

        Uses pgvector's <=> operator for cosine distance.
        Score = 1 - (embedding <=> query_vector).
        """
        if not query:
            return []

        # Generate query embedding via SentenceTransformer (BGE)
        # BGE models need a query instruction prefix for asymmetric retrieval
        model = get_embedding_model()
        instructed_query = f"为这个句子生成表示以用于检索相关文章：{query}"
        query_vec = await asyncio.to_thread(
            model.encode,
            [instructed_query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        query_vec = query_vec[0]
        # pgvector requires vector literal: '[0.1, 0.2, ...]'
        query_vector = "[" + ",".join(str(v) for v in query_vec) + "]"

        from src.core.db import async_session_factory

        async with async_session_factory() as session:
            if namespace:
                stmt = text(
                    """
                    SELECT id::text, content, metadata, 1 - (embedding <=> :vec) AS score
                    FROM knowledge_chunks
                    WHERE metadata->>'collection' = :coll AND namespace = :ns
                    ORDER BY embedding <=> :vec
                    LIMIT :k
                    """
                )
                result = await session.execute(
                    stmt,
                    {"vec": query_vector, "coll": collection, "ns": namespace, "k": self.top_k},
                )
            else:
                stmt = text(
                    """
                    SELECT id::text, content, metadata, 1 - (embedding <=> :vec) AS score
                    FROM knowledge_chunks
                    WHERE metadata->>'collection' = :coll
                    ORDER BY embedding <=> :vec
                    LIMIT :k
                    """
                )
                result = await session.execute(
                    stmt,
                    {"vec": query_vector, "coll": collection, "k": self.top_k},
                )

            rows = result.fetchall()
            logger.info(
                "dense_retrieval",
                query=query[:50],
                top_k=self.top_k,
                namespace=namespace,
                hit_count=len(rows),
            )
            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "metadata": row[2],
                    "score": float(row[3]),
                }
                for row in rows
            ]

"""Embedding generator using BGE-small-zh-v1.5 via sentence-transformers.

BGE-small-zh-v1.5 produces 512-dimensional normalized embeddings.
Model downloads from HuggingFace on first use (lazy-load singleton).
"""

import asyncio

from sentence_transformers import SentenceTransformer

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from src.core.config import settings


# SentenceTransformer singleton — must be reused to keep consistency
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or create the shared SentenceTransformer instance.

    Uses BAAI/bge-small-zh-v1.5 — a compact Chinese-English bilingual
    embedding model that outputs 512-dim normalized vectors.
    The same instance must be used for both ingestion and retrieval.
    """
    global _embedding_model
    if _embedding_model is None:
        logger.info("loading_embedding_model", model=settings.embedding_model, dim=512)
        _embedding_model = SentenceTransformer(settings.embedding_model, local_files_only=True)
    return _embedding_model


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Generate 512-dim embeddings for a list of text chunks."""
    if not chunks:
        return []

    model = get_embedding_model()
    try:
        embeddings = await asyncio.to_thread(
            model.encode,
            chunks,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        logger.info("chunks_embedded", count=len(chunks))
        return [e.tolist() for e in embeddings]
    except Exception as e:
        logger.error("embedding_failed", error=str(e))
        raise


async def ingest_documents(
    chunks: list[str],
    metadatas: list[dict],
    namespace: str,
    collection_name: str = "kefu_knowledge",
):
    """Embed chunks and insert into pgvector knowledge_chunks table."""
    if not chunks:
        return

    embeddings = await embed_chunks(chunks)

    from src.core.db import async_session_factory
    from src.models.knowledge_chunk import KnowledgeChunk

    async with async_session_factory() as session:
        for content, embedding, meta in zip(chunks, embeddings, metadatas):
            chunk = KnowledgeChunk(
                content=content,
                embedding=embedding,
                namespace=namespace,
                metadata_={**meta, "collection": collection_name},
            )
            session.add(chunk)
        await session.commit()

    logger.info(
        "documents_ingested",
        collection=collection_name,
        namespace=namespace,
        chunk_count=len(chunks),
        embedding_dim=len(embeddings[0]) if embeddings else 0,
    )

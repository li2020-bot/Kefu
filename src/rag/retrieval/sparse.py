"""Sparse (BM25) retrieval using a pure Python BM25 implementation."""

import math
import re
from collections import Counter

import jieba
from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from sqlalchemy import text

from src.core.config import settings


def _tokenize(text: str) -> list[str]:
    """Tokenize text using jieba word segmentation.

    Handles both Chinese and English text properly.
    """
    text = text.lower()
    # jieba.cut returns a generator, convert to list
    tokens = list(jieba.cut(text))
    # Filter out empty strings and punctuation
    tokens = [t for t in tokens if t and not re.match(r"^[^\w\u4e00-\u9fff]+$", t)]
    return tokens


class SimpleBM25:
    """Pure Python BM25 implementation with char n-gram tokenization.

    BM25 formula:
      score(d, q) = sum( IDF(t) * TF(t,d) * (k1+1) / (TF(t,d) + k1*(1-b + b*|d|/avgdl)) )

    Parameters:
        k1: term frequency saturation (default 1.5)
        b:  length normalization (default 0.75)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._documents: list[list[str]] = []
        self._doc_count = 0
        self._avgdl = 0.0
        self._df: dict[str, int] = {}  # document frequency per term
        self._idf: dict[str, float] = {}

    def index(self, texts: list[str]):
        """Build the BM25 index from a list of document texts."""
        self._documents = [self._tokenize_fn(t) for t in texts]
        self._doc_count = len(self._documents)
        self._avgdl = (
            sum(len(d) for d in self._documents) / self._doc_count
            if self._doc_count > 0
            else 0
        )

        # Compute document frequencies
        self._df.clear()
        for doc in self._documents:
            unique_terms = set(doc)
            for term in unique_terms:
                self._df[term] = self._df.get(term, 0) + 1

        # Compute IDF
        self._idf.clear()
        for term, df in self._df.items():
            self._idf[term] = math.log(
                1 + (self._doc_count - df + 0.5) / (df + 0.5)
            )

    def _tokenize_fn(self, text: str) -> list[str]:
        return _tokenize(text)

    def search(self, query: str, top_k: int = 25) -> list[tuple[int, float]]:
        """Search and return list of (doc_index, score), sorted by score descending."""
        if self._doc_count == 0:
            return []

        query_tokens = self._tokenize_fn(query)
        if not query_tokens:
            return []

        scores: list[float] = [0.0] * self._doc_count

        for token in query_tokens:
            idf = self._idf.get(token, 0)
            if idf == 0:
                continue

            for i, doc in enumerate(self._documents):
                tf = doc.count(token)
                if tf == 0:
                    continue
                doc_len = len(doc)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / self._avgdl
                )
                scores[i] += idf * numerator / denominator

        # Return top_k indices sorted by score
        scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return scored[:top_k]


class SparseRetriever:
    """Retrieve documents using BM25 keyword search.

    Loads all documents from the knowledge_chunks table and builds
    a BM25 index in memory. Supports namespace filtering.
    """

    def __init__(self, top_k: int | None = None):
        self.top_k = top_k or settings.retrieval_top_k * 5
        self._index: SimpleBM25 | None = None
        self._docs: list[dict] = []  # parallel list with _index

    async def _ensure_index(self, namespace: str | None = None):
        """Load documents from pgvector and build BM25 index.

        Rebuilds if namespace changes (to filter relevant documents).
        The index is cached globally for the default (no filter) case.
        """
        # Always reload for now — simple and fast for 20 docs
        from src.core.db import async_session_factory

        async with async_session_factory() as session:
            if namespace:
                stmt = text(
                    "SELECT id, content, metadata, namespace "
                    "FROM knowledge_chunks WHERE namespace = :ns"
                )
                result = await session.execute(stmt, {"ns": namespace})
            else:
                stmt = text(
                    "SELECT id, content, metadata, namespace "
                    "FROM knowledge_chunks"
                )
                result = await session.execute(stmt)

            rows = result.fetchall()

        self._docs = [
            {
                "id": str(row[0]),
                "content": row[1],
                "metadata": row[2] or {},
                "namespace": row[3],
            }
            for row in rows
        ]

        if self._docs:
            texts = [d["content"] for d in self._docs]
            self._index = SimpleBM25()
            self._index.index(texts)
            logger.info(
                "sparse_index_built",
                doc_count=len(self._docs),
                namespace=namespace or "all",
            )
        else:
            self._index = SimpleBM25()
            logger.info("sparse_index_empty", namespace=namespace or "all")

    async def retrieve(
        self,
        query: str,
        collection: str = "kefu_knowledge",
        namespace: str | None = None,
    ) -> list[dict]:
        """Retrieve top-k documents by BM25 scoring."""
        if not query:
            return []

        await self._ensure_index(namespace)

        if self._index is None or self._index._doc_count == 0:
            return []

        results = self._index.search(query, self.top_k)

        output = []
        for doc_idx, score in results:
            if score <= 0:
                continue
            doc = self._docs[doc_idx]
            output.append({
                "id": doc["id"],
                "content": doc["content"],
                "metadata": doc["metadata"],
                "score": score,
            })

        logger.info(
            "sparse_retrieval",
            query=query[:50],
            top_k=self.top_k,
            hit_count=len(output),
        )
        return output

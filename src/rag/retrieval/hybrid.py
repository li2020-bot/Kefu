"""Hybrid retrieval with Reciprocal Rank Fusion (RRF) and optional reranking."""

import asyncio

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from src.core.config import settings
from src.rag.retrieval.dense import DenseRetriever
from src.rag.retrieval.sparse import SparseRetriever
from src.rag.retrieval.reranker import Reranker


# Reranker singleton — lazy-loaded on first use
_reranker: Reranker | None = None


def _get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker


class HybridRetriever:
    """Combines dense and sparse retrieval with RRF fusion and reranking.

    Pipeline: Dense (pgvector) + Sparse (BM25) -> RRF merge -> Rerank -> top-k
    """

    def __init__(
        self,
        fusion_k: int | None = None,
        final_top_k: int | None = None,
        use_rerank: bool = True,
    ):
        self.fusion_k = fusion_k or settings.hybrid_fusion_k
        self.final_top_k = final_top_k or settings.retrieval_top_k
        self.use_rerank = use_rerank
        self.dense = DenseRetriever()
        self.sparse = SparseRetriever()

    async def retrieve(
        self,
        query: str,
        collection: str = "kefu_knowledge",
        namespace: str | None = None,
    ) -> list[dict]:
        """Execute hybrid retrieval pipeline.

        Runs dense and sparse retrieval in parallel, fuses results
        using Reciprocal Rank Fusion, then optionally reranks.
        """
        # Retrieve more candidates for reranking if enabled
        if self.use_rerank:
            self.dense.top_k = self.final_top_k * 5
            self.sparse.top_k = self.final_top_k * 5

        dense_results, sparse_results = await asyncio.gather(
            self.dense.retrieve(query, collection, namespace),
            self.sparse.retrieve(query, collection, namespace),
        )

        # RRF fusion
        merged = self._rrf_fusion(dense_results, sparse_results)

        # Rerank to refine ordering
        if self.use_rerank and len(merged) > self.final_top_k:
            reranker = _get_reranker()
            # Give reranker more candidates for a better final selection
            candidate_count = min(len(merged), self.final_top_k * 3)
            candidates = merged[:candidate_count]
            merged = await reranker.rerank(query, candidates)
        else:
            merged = merged[: self.final_top_k]

        logger.info(
            "hybrid_retrieval",
            query=query[:50],
            dense_count=len(dense_results),
            sparse_count=len(sparse_results),
            merged_count=len(merged),
            rerank=self.use_rerank,
        )
        return merged

    def _rrf_fusion(self, dense_results: list[dict], sparse_results: list[dict]) -> list[dict]:
        """Merge results using Reciprocal Rank Fusion.

        Uses document UUID for dedup. If no id available, falls back
        to content hash.
        RRF score = sum(1 / (k + rank_i)) for each result list i.
        """
        scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}

        for rank, doc in enumerate(dense_results, 1):
            doc_id = doc.get("id") or doc.get("content", "")[:50]
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (self.fusion_k + rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = doc

        for rank, doc in enumerate(sparse_results, 1):
            doc_id = doc.get("id") or doc.get("content", "")[:50]
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (self.fusion_k + rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = doc

        # Sort by RRF score descending
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        for doc_id in sorted_ids:
            doc_map[doc_id]["rrf_score"] = scores[doc_id]

        return [doc_map[doc_id] for doc_id in sorted_ids]

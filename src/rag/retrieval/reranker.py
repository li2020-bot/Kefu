"""Cross-encoder reranker for result refinement using local model."""

import asyncio

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from sentence_transformers import CrossEncoder

from src.core.config import settings



class Reranker:
    """Rerank retrieval results using a cross-encoder model.

    Default: BGE-Reranker-v2-m3 (strong multilingual support).
    Downloads from HuggingFace on first use.
    """

    def __init__(self, model_name: str | None = None, top_n: int | None = None):
        self.model_name = model_name or settings.reranker_model
        self.top_n = top_n or settings.retrieval_top_k
        self._model: CrossEncoder | None = None

    def _get_model(self) -> CrossEncoder:
        """Lazy-load the cross-encoder model."""
        if self._model is None:
            logger.info("loading_reranker_model", model=self.model_name)
            self._model = CrossEncoder(self.model_name)
        return self._model

    async def rerank(self, query: str, documents: list[dict]) -> list[dict]:
        """Rerank documents by relevance to the query.

        Uses cross-encoder to score each (query, doc) pair,
        then re-sorts by score descending.
        """
        if not documents or not query:
            return documents

        model = self._get_model()
        pairs = [(query, doc["content"]) for doc in documents]

        try:
            scores = await asyncio.to_thread(model.predict, pairs, show_progress_bar=False)
        except Exception as e:
            logger.error("reranker_failed", error=str(e))
            return documents[: self.top_n]

        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        documents.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

        logger.info("reranker_applied", doc_count=len(documents), top_n=self.top_n)
        return documents[: self.top_n]

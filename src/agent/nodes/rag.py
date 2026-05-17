"""RAG retrieval node - retrieves relevant knowledge for the user query."""

import asyncio

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from src.agent.state import AgentState, IntentType, RetrievalResult, _get_msg_content, _get_msg_role
from src.core.config import settings
from src.rag.retrieval.hybrid import HybridRetriever



async def retrieve_knowledge(state: AgentState) -> dict:
    """Retrieve relevant documents from the knowledge base.

    Uses hybrid retrieval: dense (pgvector) + sparse (BM25)
    with RRF fusion, filtered by the active skill's knowledge namespace.
    Searches across ALL namespaces (not just the first one).
    """
    if not state.messages:
        return {"retrieved_docs": []}

    # Slot-filling: user is providing data (phone, order ID, etc.).
    # Skip vector search — raw data isn't a meaningful query for the knowledge base.
    # Keep existing retrieved_docs from the previous turn.
    if state.intent == IntentType.SLOT_FILLING:
        logger.info("rag_skipped_slot_filling")
        return {}

    # Get the last USER message content as the search query,
    # skipping any system/assistant messages added by skill_dispatch etc.
    last_msg = None
    for msg in reversed(state.messages):
        if _get_msg_role(msg) == "user":
            last_msg = msg
            break
    user_text = _get_msg_content(last_msg) if last_msg else ""

    namespaces = state.knowledge_namespaces if state.knowledge_namespaces else [None]

    try:
        retriever = HybridRetriever()

        # Query across all namespaces in parallel
        async def _retrieve_one(ns: str | None) -> list[dict]:
            return await retriever.retrieve(query=user_text, namespace=ns)

        all_results_batches = await asyncio.gather(
            *[_retrieve_one(ns) for ns in namespaces],
            return_exceptions=True,
        )

        # Merge results from all namespaces, dedup by id, keep best score
        seen_ids: set[str] = set()
        merged: list[dict] = []
        for batch in all_results_batches:
            if isinstance(batch, Exception):
                logger.warning("namespace_retrieval_failed", error=str(batch))
                continue
            for r in batch:
                rid = r.get("id") or r.get("content", "")[:50]
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                merged.append(r)

        # Sort by score descending, take top-k
        merged.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        top_k = settings.retrieval_top_k
        merged = merged[:top_k]

        retrieved_docs = []
        for r in merged:
            meta = r.get("metadata", {})
            source = meta.get("faq_id", meta.get("source", "knowledge_base"))
            retrieved_docs.append(
                RetrievalResult(
                    content=r["content"],
                    source=source,
                    score=r.get("score", 0.0),
                )
            )

        logger.info(
            "rag_retrieved",
            query_length=len(user_text),
            doc_count=len(retrieved_docs),
            namespaces=namespaces,
        )

        return {"retrieved_docs": retrieved_docs}

    except Exception as e:
        logger.warning("rag_retrieval_failed", error=str(e))
        return {"retrieved_docs": []}

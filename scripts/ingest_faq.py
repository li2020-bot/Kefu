#!/usr/bin/env python3
"""Ingest FAQ data from seed_data/faq_data.json into pgvector.

Reads 20 FAQ entries, chunks Q&A pairs, embeds with bge-m3,
and stores into the knowledge_chunks table.

Usage: python scripts/ingest_faq.py
"""

import json
import re
import sys
import asyncio
from pathlib import Path

# Ensure project root is on the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.core.db import init_db
from src.rag.ingestion.embedder import ingest_documents

# Category keyword -> namespace mapping
CATEGORY_NAMESPACE_MAP = {
    "退货": "return_policy",
    "退款": "refund_policy",
    "换货": "exchange_policy",
    "订单": "order_policy",
    "物流": "shipping_faq",
    "配送": "shipping_faq",
    "快递": "shipping_faq",
    "发票": "invoice_policy",
    "库存": "products",
    "产品": "products",
    "价格": "marketing_faq",
    "促销": "marketing_faq",
    "账户": "account_policy",
    "登录": "account_policy",
    "密码": "account_policy",
    "退货/换货": "return_policy",
    "技术": "technical_docs",
    "投诉": "complaint_policy",
    "政策": "general_policy",
    "质保": "general_policy",
    "售前": "products",
}


def _map_category_to_namespace(category: str) -> str:
    """Map a category string like '售后 > 退货 > 7天无理由' to a namespace."""
    for keyword, namespace in CATEGORY_NAMESPACE_MAP.items():
        if keyword in category:
            return namespace
    return "general"


def _fix_json_quotes(text: str) -> str:
    """Fix unescaped Chinese-style double quotes in JSON string values.

    The FAQ JSON file contains patterns like "我的订单" where
    the inner quotes are standard ASCII double-quotes that should
    be escaped. We replace inner doubles with Chinese guillemets.
    """
    result = []
    in_string = False
    escaped = False
    # Track brace depth to detect top-level strings only
    in_value = False
    brace_depth = 0

    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            result.append(ch)
            continue

        if ch == "\\":
            escaped = True
            result.append(ch)
            continue

        if ch == "{":
            brace_depth += 1
            in_value = False
            result.append(ch)
            continue
        if ch == "}":
            brace_depth -= 1
            result.append(ch)
            continue

        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                # This might be an end-of-string quote or an unescaped inner quote
                # Check: is a JSON structural character (,:}]) coming next after optional whitespace?
                rest = text[i + 1 :]
                m = re.match(r"\s*[,:}\]\s]", rest)
                if m:
                    # Looks like end of JSON string
                    in_string = False
                    result.append(ch)
                else:
                    # Inner unescaped quote — replace with fullwidth quotation mark
                    # Toggle between left and right
                    result.append("\uff02")  # Fullwidth quotation mark
                continue
        else:
            result.append(ch)

    return "".join(result)


async def main():
    faq_path = Path(__file__).resolve().parent.parent / "seed_data" / "faq_data.json"

    if not faq_path.exists():
        print(f"FAQ data not found: {faq_path}")
        sys.exit(1)

    # Read and fix malformed JSON
    raw = faq_path.read_text(encoding="utf-8")
    try:
        faqs = json.loads(raw)
    except json.JSONDecodeError:
        print("Fixing malformed JSON quotes...")
        fixed = _fix_json_quotes(raw)
        try:
            faqs = json.loads(fixed)
        except json.JSONDecodeError as e:
            print(f"Still invalid JSON after fixing: {e}")
            sys.exit(1)

    print(f"Loaded {len(faqs)} FAQ entries")

    # Ensure database table exists
    print("Initializing database...")
    await init_db()
    print("Database ready")

    # Clear existing FAQ chunks to avoid duplicates on re-ingestion
    from src.core.db import async_session_factory
    from sqlalchemy import text
    async with async_session_factory() as session:
        result = await session.execute(text("DELETE FROM knowledge_chunks"))
        await session.commit()
        print(f"Cleared {result.rowcount} existing chunks")

    chunks = []
    metadatas = []
    namespaces = []

    for faq in faqs:
        # Build a rich text chunk from Q&A
        question = faq["question"]
        answer = faq["answer"]
        synonyms = ", ".join(faq.get("synonyms", []))
        tags = ", ".join(faq.get("tags", []))
        category = faq.get("category", "")

        chunk_text = f"""问题: {question}
相似问法: {synonyms}
答案: {answer}"""

        namespace = _map_category_to_namespace(category)

        chunks.append(chunk_text)
        metadatas.append({
            "faq_id": faq["id"],
            "category": category,
            "tags": tags,
            "question": question,
            "product_scope": faq.get("product_scope", "ALL"),
            "chunk_type": "faq",
        })
        namespaces.append(namespace)

    print("Embedding chunks (this may take a few minutes on first run)...")
    print(f"Model: {settings.embedding_model}")

    # Ingest by namespace to batch related chunks together
    by_namespace: dict[str, list[int]] = {}
    for i, ns in enumerate(namespaces):
        by_namespace.setdefault(ns, []).append(i)

    total = 0
    for ns, indices in by_namespace.items():
        ns_chunks = [chunks[i] for i in indices]
        ns_metas = [metadatas[i] for i in indices]
        await ingest_documents(ns_chunks, ns_metas, namespace=ns)
        print(f"  {ns}: {len(indices)} chunks ingested")
        total += len(indices)

    print(f"\nDone. {total} chunks ingested into pgvector.")


if __name__ == "__main__":
    asyncio.run(main())

"""Document chunker - splits documents into manageable chunks."""

import re
from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from src.core.config import settings
from src.rag.ingestion.parser import Document



class Chunk:
    """A chunk of a document with source metadata."""

    def __init__(self, content: str, metadata: dict | None = None):
        self.content = content
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        source = self.metadata.get("source", "unknown")
        idx = self.metadata.get("chunk_index", 0)
        return f"Chunk(source={source}, index={idx}, length={len(self.content)})"


class RecursiveTextChunker:
    """Split text recursively using separators in order of priority.

    Strategy: paragraph -> sentence -> word -> character
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        self._separators = ["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""]

    def split(self, document: Document) -> list[Chunk]:
        """Split a document into chunks."""
        content = document.content
        if not content.strip():
            return []

        chunks = self._recursive_split(content)
        results = []

        for i, chunk_text in enumerate(chunks):
            chunk_metadata = {
                **document.metadata,
                "chunk_index": i,
                "chunk_count": len(chunks),
                "char_start": content.find(chunk_text) if i == 0 else -1,
            }
            results.append(Chunk(content=chunk_text.strip(), metadata=chunk_metadata))

        logger.info(
            "document_chunked",
            source=document.metadata.get("source", "unknown"),
            original_length=len(content),
            chunk_count=len(results),
        )
        return results

    def _recursive_split(self, text: str) -> list[str]:
        """Recursively split text by the most appropriate separator."""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        # Try each separator in order
        for separator in self._separators:
            if separator == "":
                # Last resort: character-level split
                return self._char_split(text)

            splits = text.split(separator)
            if len(splits) <= 1:
                continue

            # Merge splits to form chunks
            chunks = self._merge_splits(splits, separator)
            if chunks:
                return chunks

        return [text]

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        """Merge splits into chunks of appropriate size."""
        chunks = []
        current_chunk_parts: list[str] = []
        current_length = 0

        for split in splits:
            split_len = len(split)
            sep_len = len(separator) if current_chunk_parts else 0

            if current_length + split_len + sep_len > self.chunk_size and current_chunk_parts:
                chunks.append(separator.join(current_chunk_parts))

                # Build overlap by keeping last part
                overlap_text = separator.join(current_chunk_parts)
                overlap_start = max(0, len(overlap_text) - self.chunk_overlap)
                overlap_content = overlap_text[overlap_start:]

                current_chunk_parts = [overlap_content] if overlap_content.strip() else []
                current_length = len(overlap_content)

            current_chunk_parts.append(split)
            current_length += split_len + sep_len

        if current_chunk_parts:
            chunks.append(separator.join(current_chunk_parts))

        return chunks

    def _char_split(self, text: str) -> list[str]:
        """Character-level split as last resort."""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - self.chunk_overlap
        return chunks


class FAQChunker:
    """Specialized chunker for FAQ-style documents (Q&A pairs)."""

    def split(self, document: Document) -> list[Chunk]:
        """Split FAQ document by Q&A pairs."""
        content = document.content

        # Pattern: Q: / A: or Question / Answer or FAQ item separators
        qa_pattern = r"(?:Q[:：]|问[:：]|问题[:：]|FAQ-\w+.*?\n)"
        parts = re.split(qa_pattern, content)

        chunks = []
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            chunk_metadata = {
                **document.metadata,
                "chunk_index": i,
                "chunk_type": "faq",
            }
            chunks.append(Chunk(content=part.strip(), metadata=chunk_metadata))

        return chunks

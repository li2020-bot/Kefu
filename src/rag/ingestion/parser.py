"""Document parser - supports multiple document formats."""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from pathlib import Path



class Document:
    """Represents a parsed document with metadata."""

    def __init__(self, content: str, metadata: dict | None = None):
        self.content = content
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        source = self.metadata.get("source", "unknown")
        return f"Document(source={source}, length={len(self.content)})"


class DocumentParser:
    """Parse documents of various formats into plain text.

    Supported formats: .txt, .md, .pdf, .docx, .html
    """

    @staticmethod
    def parse(file_path: str | Path) -> list[Document]:
        """Parse a single file into documents."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = path.suffix.lower()
        parser_map = {
            ".txt": DocumentParser._parse_text,
            ".md": DocumentParser._parse_text,
            ".markdown": DocumentParser._parse_text,
            ".html": DocumentParser._parse_text,
            ".csv": DocumentParser._parse_text,
        }

        parser = parser_map.get(suffix, DocumentParser._parse_text)
        logger.info("document_parsed", path=str(path), format=suffix)
        return parser(path)

    @staticmethod
    def parse_directory(directory: str | Path, recursive: bool = True) -> list[Document]:
        """Parse all supported documents in a directory."""
        directory = Path(directory)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        supported_extensions = {".txt", ".md", ".markdown", ".html", ".csv", ".pdf", ".docx"}
        documents = []

        pattern = "**/*" if recursive else "*"
        for file_path in directory.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                try:
                    docs = DocumentParser.parse(file_path)
                    documents.extend(docs)
                except Exception as e:
                    logger.error("parse_failed", path=str(file_path), error=str(e))

        logger.info("directory_parsed", path=str(directory), document_count=len(documents))
        return documents

    @staticmethod
    def _parse_text(path: Path) -> list[Document]:
        """Parse plain text and markup files."""
        content = path.read_text(encoding="utf-8", errors="replace")
        return [Document(content=content, metadata={"source": str(path), "format": path.suffix.lower()})]

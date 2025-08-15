"""Utilities for extracting plain text from various document formats.

Currently supported:
 - Plain text-like formats (.txt, .md, .csv, .log)
 - PDF (via pdfminer.six)
 - DOCX (via python-docx)

If a required library is missing the caller receives a clear RuntimeError instructing them to
add the needed dependency to requirements.txt.
"""

from typing import Optional
import os


def read_text_from_file(path: str) -> str:
    """Return extracted text from the given file path.

    Strategy:
        - Choose fast direct read for plain-text extensions.
        - For PDF and DOCX leverage specialized parsers.
        - Fallback: attempt a generic UTF-8 decode with replacement.

    Args:
        path: Path to the document on disk.
    Returns:
        Extracted text (may be empty string if parser yields nothing).
    Raises:
        RuntimeError: when an optional dependency is missing for a given format.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".log"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if ext == ".pdf":
        try:
            import pdfminer.high_level  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "pdfminer.six is required to read PDFs. Add 'pdfminer.six' to requirements.txt"
            ) from e
        return pdfminer.high_level.extract_text(path) or ""
    if ext == ".docx":
        try:
            import docx  # type: ignore  # python-docx
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "python-docx is required to read .docx files. Add 'python-docx' to requirements.txt"
            ) from e
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    # Fallback: treat as text
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

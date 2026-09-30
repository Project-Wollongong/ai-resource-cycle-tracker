"""Deterministic PDF text extraction for P03 input; no interpretation is performed."""
from pathlib import Path
from pypdf import PdfReader


def extract_pdf_text(path: Path) -> tuple[str, int]:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(page.rstrip() for page in pages).strip()
    if not text:
        raise ValueError("PDF contains no extractable text")
    return text + "\n", len(reader.pages)

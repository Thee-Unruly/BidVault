"""
detector.py
───────────
Auto-detects document type and decides which extraction path to use.
Handles: digital PDF, scanned PDF, Word (.docx), plain text.
"""

import os
from enum import Enum
from dataclasses import dataclass
from pathlib import Path


class DocType(str, Enum):
    DIGITAL_PDF  = "digital_pdf"    # selectable text, no OCR needed
    SCANNED_PDF  = "scanned_pdf"    # image-only pages, OCR required
    MIXED_PDF    = "mixed_pdf"      # some pages digital, some scanned
    WORD         = "word"           # .docx
    TEXT         = "text"           # .txt


@dataclass
class DetectionResult:
    doc_type: DocType
    page_count: int
    needs_ocr: bool
    confidence: float               # 0-1: how confident we are in the detection
    notes: str = ""


def detect(file_path: str) -> DetectionResult:
    """
    Inspect the file and return what kind of document it is.
    This runs BEFORE any extraction — it tells the pipeline which
    extractor to route the document to.
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    if ext in (".docx", ".doc"):
        return DetectionResult(
            doc_type   = DocType.WORD,
            page_count = _estimate_word_pages(file_path),
            needs_ocr  = False,
            confidence = 1.0,
        )

    if ext == ".txt":
        return DetectionResult(
            doc_type   = DocType.TEXT,
            page_count = 1,
            needs_ocr  = False,
            confidence = 1.0,
        )

    if ext == ".pdf":
        return _detect_pdf(file_path)

    raise ValueError(f"Unsupported file type: {ext}")


def _detect_pdf(file_path: str) -> DetectionResult:
    """
    Inspect each page of the PDF.
    A page is considered "digital" if pdfplumber extracts
    meaningful text from it (> 30 chars). Otherwise it's scanned.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Run: pip install pdfplumber")

    digital_pages = 0
    scanned_pages = 0

    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        # Sample up to 10 pages to keep detection fast
        sample = pdf.pages[:min(10, page_count)]

        for page in sample:
            text = page.extract_text() or ""
            # Strip whitespace and check meaningful content
            clean = text.strip().replace("\n", "").replace(" ", "")
            if len(clean) > 30:
                digital_pages += 1
            else:
                scanned_pages += 1

    total_sampled = digital_pages + scanned_pages
    if total_sampled == 0:
        return DetectionResult(
            doc_type   = DocType.SCANNED_PDF,
            page_count = page_count,
            needs_ocr  = True,
            confidence = 0.7,
            notes      = "Empty pages — assuming scanned",
        )

    digital_ratio = digital_pages / total_sampled

    if digital_ratio >= 0.9:
        return DetectionResult(
            doc_type   = DocType.DIGITAL_PDF,
            page_count = page_count,
            needs_ocr  = False,
            confidence = digital_ratio,
        )
    elif digital_ratio <= 0.1:
        return DetectionResult(
            doc_type   = DocType.SCANNED_PDF,
            page_count = page_count,
            needs_ocr  = True,
            confidence = 1 - digital_ratio,
        )
    else:
        return DetectionResult(
            doc_type   = DocType.MIXED_PDF,
            page_count = page_count,
            needs_ocr  = True,           # OCR needed for the scanned pages
            confidence = 0.85,
            notes      = f"{scanned_pages}/{total_sampled} sampled pages are scanned",
        )


def _estimate_word_pages(file_path: str) -> int:
    """Rough page estimate for Word docs (300 words per page)."""
    try:
        from docx import Document
        doc   = Document(file_path)
        words = sum(len(p.text.split()) for p in doc.paragraphs)
        return max(1, words // 300)
    except Exception:
        return 1

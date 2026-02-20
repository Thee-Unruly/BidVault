"""
chunker.py
──────────
Splits extracted text into chunks suitable for embedding.

Strategy (in priority order):
  1. Structure-aware splitting  — splits at [H1]/[H2] heading markers
                                   preserved by the Word extractor.
                                   Keeps logical sections together.
  2. Semantic splitting         — splits at double newlines (paragraph breaks).
                                   Works well for digital PDFs.
  3. Token-based fallback       — splits at token limit with overlap.
                                   Last resort for dense, unstructured text.

Each chunk carries a section_hint — the nearest preceding heading —
which is used to set the section_type metadata field.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# Chunk size targets (in characters — approximating tokens at ~4 chars/token)
CHUNK_SIZE     = 2000   # ~500 tokens
CHUNK_OVERLAP  = 300    # ~75 tokens — ensures context continuity at boundaries
MIN_CHUNK_SIZE = 200    # Discard chunks smaller than this


@dataclass
class Chunk:
    text: str
    index: int                          # position in document (0-based)
    section_hint: str = ""              # nearest heading before this chunk
    chunk_method: str = ""              # which splitting strategy was used
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)


def chunk(text: str, source_type: str = "unknown") -> list[Chunk]:
    """
    Main entry point. Returns a list of Chunk objects.
    Automatically selects the best chunking strategy for the text.
    """
    if not text or not text.strip():
        return []

    # Try structure-aware first (Word docs with headings)
    if _has_heading_markers(text):
        chunks = _structure_aware_split(text)
        if len(chunks) >= 2:
            return _assign_indices(chunks, "structure_aware")

    # Try paragraph-based (clean PDFs)
    chunks = _paragraph_split(text)
    if len(chunks) >= 2:
        return _assign_indices(chunks, "paragraph")

    # Fall back to token-based with overlap
    chunks = _token_split(text)
    return _assign_indices(chunks, "token_based")


# ── STRATEGY 1: STRUCTURE-AWARE ───────────────────────────────────────────────

def _has_heading_markers(text: str) -> bool:
    return bool(re.search(r"\[H[123]\]", text))


def _structure_aware_split(text: str) -> list[Chunk]:
    """
    Split at heading markers [H1], [H2], [H3].
    Each heading starts a new chunk. If a section is too long,
    it gets further split by token-based method.
    """
    # Split on heading markers, keeping the marker with its section
    parts = re.split(r"(\[H[123]\][^\n]*\n)", text)

    chunks   = []
    current_heading = ""
    current_text    = ""

    for part in parts:
        heading_match = re.match(r"\[H([123])\] (.*)\n", part)

        if heading_match:
            # Save previous section before starting new one
            if current_text.strip():
                chunks.extend(
                    _split_if_too_long(current_text.strip(), current_heading)
                )
            level   = heading_match.group(1)
            heading = heading_match.group(2).strip()
            current_heading = f"H{level}: {heading}"
            current_text    = part
        else:
            current_text += part

    # Don't forget the last section
    if current_text.strip():
        chunks.extend(
            _split_if_too_long(current_text.strip(), current_heading)
        )

    return [c for c in chunks if len(c.text.strip()) >= MIN_CHUNK_SIZE]


# ── STRATEGY 2: PARAGRAPH-BASED ──────────────────────────────────────────────

def _paragraph_split(text: str) -> list[Chunk]:
    """
    Split on double newlines (paragraph breaks).
    Groups short paragraphs together to hit the target chunk size.
    """
    paragraphs = re.split(r"\n\n+", text)

    chunks        = []
    current_text  = ""
    current_hint  = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Detect if this paragraph looks like a heading
        if _looks_like_heading(para):
            if current_text.strip():
                chunks.append(Chunk(text=current_text.strip(), index=0, section_hint=current_hint))
            current_hint = para
            current_text = para + "\n\n"
        else:
            current_text += para + "\n\n"
            # Flush when we've hit the target size
            if len(current_text) >= CHUNK_SIZE:
                chunks.append(Chunk(text=current_text.strip(), index=0, section_hint=current_hint))
                # Keep last paragraph as overlap context
                current_text = para + "\n\n"

    if current_text.strip():
        chunks.append(Chunk(text=current_text.strip(), index=0, section_hint=current_hint))

    return [c for c in chunks if len(c.text.strip()) >= MIN_CHUNK_SIZE]


def _looks_like_heading(text: str) -> bool:
    """
    Heuristic: a paragraph that is short, has no sentence-ending punctuation,
    and is not all lowercase is probably a heading or section title.
    """
    text = text.strip()
    if len(text) > 120:
        return False
    if text.endswith((".", ",", ";")):
        return False
    if text == text.lower():
        return False
    return bool(re.match(r"^[A-Z0-9]", text))


# ── STRATEGY 3: TOKEN-BASED ───────────────────────────────────────────────────

def _token_split(text: str, heading: str = "") -> list[Chunk]:
    """
    Naive sliding window split. Last resort for dense unstructured text.
    Tries to split at sentence boundaries within the window.
    """
    chunks = []
    start  = 0

    while start < len(text):
        end = start + CHUNK_SIZE

        if end < len(text):
            # Try to find a sentence boundary to split cleanly
            boundary = _find_sentence_boundary(text, end)
            end = boundary if boundary else end

        chunk_text = text[start:end].strip()
        if len(chunk_text) >= MIN_CHUNK_SIZE:
            chunks.append(Chunk(text=chunk_text, index=0, section_hint=heading))

        # Move forward by chunk size minus overlap
        start += (CHUNK_SIZE - CHUNK_OVERLAP)

    return chunks


def _find_sentence_boundary(text: str, pos: int, search_window: int = 200) -> Optional[int]:
    """Find the nearest sentence end (. ! ?) near pos, searching backwards."""
    search_start = max(0, pos - search_window)
    segment      = text[search_start:pos]
    matches      = list(re.finditer(r"[.!?]\s", segment))
    if matches:
        last_match = matches[-1]
        return search_start + last_match.end()
    return None


# ── UTILITIES ─────────────────────────────────────────────────────────────────

def _split_if_too_long(text: str, heading: str) -> list[Chunk]:
    """If a section is larger than CHUNK_SIZE, apply token splitting to it."""
    if len(text) <= CHUNK_SIZE:
        return [Chunk(text=text, index=0, section_hint=heading)]
    return _token_split(text, heading)


def _assign_indices(chunks: list[Chunk], method: str) -> list[Chunk]:
    for i, chunk in enumerate(chunks):
        chunk.index        = i
        chunk.chunk_method = method
    return chunks


# ── SECTION TYPE INFERENCE ────────────────────────────────────────────────────

# Maps heading keywords → standardised section_type for metadata
SECTION_TYPE_PATTERNS = {
    "executive summary":    "executive_summary",
    "technical approach":   "methodology",
    "methodology":          "methodology",
    "approach":             "methodology",
    "work plan":            "work_plan",
    "workplan":             "work_plan",
    "team":                 "team",
    "personnel":            "team",
    "key experts":          "team",
    "qualifications":       "team",
    "past experience":      "past_experience",
    "previous experience":  "past_experience",
    "similar assignments":  "past_experience",
    "firm profile":         "company_profile",
    "company profile":      "company_profile",
    "about us":             "company_profile",
    "financial":            "financial",
    "budget":               "financial",
    "cost":                 "financial",
    "eligibility":          "requirements",
    "mandatory":            "requirements",
    "evaluation criteria":  "requirements",
    "terms of reference":   "scope",
    "scope of work":        "scope",
    "background":           "background",
    "introduction":         "background",
    "context":              "background",
}


def infer_section_type(section_hint: str) -> str:
    """
    Given a section heading, return a standardised section_type.
    Falls back to 'general' if no match found.
    """
    hint_lower = section_hint.lower()
    for pattern, section_type in SECTION_TYPE_PATTERNS.items():
        if pattern in hint_lower:
            return section_type
    return "general"

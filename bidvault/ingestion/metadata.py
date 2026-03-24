"""
bidvault/ingestion/metadata.py
───────────────────────────────
Generic metadata engine for the Document Ingestion Pipeline.
Every document chunk is stored with core fields (file_name, chunk_index, etc.)
and a flexible 'extra' dictionary for domain-specific metadata.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


@dataclass
class DocumentMetadata:
    """
    Core metadata for a document chunk.
    This class is domain-agnostic. Domain-specific fields (like 'sector' or 'client')
    are stored in the flexible 'extra' dictionary.
    """

    # ── UNIVERSAL CORE FIELDS ────────────────────────────────────────────────
    document_id:    str = ""     # Parent document UUID from the database
    file_name:      str = ""     # Original file name
    chunk_index:    int = 0      # Position in the document
    chunk_method:   str = ""     # Strategy (structure, paragraph, etc.)
    section_hint:   str = ""     # Raw heading text above chunk
    section_type:   str = "general" # Standardized type (mapped by analyzer)

    # ── EXTRA STORAGE ────────────────────────────────────────────────────────
    # For any domain-specific data (e.g. bid-specific, legal-specific)
    extra: Dict[str, Any] = field(default_factory=dict)

    def validate(self):
        """Basic universal validation. Domain validation happens in analyzers."""
        if not self.document_id:
            # We don't raise as it's often set later by the store
            pass

    def to_dict(self) -> dict:
        """
        Merge core fields and 'extra' fields into a flat dictionary
        for storage in pgvector JSONB.
        """
        d = asdict(self)
        extra = d.pop("extra", {})
        
        # Merge extra fields into the top-level
        # Filter None and empty strings for cleaner indexing
        result = {k: v for k, v in d.items() if v is not None and v != ""}
        for k, v in extra.items():
            if v is not None and v != "":
                result[k] = v
                
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentMetadata":
        """Reconstitute from a dictionary (e.g. from vector store results)."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        
        core_data = {}
        extra_data = {}
        
        for k, v in d.items():
            if k in valid_fields and k != "extra":
                core_data[k] = v
            else:
                extra_data[k] = v
                
        return cls(**core_data, extra=extra_data)


# ── INTERFACE ───────────────────────────────────────────────────────────────

class DocumentAnalyzer:
    """
    Interface for domain-specific metadata extraction.
    Inherit from this and pass it to the IngestionPipeline to support new document types.
    """
    def analyze(self, text: str, initial_meta: dict) -> dict:
        """Return a dictionary of extra metadata elements from text."""
        return {}

    def infer_section_type(self, hint: str) -> str:
        """Standardized mapping for section headings."""
        return "general"

"""
metadata.py
───────────
Defines the metadata schema for every chunk stored in the vector DB.
Also provides utilities to validate and enrich metadata.

Good metadata is what separates useful retrieval from noise.
Every chunk must have at minimum: source_type, year, sector.
Without these, the retrieval agent cannot filter intelligently.

USAGE:
    meta = DocumentMetadata(
        source_type = "proposal",
        sector      = "health",
        donor       = "usaid",
        year        = 2023,
        won         = True,
        client      = "Ministry of Health Kenya",
    )
    meta.validate()   # raises if required fields missing
    d = meta.to_dict()  # for storage
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    PROPOSAL     = "proposal"       # Past bid / proposal document
    RFP          = "rfp"            # Incoming tender / RFP
    CV           = "cv"             # Consultant CV
    PROJECT      = "project"        # Project description / completion report
    CERTIFICATE  = "certificate"    # Compliance document
    METHODOLOGY  = "methodology"    # Firm's standard methodology library
    FINANCIAL    = "financial"      # Financial proposal / budget template
    OTHER        = "other"


class Sector(str, Enum):
    HEALTH          = "health"
    EDUCATION       = "education"
    INFRASTRUCTURE  = "infrastructure"
    GOVERNANCE      = "governance"
    ENVIRONMENT     = "environment"
    AGRICULTURE     = "agriculture"
    FINANCE         = "finance"
    ICT             = "ict"
    WATER           = "water"
    ENERGY          = "energy"
    HUMANITARIAN    = "humanitarian"
    GENERAL         = "general"     # multi-sector or unclear


class Donor(str, Enum):
    WORLD_BANK  = "world_bank"
    USAID       = "usaid"
    AFDB        = "afdb"            # African Development Bank
    EU          = "eu"
    GIZ         = "giz"
    DFID        = "dfid"            # now FCDO
    FCDO        = "fcdo"
    UN          = "un"
    GOK         = "gok"             # Government of Kenya
    COUNTY      = "county"          # Kenya county government
    PRIVATE     = "private"         # Private sector client
    NGO         = "ngo"
    OTHER       = "other"


class SectionType(str, Enum):
    EXECUTIVE_SUMMARY  = "executive_summary"
    METHODOLOGY        = "methodology"
    WORK_PLAN          = "work_plan"
    TEAM               = "team"
    PAST_EXPERIENCE    = "past_experience"
    COMPANY_PROFILE    = "company_profile"
    FINANCIAL          = "financial"
    REQUIREMENTS       = "requirements"
    SCOPE              = "scope"
    BACKGROUND         = "background"
    GENERAL            = "general"


# ── METADATA SCHEMA ───────────────────────────────────────────────────────────

@dataclass
class DocumentMetadata:
    """
    Metadata attached to every chunk stored in the vector DB.
    Required fields are enforced by validate().
    """

    # ── REQUIRED ──────────────────────────────────────────────────────────────
    source_type:    str     = ""    # SourceType value
    year:           int     = 0     # Year the source document was written

    # ── STRONGLY RECOMMENDED ──────────────────────────────────────────────────
    sector:         str     = "general"     # Sector enum value
    donor:          str     = "other"       # Donor enum value
    section_type:   str     = "general"     # SectionType value — set by chunker

    # ── DOCUMENT-LEVEL ────────────────────────────────────────────────────────
    document_id:    str     = ""    # UUID of the parent document in PostgreSQL
    file_name:      str     = ""    # Original file name
    client:         str     = ""    # Client organisation name
    country:        str     = "Kenya"
    language:       str     = "en"

    # ── PROPOSAL-SPECIFIC ─────────────────────────────────────────────────────
    won:                Optional[bool]  = None  # True/False/None(unknown)
    tender_value_usd:   Optional[float] = None  # Contract value if known
    bid_reference:      str             = ""    # RFP reference number

    # ── CHUNK-LEVEL ───────────────────────────────────────────────────────────
    chunk_index:    int     = 0     # Position within the document
    chunk_method:   str     = ""    # Which chunking strategy was used
    section_hint:   str     = ""    # Raw heading text above this chunk

    # ── SHAREPOINT ────────────────────────────────────────────────────────────
    sharepoint_item_id: str = ""    # Graph API item ID (if sourced from SharePoint)
    sharepoint_url:     str = ""    # Direct URL back to the file

    def validate(self):
        """Raises ValueError if required fields are missing."""
        errors = []
        if not self.source_type:
            errors.append("source_type is required")
        if not self.year or self.year < 2000:
            errors.append("year is required and must be >= 2000")
        if errors:
            raise ValueError(f"Metadata validation failed: {'; '.join(errors)}")

    def to_dict(self) -> dict:
        """Serialise to a flat dict for storage (pgvector metadata column)."""
        d = asdict(self)
        # Remove None values — pgvector JSON doesn't handle None well
        return {k: v for k, v in d.items() if v is not None and v != ""}

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentMetadata":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)


# ── AUTO-TAGGING ──────────────────────────────────────────────────────────────

# Keywords that indicate sectors — used to auto-tag if sector not provided
SECTOR_KEYWORDS = {
    Sector.HEALTH:          ["health", "hospital", "clinic", "malaria", "hiv", "nutrition", "maternal", "medical", "disease"],
    Sector.EDUCATION:       ["education", "school", "learning", "literacy", "teacher", "curriculum", "university"],
    Sector.INFRASTRUCTURE:  ["road", "bridge", "construction", "infrastructure", "transport", "highway", "building"],
    Sector.GOVERNANCE:      ["governance", "public sector", "ministry", "government", "policy", "institutional", "county"],
    Sector.ENVIRONMENT:     ["environment", "climate", "conservation", "biodiversity", "forest", "carbon", "emission"],
    Sector.AGRICULTURE:     ["agriculture", "farming", "crop", "livestock", "food security", "irrigation", "agri"],
    Sector.WATER:           ["water", "sanitation", "wash", "sewage", "borehole", "irrigation"],
    Sector.ENERGY:          ["energy", "electricity", "solar", "renewable", "power", "grid", "generation"],
    Sector.ICT:             ["ict", "technology", "digital", "software", "system", "data", "information"],
}

DONOR_KEYWORDS = {
    Donor.WORLD_BANK:  ["world bank", "ibrd", "ida", "wb "],
    Donor.USAID:       ["usaid", "u.s. agency", "united states agency"],
    Donor.AFDB:        ["african development bank", "afdb", "adb "],
    Donor.EU:          ["european union", "eu ", "european commission"],
    Donor.GIZ:         ["giz", "deutsche gesellschaft", "german"],
    Donor.FCDO:        ["fcdo", "foreign commonwealth", "dfid", "uk aid"],
    Donor.UN:          ["united nations", "undp", "unicef", "unhcr", "unfpa", "who "],
    Donor.GOK:         ["government of kenya", "republic of kenya", "gok", "ministry of"],
    Donor.COUNTY:      ["county government", "county of", "nairobi county", "mombasa county"],
}


def auto_tag_source_type(text: str) -> str:
    """Infer source_type from document text."""
    text_lower = text.lower()
    
    if any(kw in text_lower for kw in ["proposal", "bid", "tender response", "bidding document"]):
        return SourceType.PROPOSAL
    if any(kw in text_lower for kw in ["rfp", "request for proposal", "invitation to tender", "tender notice"]):
        return SourceType.RFP
    if any(kw in text_lower for kw in ["curriculum vitae", "resume", "personal profile", "years of experience"]):
        return SourceType.CV
    if any(kw in text_lower for kw in ["act", "gazette", "chapter", "law of kenya"]):
        return SourceType.OTHER # or add LEGAL to SourceType
    
    return SourceType.OTHER


def auto_tag_sector(text: str) -> str:
    """Infer sector from document text using keyword matching."""
    text_lower = text.lower()
    scores = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        score = sum(text_lower.count(kw) for kw in keywords)
        if score > 0:
            scores[sector] = score
    if not scores:
        return Sector.GENERAL
    return max(scores, key=scores.get)


def auto_tag_donor(text: str) -> str:
    """Infer donor from document text using keyword matching."""
    text_lower = text.lower()
    for donor, keywords in DONOR_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return donor
    return Donor.OTHER


def extract_year(text: str) -> int:
    """Find the most likely year in the first few pages."""
    import re
    import datetime
    
    # Look for 4-digit years between 1990 and current year + 1
    current_year = datetime.datetime.now().year
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text[:5000])
    
    if not years:
        return current_year
        
    # Count occurrences and return the most common one that is reasonable
    from collections import Counter
    year_counts = Counter([int(y) for y in years if 1990 <= int(y) <= current_year + 1])
    
    if not year_counts:
        return current_year
        
    return year_counts.most_common(1)[0][0]


def enrich_metadata(meta: DocumentMetadata, text: str) -> DocumentMetadata:
    """
    Auto-fill missing metadata fields by analysing the document text.
    Call this after creating a metadata object if the user hasn't
    provided fields manually.
    """
    if not meta.source_type or meta.source_type == "other":
        meta.source_type = auto_tag_source_type(text)

    if not meta.year or meta.year == 0:
        meta.year = extract_year(text)

    if meta.sector == "general" or not meta.sector:
        meta.sector = auto_tag_sector(text)

    if meta.donor == "other" or not meta.donor:
        meta.donor = auto_tag_donor(text)

    return meta

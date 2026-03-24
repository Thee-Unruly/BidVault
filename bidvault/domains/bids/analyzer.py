"""
bidvault/domains/bids/analyzer.py
───────────────────────────────
Specialized logic for the "Bidding" domain.
Relocated from the core ingestion pipeline to allow for generalization.
"""

from enum import Enum
from typing import Optional, List
import re
from collections import Counter
import datetime

# ── ENUMS ─────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    PROPOSAL     = "proposal"
    RFP          = "rfp"
    CV           = "cv"
    PROJECT      = "project"
    CERTIFICATE  = "certificate"
    METHODOLOGY  = "methodology"
    FINANCIAL    = "financial"
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
    GENERAL         = "general"

class Donor(str, Enum):
    WORLD_BANK  = "world_bank"
    USAID       = "usaid"
    AFDB        = "afdb"
    EU          = "eu"
    GIZ         = "giz"
    FCDO        = "fcdo"
    UN          = "un"
    GOK         = "gok"
    COUNTY      = "county"
    PRIVATE     = "private"
    NGO         = "ngo"
    OTHER       = "other"

# ── KEYWORDS ──────────────────────────────────────────────────────────────────

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

BID_SECTION_PATTERNS = {
    "executive summary":    "executive_summary",
    "technical approach":   "methodology",
    "methodology":          "methodology",
    "approach":             "methodology",
    "work plan":            "work_plan",
    "team":                 "team",
    "past experience":      "past_experience",
    "firm profile":         "company_profile",
    "financial":            "financial",
    "budget":               "financial",
    "requirements":         "requirements",
    "scope of work":        "scope",
    "background":           "background",
}

# ── LOGIC ───────────────────────────────────────────────────────────────────

def auto_tag_sector(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        score = sum(text_lower.count(kw) for kw in keywords)
        if score > 0: scores[sector] = score
    return max(scores, key=scores.get) if scores else Sector.GENERAL

def auto_tag_donor(text: str) -> str:
    text_lower = text.lower()
    for donor, keywords in DONOR_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return donor
    return Donor.OTHER

def extract_year(text: str) -> int:
    current_year = datetime.datetime.now().year
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", text[:5000])
    if not years: return current_year
    year_counts = Counter([int(y) for y in years if 1990 <= int(y) <= current_year + 1])
    return year_counts.most_common(1)[0][0] if year_counts else current_year

class BidAnalyzer:
    """The 'Bid' domain adapter. Replicates the legacy bid-specific logic."""

    def analyze(self, text: str, initial_meta: dict) -> dict:
        """
        Takes raw text and returns a dictionary of 'extra' metadata
        discovered via bid-specific heuristics.
        """
        extra = {}
        
        # Sector auto-tagging
        if not initial_meta.get("sector") or initial_meta.get("sector") == "general":
            extra["sector"] = auto_tag_sector(text)
        
        # Donor auto-tagging
        if not initial_meta.get("donor") or initial_meta.get("donor") == "other":
            extra["donor"] = auto_tag_donor(text)
            
        # Year extraction
        if not initial_meta.get("year"):
            extra["year"] = extract_year(text)

        return extra

    def infer_section_type(self, hint: str) -> str:
        """Maps a heading to a bid-related section type."""
        hint_lower = hint.lower()
        for pattern, section_type in BID_SECTION_PATTERNS.items():
            if pattern in hint_lower:
                return section_type
        return "general"

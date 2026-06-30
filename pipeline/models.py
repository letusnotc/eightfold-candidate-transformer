"""
Pydantic v2 canonical schema for the Eightfold Candidate Transformer.
All pipeline stages produce and consume these models.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: list[str] = []


class Skill(BaseModel):
    name: str                  # canonical name
    confidence: float          # 0.0 – 1.0
    sources: list[str]         # which sources mentioned it


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None   # YYYY-MM
    end: Optional[str] = None     # YYYY-MM or "present"
    summary: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None


class ProvenanceEntry(BaseModel):
    field: str
    source: str    # e.g. "csv", "github", "resume_pdf"
    method: str    # e.g. "direct", "regex", "gliner_ner", "heuristic"


class CanonicalProfile(BaseModel):
    candidate_id: str
    full_name: Optional[str] = None
    emails: list[str] = []
    phones: list[str] = []          # E.164 format
    location: Location = Location()
    links: Links = Links()
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[Skill] = []
    experience: list[Experience] = []
    education: list[Education] = []
    provenance: list[ProvenanceEntry] = []
    overall_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def make_candidate_id(primary_email: Optional[str] = None, full_name: Optional[str] = None) -> str:
    """
    Deterministic SHA-256-based candidate ID.
    Primary key: email (lowercased).  Fallback: full_name.
    """
    key = (primary_email or "").strip().lower() or (full_name or "").strip().lower()
    if not key:
        key = "unknown"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

"""
Notes Parser — extracts candidate data from free-text recruiter notes.

Reuses the GLiNER + regex pipeline from resume_parser.
Also extracts sentiment indicators from recruiter language.
Confidence: 0.60 (least structured source).
"""

from __future__ import annotations

import logging
import re

from pipeline.parsers.resume_parser import (
    _extract_emails,
    _extract_phones,
    _extract_links,
    _extract_gliner_entities,
    _clean_name,
    _extract_skills_from_text,
)
from pipeline.normalizers.skills import load_canonical_skills

logger = logging.getLogger(__name__)

# Sentiment indicator patterns
_POSITIVE_RE = re.compile(
    r"\b(strong|excellent|great|impressive|recommend|positive|enthusiastic|"
    r"well.prepared|good fit|outstanding|top|stellar|fantastic|ideal)\b",
    re.IGNORECASE,
)
_NEGATIVE_RE = re.compile(
    r"\b(concern|weak|not a fit|poor|slow|hesitant|unclear|lacks|missing|"
    r"does not|didn't|disappointed|below|struggle|risk)\b",
    re.IGNORECASE,
)
_RECOMMENDATION_RE = re.compile(
    r"\b(recommend|move to|proceed|advance|next round|technical round|schedule)\b",
    re.IGNORECASE,
)


def _extract_sentiment(text: str) -> dict:
    """
    Extract basic sentiment signals from recruiter text.
    Returns {"positive": bool, "negative": bool, "recommended": bool}
    """
    return {
        "positive": bool(_POSITIVE_RE.search(text)),
        "negative": bool(_NEGATIVE_RE.search(text)),
        "recommended": bool(_RECOMMENDATION_RE.search(text)),
    }


def parse_notes(path: str) -> dict:
    """
    Parse recruiter notes from a plain .txt file at *path*.

    Returns:
      {"source": "notes", "data": {...extracted fields...}}

    Never raises — returns empty data dict on any error.
    """
    empty = {"source": "notes", "data": {}}

    if not path:
        return empty

    # Read text
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except FileNotFoundError:
        logger.warning("Notes file not found: %r", path)
        return empty
    except Exception as e:
        logger.warning("Notes file read error for %r: %s", path, e)
        return empty

    if not text.strip():
        logger.warning("Notes file is empty: %r", path)
        return empty

    canonical_map = load_canonical_skills()

    # Layer 1 — Regex
    emails = _extract_emails(text)
    phones = _extract_phones(text)
    links = _extract_links(text)

    # Layer 2 — GLiNER NER
    gliner_entities = _extract_gliner_entities(text)

    # Layer 3 — Name
    full_name = None
    person_names = [t for t, _ in gliner_entities.get("person name", [])]
    if person_names:
        best_name = max(gliner_entities.get("person name", []), key=lambda x: x[1], default=(None, 0))[0]
        if best_name:
            full_name = _clean_name(best_name)

    # Layer 4 — Skills keyword scan
    skills = _extract_skills_from_text(text, canonical_map)
    for label in ("programming language", "software framework", "skill"):
        for skill_text, _ in gliner_entities.get(label, []):
            from pipeline.normalizers.skills import canonicalize_skill
            canon = canonicalize_skill(skill_text, canonical_map)
            if canon and canon not in skills:
                skills.append(canon)

    # Sentiment
    sentiment = _extract_sentiment(text)

    # Build data dict
    data: dict = {}

    if full_name:
        data["full_name"] = full_name
    if emails:
        data["emails"] = emails
    if phones:
        data["phones"] = phones
    if links.get("github"):
        data["github"] = links["github"]
    if links.get("linkedin"):
        data["linkedin"] = links["linkedin"]
    if skills:
        data["skills"] = skills

    # Store sentiment as metadata (not a canonical field, but useful for the UI)
    data["_sentiment"] = sentiment

    logger.debug("Notes parser extracted %d fields from %r", len(data), path)
    return {"source": "notes", "data": data}

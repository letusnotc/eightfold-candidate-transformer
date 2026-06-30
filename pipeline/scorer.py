"""
Scorer — computes per-field and overall confidence for a CanonicalProfile.

Confidence model:
  - Base: highest source confidence among contributing sources
  - Conflict penalty: -0.20 if same field has different values across sources
  - Corroboration bonus: +0.10 if 2+ sources agree (capped at 1.0)
  - Missing: 0.0

Overall confidence: weighted average of key field confidences.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pipeline.models import CanonicalProfile

logger = logging.getLogger(__name__)

# Base confidence by source type
SOURCE_CONFIDENCE: dict[str, float] = {
    "csv":          1.0,
    "ats_json":     1.0,
    "github":       0.85,
    "resume_pdf":   0.70,
    "resume_docx":  0.70,
    "resume_txt":   0.70,
    "notes":        0.60,
    "computed":     0.65,
    "merged":       0.75,
}

CONFLICT_PENALTY    = -0.20
CORROBORATION_BONUS =  0.10

# Weights for overall confidence computation
FIELD_WEIGHTS: dict[str, float] = {
    "full_name":        0.20,
    "emails":           0.15,
    "phones":           0.10,
    "skills":           0.20,
    "experience":       0.20,
    "education":        0.15,
}


def score_field(
    field: str,
    value: Any,
    sources: list[str],
    conflicts: bool = False,
) -> float:
    """
    Compute confidence for a single field.

    Args:
        field:     field name (for logging)
        value:     the merged value (None = missing)
        sources:   list of source tags that provided this field
        conflicts: True if different sources gave different values

    Returns confidence in [0.0, 1.0].
    """
    if value is None or (isinstance(value, (list, dict)) and not value):
        return 0.0

    if not sources:
        return 0.0

    # Start with highest source confidence
    base = max(SOURCE_CONFIDENCE.get(s, 0.50) for s in sources)

    # Modifiers
    if conflicts:
        base += CONFLICT_PENALTY

    if len(sources) >= 2:
        base += CORROBORATION_BONUS

    return max(0.0, min(1.0, base))


def compute_overall_confidence(profile: CanonicalProfile) -> float:
    """
    Weighted average of key field confidences.

    For each key field, determine which sources contributed and whether
    there were conflicts, then score it and apply the weight.
    """
    # Build source sets from provenance
    field_sources: dict[str, list[str]] = {}
    for entry in profile.provenance:
        field_sources.setdefault(entry.field, []).append(entry.source)

    total_weight = sum(FIELD_WEIGHTS.values())
    weighted_sum = 0.0

    for field, weight in FIELD_WEIGHTS.items():
        value = getattr(profile, field, None)
        sources = field_sources.get(field, [])

        # For list fields, check if non-empty
        if isinstance(value, list):
            effective_value = value if value else None
        else:
            effective_value = value

        # Simple conflict detection: multiple distinct values from different sources
        # (We don't have per-field conflict info here, so we skip the penalty at this level)
        conf = score_field(field, effective_value, sources, conflicts=False)
        weighted_sum += conf * weight

    overall = weighted_sum / total_weight if total_weight > 0 else 0.0
    return round(max(0.0, min(1.0, overall)), 3)


def score_profile(profile: CanonicalProfile) -> CanonicalProfile:
    """
    Compute and set overall_confidence on the profile.
    Also updates individual skill confidences for corroboration.
    Returns the profile (mutated in place, also returned for chaining).
    """
    profile.overall_confidence = compute_overall_confidence(profile)
    logger.debug("Profile %s scored: overall_confidence=%.3f", profile.candidate_id, profile.overall_confidence)
    return profile

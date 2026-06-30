"""
Merger — combines extracted records from multiple sources into a single CanonicalProfile.

Source priority (lower index = higher trust):
  csv > ats_json > github > resume_pdf > resume_docx > resume_txt > notes

Merge rules:
  - emails/phones: union, deduplicated
  - full_name: highest-priority source wins
  - skills: union by canonical name, tracking all source mentions
  - experience: union (no dedup), sorted start desc
  - education: union, deduplicated by institution+degree
  - location: highest-priority source wins per sub-field
  - headline: github bio > CSV title > ATS title
  - links: union, per-link-type priority
  - candidate_id: hash of primary email or name
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from pipeline.models import (
    CanonicalProfile, Education, Experience, Links, Location,
    ProvenanceEntry, Skill, make_candidate_id,
)
from pipeline.normalizers.date import normalize_date, extract_years_experience
from pipeline.normalizers.location import normalize_location
from pipeline.normalizers.phone import normalize_phones
from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills

logger = logging.getLogger(__name__)

# Source priority (index 0 = highest trust)
SOURCE_PRIORITY = ["csv", "ats_json", "github", "resume_pdf", "resume_docx", "resume_txt", "notes"]

CONTACT_FIELD_PRIORITY  = ["csv", "ats_json", "resume_pdf", "resume_docx", "resume_txt", "github", "notes"]
PROFESSIONAL_FIELD_PRIORITY = ["github", "resume_pdf", "resume_docx", "ats_json", "csv", "notes"]


def _source_rank(source: str, priority: list[str]) -> int:
    """Lower = higher priority. Unknown sources get lowest priority."""
    try:
        return priority.index(source)
    except ValueError:
        return len(priority)


def _pick_field(
    field_name: str,
    records: list[dict],
    priority_list: list[str],
    provenance: list[ProvenanceEntry],
    method: str = "direct",
) -> Optional[Any]:
    """
    Pick the best value for a scalar field from records using priority_list.
    Records records a ProvenanceEntry for the winning value.
    """
    best_value = None
    best_rank = len(priority_list) + 1
    best_source = None

    for rec in records:
        source = rec.get("source", "unknown")
        value = rec.get("data", {}).get(field_name)
        if value is None:
            continue
        rank = _source_rank(source, priority_list)
        if rank < best_rank:
            best_rank = rank
            best_value = value
            best_source = source

    if best_value is not None and best_source is not None:
        provenance.append(ProvenanceEntry(field=field_name, source=best_source, method=method))

    return best_value


def _merge_emails(records: list[dict], provenance: list[ProvenanceEntry]) -> list[str]:
    """Union of all emails across sources, deduplicated, lowercased."""
    seen: set[str] = set()
    result: list[str] = []
    for rec in records:
        source = rec.get("source", "unknown")
        raw_emails = rec.get("data", {}).get("emails", [])
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]
        for e in raw_emails:
            cleaned = str(e).strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
                provenance.append(ProvenanceEntry(field="emails", source=source, method="direct"))
    return result


def _merge_phones(records: list[dict], provenance: list[ProvenanceEntry]) -> list[str]:
    """Union of all phones across sources, E.164 normalized, deduplicated."""
    all_raw: list[tuple[str, str]] = []  # (raw_phone, source)
    for rec in records:
        source = rec.get("source", "unknown")
        raw_phones = rec.get("data", {}).get("phones", [])
        if isinstance(raw_phones, str):
            raw_phones = [raw_phones]
        for p in raw_phones:
            all_raw.append((str(p).strip(), source))

    seen: set[str] = set()
    result: list[str] = []
    for raw_phone, source in all_raw:
        normalized = None
        # Try normalizing phone
        from pipeline.normalizers.phone import normalize_phone
        normalized = normalize_phone(raw_phone)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
            provenance.append(ProvenanceEntry(field="phones", source=source, method="direct"))
        elif not normalized and raw_phone not in seen:
            # Keep unnormalized as fallback
            seen.add(raw_phone)
            result.append(raw_phone)
            provenance.append(ProvenanceEntry(field="phones", source=source, method="heuristic"))

    return result


def _merge_skills(records: list[dict], provenance: list[ProvenanceEntry]) -> list[Skill]:
    """
    Union of all skills across sources.
    Skills with the same canonical name are merged; all source mentions tracked.
    """
    canonical_map = load_canonical_skills()
    skills_by_name: dict[str, Skill] = {}

    for rec in records:
        source = rec.get("source", "unknown")
        raw_skills = rec.get("data", {}).get("skills", [])
        if isinstance(raw_skills, str):
            raw_skills = [s.strip() for s in raw_skills.split(",") if s.strip()]

        for raw in raw_skills:
            canon = canonicalize_skill(str(raw), canonical_map)
            if not canon:
                continue
            if canon in skills_by_name:
                existing = skills_by_name[canon]
                if source not in existing.sources:
                    existing.sources.append(source)
                    # Boost confidence for corroboration
                    existing.confidence = min(1.0, existing.confidence + 0.10)
            else:
                # Base confidence by source type
                from pipeline.scorer import SOURCE_CONFIDENCE
                base_conf = SOURCE_CONFIDENCE.get(source, 0.60)
                skills_by_name[canon] = Skill(name=canon, confidence=base_conf, sources=[source])

    if skills_by_name:
        provenance.append(ProvenanceEntry(field="skills", source="merged", method="union"))

    # Sort by confidence desc
    return sorted(skills_by_name.values(), key=lambda s: s.confidence, reverse=True)


def _merge_experience(records: list[dict], provenance: list[ProvenanceEntry]) -> list[Experience]:
    """Union of all experience entries, sorted by start date descending."""
    all_exp: list[Experience] = []
    seen_keys: set[tuple] = set()

    for rec in records:
        source = rec.get("source", "unknown")
        raw_exps = rec.get("data", {}).get("experience", [])
        if not isinstance(raw_exps, list):
            continue

        for e in raw_exps:
            if not isinstance(e, dict):
                continue
            start = normalize_date(e.get("start") or e.get("_raw_context", "")) if e.get("start") else None
            end_raw = e.get("end")
            end = "present" if end_raw and str(end_raw).lower() in {"present", "current", "now"} else normalize_date(end_raw) if end_raw else None

            exp = Experience(
                company=e.get("company"),
                title=e.get("title"),
                start=start,
                end=end,
                summary=e.get("summary"),
            )

            # Dedup key
            key = (exp.company or "", exp.title or "", exp.start or "")
            if key not in seen_keys:
                seen_keys.add(key)
                all_exp.append(exp)
                provenance.append(ProvenanceEntry(field="experience", source=source, method="heuristic"))

    # Sort by start date descending (most recent first)
    def sort_key(exp: Experience) -> str:
        return exp.start or "0000-00"

    return sorted(all_exp, key=sort_key, reverse=True)


def _merge_education(records: list[dict], provenance: list[ProvenanceEntry]) -> list[Education]:
    """Union of all education entries, deduplicated by institution+degree."""
    seen_keys: set[tuple] = set()
    result: list[Education] = []

    for rec in records:
        source = rec.get("source", "unknown")
        raw_edus = rec.get("data", {}).get("education", [])
        if not isinstance(raw_edus, list):
            continue

        for e in raw_edus:
            if not isinstance(e, dict):
                continue
            edu = Education(
                institution=e.get("institution"),
                degree=e.get("degree"),
                field=e.get("field"),
                end_year=e.get("end_year"),
            )
            key = (edu.institution or "", edu.degree or "")
            if key not in seen_keys:
                seen_keys.add(key)
                result.append(edu)
                provenance.append(ProvenanceEntry(field="education", source=source, method="heuristic"))

    return result


def _merge_location(records: list[dict], provenance: list[ProvenanceEntry]) -> Location:
    """Highest-priority source wins per sub-field."""
    location = Location()

    for field_name in ("city", "region", "country"):
        for priority_source in CONTACT_FIELD_PRIORITY:
            for rec in records:
                if rec.get("source") != priority_source:
                    continue
                raw_loc = rec.get("data", {}).get("location")
                if not raw_loc:
                    continue
                parsed = normalize_location(str(raw_loc))
                value = parsed.get(field_name)
                if value:
                    setattr(location, field_name, value)
                    provenance.append(
                        ProvenanceEntry(field=f"location.{field_name}", source=priority_source, method="heuristic")
                    )
                    break
            else:
                continue
            break

    return location


def _merge_links(records: list[dict], provenance: list[ProvenanceEntry]) -> Links:
    """Union of links; prefer github source for github link, etc."""
    links = Links()

    for rec in records:
        source = rec.get("source", "unknown")
        data = rec.get("data", {})

        if not links.github and data.get("github"):
            links.github = data["github"]
            provenance.append(ProvenanceEntry(field="links.github", source=source, method="direct"))

        if not links.linkedin and data.get("linkedin"):
            links.linkedin = data["linkedin"]
            provenance.append(ProvenanceEntry(field="links.linkedin", source=source, method="direct"))

        if not links.portfolio and data.get("portfolio"):
            links.portfolio = data["portfolio"]
            provenance.append(ProvenanceEntry(field="links.portfolio", source=source, method="direct"))

        other = data.get("links_other", [])
        if other:
            for url in other:
                if url not in links.other:
                    links.other.append(url)

    return links


def _merge_headline(records: list[dict], provenance: list[ProvenanceEntry]) -> Optional[str]:
    """github bio > resume headline > ats_json title > csv title > notes"""
    priority = ["github", "resume_pdf", "resume_docx", "resume_txt", "ats_json", "csv", "notes"]
    return _pick_field("headline", records, priority, provenance, method="direct")


def merge_profiles(extracted_records: list[dict]) -> CanonicalProfile:
    """
    Merge a list of extracted records into a single CanonicalProfile.

    Each record: {"source": str, "data": dict}
    """
    provenance: list[ProvenanceEntry] = []

    if not extracted_records:
        logger.warning("No records to merge — returning empty profile")
        return CanonicalProfile(candidate_id=make_candidate_id())

    # Emails & phones
    emails = _merge_emails(extracted_records, provenance)
    phones = _merge_phones(extracted_records, provenance)

    # Full name (contact priority)
    full_name = _pick_field("full_name", extracted_records, CONTACT_FIELD_PRIORITY, provenance)

    # Candidate ID
    candidate_id = make_candidate_id(
        primary_email=emails[0] if emails else None,
        full_name=full_name,
    )

    # Location
    location = _merge_location(extracted_records, provenance)

    # Links
    links = _merge_links(extracted_records, provenance)

    # Headline
    headline = _merge_headline(extracted_records, provenance)
    # Also try title from ATS/CSV if no headline
    if not headline:
        headline = _pick_field("title", extracted_records, PROFESSIONAL_FIELD_PRIORITY, provenance)

    # Skills
    skills = _merge_skills(extracted_records, provenance)

    # Experience
    experience = _merge_experience(extracted_records, provenance)

    # Education
    education = _merge_education(extracted_records, provenance)

    # Years experience: try explicit field first, then compute from experience
    years_exp: Optional[float] = _pick_field(
        "years_experience", extracted_records, PROFESSIONAL_FIELD_PRIORITY, provenance, method="direct"
    )
    if years_exp is None and experience:
        exp_dicts = [e.model_dump() for e in experience]
        years_exp = extract_years_experience(exp_dicts)
        if years_exp is not None:
            provenance.append(ProvenanceEntry(field="years_experience", source="computed", method="heuristic"))
    if years_exp is not None:
        try:
            years_exp = float(years_exp)
        except (ValueError, TypeError):
            years_exp = None

    profile = CanonicalProfile(
        candidate_id=candidate_id,
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=links,
        headline=headline,
        years_experience=years_exp,
        skills=skills,
        experience=experience,
        education=education,
        provenance=provenance,
        overall_confidence=0.0,  # Scorer will fill this in
    )

    logger.debug(
        "Merged profile: id=%s name=%r emails=%d skills=%d",
        profile.candidate_id, profile.full_name, len(profile.emails), len(profile.skills),
    )
    return profile

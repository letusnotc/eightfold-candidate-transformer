"""
Resume Parser — extracts candidate data from PDF and DOCX files.

Layered extraction pipeline:
  1. Text extraction (pdfplumber for PDF, python-docx for DOCX)
  2. Regex for emails, URLs, LinkedIn, GitHub (highest confidence)
  3. GLiNER NER for names, orgs, titles, degrees, skills
  4. nameparser for human name cleaning
  5. Skills keyword scan against canonical map
  6. phonenumbers.PhoneNumberMatcher for phone numbers

GLiNER model is loaded once at module level (slow first load, fast reuse).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from pipeline.normalizers.phone import normalize_phone
from pipeline.normalizers.skills import load_canonical_skills

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
EMAIL_RE    = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}")
URL_RE      = re.compile(r"https?://[^\s<>\"]+")
GITHUB_RE   = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([\w\-]+)(?:/[\w\-]*)*")
LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)"   # full URL
    r"|linkedin\s*:\s*(?:https?://(?:www\.)?linkedin\.com/in/)?([\w\-]+)",  # "LinkedIn: slug"
    re.IGNORECASE,
)

# Lines containing these keywords are education entries, not work experience
_EDUCATION_LINE_RE = re.compile(
    r"\b(?:school|university|college|institute|b\.tech|b\.e\.?|m\.tech|mba|"
    r"ph\.?d|class\s+\d+|cgpa|gpa|cbse|icse|diploma|bachelor|master|expected"
    r"|b\.sc|m\.sc|12th|10th|public\s+school|high\s+school|hsc|ssc)\b",
    re.IGNORECASE,
)

# Experience date ranges like "Jan 2021 - Present", "2018 – 2020"
DATE_RANGE_RE = re.compile(
    r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})"
    r"\s*[-–—to]+\s*"
    r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}|Present|Current|Now)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# GLiNER — load once at module level
# ---------------------------------------------------------------------------
_GLINER_MODEL = None
_GLINER_LABELS = [
    "person name",
    "organization",
    "job title",
    "university",
    "degree",
    "programming language",
    "software framework",
    "skill",
    "city",
    "country",
]


def _get_gliner():
    global _GLINER_MODEL
    if _GLINER_MODEL is not None:
        return _GLINER_MODEL
    try:
        from gliner import GLiNER
        logger.info("Loading GLiNER model (first time — may take a moment)...")
        _GLINER_MODEL = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
        logger.info("GLiNER model loaded.")
    except Exception as e:
        logger.warning("GLiNER not available: %s", e)
        _GLINER_MODEL = None
    return _GLINER_MODEL


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text_pdf(path: str) -> str:
    try:
        import pdfplumber
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n".join(pages)
    except Exception as e:
        logger.warning("PDF text extraction failed for %r: %s", path, e)
        return ""


def _extract_text_docx(path: str) -> str:
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception as e:
        logger.warning("DOCX text extraction failed for %r: %s", path, e)
        return ""


def _extract_text_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        logger.warning("TXT text extraction failed for %r: %s", path, e)
        return ""


def extract_text(path: str) -> str:
    """Dispatch to the right extractor based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _extract_text_pdf(path)
    elif ext == ".docx":
        return _extract_text_docx(path)
    elif ext in (".txt", ".text", ""):
        return _extract_text_txt(path)
    else:
        logger.warning("Unsupported resume file extension: %r", ext)
        return ""


# ---------------------------------------------------------------------------
# Entity extraction layers
# ---------------------------------------------------------------------------

def _extract_emails(text: str) -> list[str]:
    return list({m.lower() for m in EMAIL_RE.findall(text)})


def _extract_phones(text: str) -> list[str]:
    try:
        import phonenumbers
        results: list[str] = []
        seen: set[str] = set()
        for match in phonenumbers.PhoneNumberMatcher(text, "US"):
            e164 = normalize_phone(match.raw_string, "US")
            if e164 and e164 not in seen:
                seen.add(e164)
                results.append(e164)
        # Also try IN region if US found nothing
        if not results:
            for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
                e164 = normalize_phone(match.raw_string, "IN")
                if e164 and e164 not in seen:
                    seen.add(e164)
                    results.append(e164)
        return results
    except Exception as e:
        logger.debug("Phone extraction error: %s", e)
        return []


def _extract_links(text: str) -> dict:
    links: dict = {}
    github_m = GITHUB_RE.search(text)
    if github_m:
        links["github"] = f"https://github.com/{github_m.group(1)}"

    linkedin_m = LINKEDIN_RE.search(text)
    if linkedin_m:
        slug = linkedin_m.group(1) or linkedin_m.group(2)
        if slug:
            links["linkedin"] = f"https://linkedin.com/in/{slug}"

    # Other URLs
    all_urls = URL_RE.findall(text)
    other: list[str] = []
    for url in all_urls:
        if "linkedin.com" not in url and "github.com" not in url:
            other.append(url)
    if other:
        links["other"] = other

    return links


def _extract_gliner_entities(text: str) -> dict:
    """Run GLiNER on the first 2000 chars and return grouped entities."""
    model = _get_gliner()
    if model is None:
        return {}

    snippet = text[:2000]
    try:
        entities = model.predict_entities(snippet, _GLINER_LABELS)
    except Exception as e:
        logger.warning("GLiNER prediction failed: %s", e)
        return {}

    grouped: dict[str, list[tuple[str, float]]] = {}
    for ent in entities:
        label = ent["label"]
        text_val = ent["text"].strip()
        score = float(ent.get("score", 0.7))
        grouped.setdefault(label, []).append((text_val, score))

    return grouped


def _clean_name(raw_name: str) -> str:
    """Use nameparser for cleaning, fallback to raw."""
    try:
        from nameparser import HumanName
        parsed = HumanName(raw_name)
        cleaned = str(parsed).strip()
        return cleaned if cleaned else raw_name
    except Exception:
        return raw_name


def _extract_skills_from_text(text: str, canonical_map: dict) -> list[str]:
    """Scan full text for all known skill aliases."""
    text_lower = text.lower()
    found: list[str] = []
    seen: set[str] = set()

    for alias, canonical in canonical_map.items():
        # Word-boundary match to avoid partial matches
        pattern = r"(?<![a-zA-Z0-9\-])" + re.escape(alias) + r"(?![a-zA-Z0-9\-])"
        if re.search(pattern, text_lower) and canonical not in seen:
            seen.add(canonical)
            found.append(canonical)

    return found


def _extract_experience(text: str) -> list[dict]:
    """Heuristic: find date ranges and the surrounding line as experience entry."""
    experiences: list[dict] = []

    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = DATE_RANGE_RE.search(line)
        if m:
            # Skip lines that look like education entries (schools, degrees, CGPA, etc.)
            if _EDUCATION_LINE_RE.search(line):
                continue
            start_raw = m.group(1)
            end_raw = m.group(2)

            # Try to get company/title from surrounding lines
            context_line = line.strip()
            # Look for "Title — Company (date)" or "Company · Title · date"
            exp: dict = {
                "start": start_raw,
                "end": end_raw if end_raw.lower() not in {"present", "current", "now"} else "present",
                "_raw_context": context_line,
            }

            # Try to extract company and title from the context
            # Pattern: "Title — Company" or "Company - Title"
            dash_parts = re.split(r"\s*[—\-–]\s*", re.sub(r"\(.*?\)", "", context_line))
            dash_parts = [p.strip() for p in dash_parts if p.strip()]
            if len(dash_parts) >= 2:
                # Convention: usually "Title — Company (date)"
                exp["title"] = dash_parts[0]
                exp["company"] = dash_parts[1]

            experiences.append(exp)

    return experiences


_SCHOOL_LINE_RE = re.compile(
    r"^(.+?(?:school|college|institute|university|iit|nit|iiit)[^\n,]*)"
    r"\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_education(text: str, gliner_entities: dict) -> list[dict]:
    """Extract education from GLiNER university/degree entities + pattern matching."""
    education: list[dict] = []
    seen_names: set[str] = set()

    unis = [t for t, _ in gliner_entities.get("university", [])]
    degrees = [t for t, _ in gliner_entities.get("degree", [])]

    for i, uni in enumerate(unis):
        key = uni.lower()[:20]
        if key in seen_names:
            continue
        seen_names.add(key)

        edu: dict = {"institution": uni}
        if i < len(degrees):
            edu["degree"] = degrees[i]

        year_m = re.search(re.escape(uni[:15]) + r".{0,80}(\b20\d{2}|\b19\d{2})", text, re.IGNORECASE)
        if year_m:
            try:
                edu["end_year"] = int(year_m.group(1))
            except ValueError:
                pass

        education.append(edu)

    # Fallback: catch schools/colleges GLiNER missed via line pattern
    for m in _SCHOOL_LINE_RE.finditer(text):
        name = m.group(1).strip()
        key = name.lower()[:20]
        if key in seen_names:
            continue
        seen_names.add(key)

        edu = {"institution": name}
        # Try to find end year nearby
        year_m = re.search(re.escape(name[:15]) + r".{0,120}(\b20\d{2}|\b19\d{2})", text, re.IGNORECASE)
        if year_m:
            try:
                edu["end_year"] = int(year_m.group(1))
            except ValueError:
                pass

        education.append(edu)

    return education


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_resume(path: str, source_tag: str = "resume") -> dict:
    """
    Parse a resume (PDF, DOCX, or TXT) at *path*.

    Returns:
      {"source": source_tag, "data": {...extracted fields...}}

    Never raises — returns empty data dict on any error.
    """
    empty = {"source": source_tag, "data": {}}

    if not path:
        return empty

    # Determine source tag from extension if not overridden
    ext = os.path.splitext(path)[1].lower()
    if source_tag == "resume":
        if ext == ".pdf":
            source_tag = "resume_pdf"
        elif ext == ".docx":
            source_tag = "resume_docx"
        elif ext == ".txt":
            source_tag = "resume_txt"

    text = extract_text(path)
    if not text.strip():
        logger.warning("No text extracted from resume: %r", path)
        return {"source": source_tag, "data": {}}

    canonical_map = load_canonical_skills()

    # Layer 1 — Regex
    emails = _extract_emails(text)
    phones = _extract_phones(text)
    links = _extract_links(text)

    # Layer 2 — GLiNER NER
    gliner_entities = _extract_gliner_entities(text)

    # Layer 3 — Name cleaning
    full_name = None
    person_names = [t for t, _ in gliner_entities.get("person name", [])]
    if person_names:
        # Take the best-scoring one (first after model sorts by score)
        best_name = max(gliner_entities.get("person name", []), key=lambda x: x[1], default=(None, 0))[0]
        if best_name:
            full_name = _clean_name(best_name)

    # Fallback: first line of text often contains the name
    if not full_name:
        first_line = text.strip().split("\n")[0].strip()
        # Heuristic: first line < 50 chars and no @ means it could be a name
        if first_line and len(first_line) < 50 and "@" not in first_line and "http" not in first_line:
            # Make sure it's not a section header (all caps)
            if not first_line.isupper():
                full_name = _clean_name(first_line)

    # Layer 2 — GLiNER orgs/titles
    orgs = [t for t, _ in gliner_entities.get("organization", [])]
    titles = [t for t, _ in gliner_entities.get("job title", [])]
    headline = titles[0] if titles else None

    # Layer 4 — Skills keyword scan
    skills = _extract_skills_from_text(text, canonical_map)

    # Also add GLiNER skills/languages
    for label in ("programming language", "software framework", "skill"):
        for skill_text, _ in gliner_entities.get(label, []):
            from pipeline.normalizers.skills import canonicalize_skill
            canon = canonicalize_skill(skill_text, canonical_map)
            if canon and canon not in skills:
                skills.append(canon)

    # Experience
    experience = _extract_experience(text)

    # Education
    education = _extract_education(text, gliner_entities)

    # Location from GLiNER
    location = None
    cities = [t for t, _ in gliner_entities.get("city", [])]
    countries = [t for t, _ in gliner_entities.get("country", [])]
    if cities or countries:
        location = ", ".join(cities[:1] + countries[:1]) if (cities or countries) else None

    # Build data dict
    data: dict = {}

    if full_name:
        data["full_name"] = full_name
    if emails:
        data["emails"] = emails
    if phones:
        data["phones"] = phones
    if links:
        if "github" in links:
            data["github"] = links["github"]
        if "linkedin" in links:
            data["linkedin"] = links["linkedin"]
        if "other" in links:
            data["links_other"] = links["other"]
    if headline:
        data["headline"] = headline
    if skills:
        data["skills"] = skills
    if experience:
        data["experience"] = experience
    if education:
        data["education"] = education
    if location:
        data["location"] = location

    logger.debug("Resume parser (%s) extracted %d fields from %r", source_tag, len(data), path)
    return {"source": source_tag, "data": data}

"""
ATS JSON Parser — flexible field mapping from arbitrary ATS JSON blobs.

Strategy:
  1. Flatten nested JSON to dot-notation keys
  2. Try alias map (fast, deterministic, zero cost)
  3. For remaining unrecognized fields, call LLM mapper if GEMINI_API_KEY set
  4. Combine first_name + last_name if full_name not found
  5. Return unrecognized_fields list for caller feedback
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Alias map: canonical key → list of known ATS field name variants
FIELD_MAP: dict[str, list[str]] = {
    "full_name": [
        "name", "fullname", "full_name", "candidate_name", "applicant_name",
        "candidatename", "applicantname", "fullName", "candidateName",
        "applicantName", "candidate", "applicant",
    ],
    "first_name": [
        "first_name", "firstname", "firstName", "given_name", "givenName",
        "fname",
    ],
    "last_name": [
        "last_name", "lastname", "lastName", "surname", "family_name",
        "familyName", "lname",
    ],
    "emails": [
        "email", "emailaddress", "email_address", "contact_email",
        "contactemail", "email_id", "emailid", "emailAddress", "contactEmail",
        "mail", "e-mail", "e_mail",
    ],
    "phones": [
        "phone", "phonenumber", "phone_number", "mobile", "cell",
        "mobilenumber", "cellphone", "contact_number", "contactnumber",
        "phoneNumber", "mobileNumber", "contactNumber", "telephone", "tel",
    ],
    "title": [
        "title", "jobtitle", "job_title", "current_title", "position",
        "currenttitle", "currentposition", "designation", "jobTitle",
        "currentTitle", "role", "current_role", "currentRole",
    ],
    "company": [
        "company", "currentcompany", "current_company", "employer",
        "currentemployer", "organization", "org", "currentCompany",
        "currentEmployer", "employer_name", "employerName",
    ],
    "location": [
        "location", "city", "address", "geo", "geography",
        "current_location", "currentlocation", "place", "currentLocation",
        "region", "country", "city_state",
    ],
    "skills": [
        "skills", "skill_set", "skillset", "competencies", "technologies",
        "tech_stack", "techstack", "expertise", "tools", "skillSet",
        "techStack", "technical_skills", "technicalSkills", "key_skills",
        "keySkills",
    ],
    "linkedin": [
        "linkedin", "linkedinurl", "linkedin_url", "linkedin_profile",
        "linkedinprofile", "linkedInProfile", "linkedinUrl", "linkedin_link",
    ],
    "github": [
        "github", "githuburl", "github_url", "github_profile",
        "githubprofile", "githubProfile", "githubUrl", "github_link",
    ],
    "portfolio": [
        "portfolio", "portfoliourl", "portfolio_url", "website",
        "personal_website", "personalwebsite", "blog", "portfolioUrl",
        "personalWebsite", "personal_site",
    ],
    "years_experience": [
        "totalexperience", "total_experience", "years_of_experience",
        "yearsexperience", "experience_years", "experienceyears",
        "yoe", "years_exp", "totalExperience", "yearsExperience",
        "experienceYears", "total_yrs", "years",
    ],
    "summary": [
        "summary", "bio", "about", "profile_summary", "profilesummary",
        "overview", "description", "profileSummary", "candidate_summary",
        "candidateSummary", "objective", "profile",
    ],
    "education": [
        "education", "qualifications", "academic_background",
        "academicBackground", "academics", "educational_background",
    ],
    "experience": [
        "experience", "work_experience", "workexperience", "employment",
        "employment_history", "employmentHistory", "work_history",
        "workHistory", "jobs",
    ],
}

# Build reverse lookup: lowercased alias → canonical key (built once)
_ALIAS_LOOKUP: dict[str, str] = {
    alias.lower(): canonical
    for canonical, aliases in FIELD_MAP.items()
    for alias in aliases
}


def _flatten_json(obj: Any, prefix: str = "") -> dict[str, Any]:
    """
    Flatten nested dicts to dot-notation keys.
    Lists (of any type) are always kept as-is — never exploded into indexed keys.
    This preserves multi-value fields (skills, experience, education) intact.
    """
    items: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.update(_flatten_json(v, key))
            else:
                # Lists and primitives kept as-is
                items[key] = v
    else:
        items[prefix] = obj
    return items


def _resolve_aliases(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Map raw keys to canonical keys using the alias lookup.
    Returns (recognized, unrecognized) dicts.
    """
    recognized: dict[str, Any] = {}
    unrecognized: dict[str, Any] = {}

    for raw_key, value in raw.items():
        # Strip dot-notation prefix for leaf keys (e.g. "candidate.name" → try "name" too)
        leaf = raw_key.split(".")[-1].strip("[]0123456789")
        canonical = _ALIAS_LOOKUP.get(raw_key.lower()) or _ALIAS_LOOKUP.get(leaf.lower())
        if canonical:
            if canonical not in recognized:
                recognized[canonical] = value
        else:
            unrecognized[raw_key] = value

    return recognized, unrecognized


def _normalize(canonical_key: str, value: Any) -> Any:
    """Coerce value to the expected type for a canonical key."""
    if canonical_key == "emails":
        if isinstance(value, list):
            return [str(e).strip().lower() for e in value if e]
        return [str(value).strip().lower()] if value else []

    if canonical_key == "phones":
        if isinstance(value, list):
            return [str(p).strip() for p in value if p]
        return [str(value).strip()] if value else []

    if canonical_key == "skills":
        if isinstance(value, list):
            return [str(s).strip() for s in value if s]
        if isinstance(value, str):
            return [s.strip() for s in value.split(",") if s.strip()]
        return []

    if canonical_key == "years_experience":
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    if canonical_key in ("experience", "education"):
        return value if isinstance(value, list) else []

    # String fields
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return value  # pass unknown list fields through unchanged
    return str(value).strip() if value is not None else None


def parse_ats_json_all(path: str) -> list[dict]:
    """
    Parse all records from an ATS JSON file (handles both single object and array).
    Returns a list of parsed records — one per candidate in the file.
    Never raises.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning("ATS JSON read error for %r: %s", path, e)
        return []

    records_raw = raw if isinstance(raw, list) else [raw]
    results = []
    for record in records_raw:
        if not isinstance(record, dict):
            continue
        parsed = parse_ats_json(record)
        if parsed.get("data"):
            results.append(parsed)
    return results


def parse_ats_json(source: str | dict) -> dict:
    """
    Parse an ATS JSON blob from a file path or a dict directly.

    Returns:
      {
        "source": "ats_json",
        "data": {...canonical fields...},
        "unrecognized_fields": [...field names the parser couldn't map...]
      }

    Never raises.
    """
    empty = {"source": "ats_json", "data": {}, "unrecognized_fields": []}
    raw_data: Any = {}

    if isinstance(source, str):
        try:
            with open(source, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except FileNotFoundError:
            logger.warning("ATS JSON file not found: %r", source)
            return empty
        except json.JSONDecodeError as e:
            logger.warning("ATS JSON decode error for %r: %s", source, e)
            return empty
        except Exception as e:
            logger.warning("ATS JSON unexpected error for %r: %s", source, e)
            return empty
    elif isinstance(source, dict):
        raw_data = source
    else:
        logger.warning("ATS JSON: unsupported source type %r", type(source))
        return empty

    # Handle array input — pick first object (most ATS bulk exports)
    if isinstance(raw_data, list):
        if not raw_data:
            return empty
        logger.info("ATS JSON: received array of %d records, using first", len(raw_data))
        raw_data = raw_data[0]

    if not isinstance(raw_data, dict) or not raw_data:
        return empty

    # Flatten nested structure, then resolve aliases
    flat = _flatten_json(raw_data)
    recognized, unrecognized = _resolve_aliases(flat)

    # LLM fallback for unrecognized fields
    llm_mapped: dict[str, str | None] = {}
    if unrecognized:
        try:
            from pipeline.llm_mapper import map_unknown_fields
            sample = {k: v for k, v in list(unrecognized.items())[:20]}
            llm_mapped = map_unknown_fields(sample)
            for raw_key, canonical in llm_mapped.items():
                if canonical and raw_key in unrecognized and canonical not in recognized:
                    recognized[canonical] = unrecognized.pop(raw_key)
                    logger.info("LLM mapped ATS field %r → %r", raw_key, canonical)
        except Exception as e:
            logger.debug("LLM mapper error: %s", e)

    # Build output data dict
    data: dict[str, Any] = {}
    for canonical_key, value in recognized.items():
        norm = _normalize(canonical_key, value)
        if norm is not None and norm != [] and norm != "":
            data[canonical_key] = norm

    # Synthesize a current-role experience entry from flat company/title fields
    # when no structured experience array was found
    if "experience" not in data and ("company" in data or "title" in data):
        data["experience"] = [{
            "company": data.get("company"),
            "title":   data.get("title"),
            "start":   None,
            "end":     None,
        }]

    # Combine first_name + last_name → full_name
    if "full_name" not in data:
        first = data.pop("first_name", None)
        last  = data.pop("last_name", None)
        if first or last:
            data["full_name"] = " ".join(filter(None, [first, last])).strip()
    else:
        data.pop("first_name", None)
        data.pop("last_name", None)

    unrecognized_list = list(unrecognized.keys())
    if unrecognized_list:
        logger.info("ATS JSON: %d unrecognized fields: %s", len(unrecognized_list), unrecognized_list)

    logger.debug("ATS JSON parser extracted keys: %s", list(data.keys()))
    return {
        "source": "ats_json",
        "data": data,
        "unrecognized_fields": unrecognized_list,
    }

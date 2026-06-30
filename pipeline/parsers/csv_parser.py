"""
CSV Parser — reads recruiter CSV exports and extracts candidate data.

Strategy:
  1. Normalize column names, try alias map (deterministic)
  2. For unrecognized columns, call LLM mapper if GEMINI_API_KEY is set
  3. Combine first_name + last_name if full_name column absent
  4. Return unrecognized_columns list for caller feedback
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False
    logger.warning("pandas not installed — CSV parser will not function")

# Alias map: normalized column name → canonical key
_COL_MAP: dict[str, str] = {
    # Full name
    "name":               "full_name",
    "fullname":           "full_name",
    "full_name":          "full_name",
    "candidate_name":     "full_name",
    "applicant_name":     "full_name",
    "candidate":          "full_name",
    # First / last
    "first_name":         "first_name",
    "firstname":          "first_name",
    "given_name":         "first_name",
    "fname":              "first_name",
    "last_name":          "last_name",
    "lastname":           "last_name",
    "surname":            "last_name",
    "family_name":        "last_name",
    "lname":              "last_name",
    # Email
    "email":              "emails",
    "email_address":      "emails",
    "emailaddress":       "emails",
    "e-mail":             "emails",
    "e_mail":             "emails",
    "contact_email":      "emails",
    "mail":               "emails",
    # Phone
    "phone":              "phones",
    "phone_number":       "phones",
    "phonenumber":        "phones",
    "mobile":             "phones",
    "cell":               "phones",
    "mobile_number":      "phones",
    "cell_phone":         "phones",
    "contact_number":     "phones",
    "telephone":          "phones",
    "tel":                "phones",
    # Company
    "current_company":    "company",
    "company":            "company",
    "employer":           "company",
    "organization":       "company",
    "org":                "company",
    "current_employer":   "company",
    "employer_name":      "company",
    # Title
    "title":              "title",
    "job_title":          "title",
    "jobtitle":           "title",
    "position":           "title",
    "current_title":      "title",
    "current_role":       "title",
    "role":               "title",
    "designation":        "title",
    # Location
    "location":           "location",
    "city":               "location",
    "address":            "location",
    "geo":                "location",
    "region":             "location",
    "current_location":   "location",
    "place":              "location",
    "city_state":         "location",
    # LinkedIn
    "linkedin":           "linkedin",
    "linkedin_url":       "linkedin",
    "linkedinurl":        "linkedin",
    "linkedin_profile":   "linkedin",
    "linkedin_link":      "linkedin",
    # GitHub
    "github":             "github",
    "github_url":         "github",
    "githuburl":          "github",
    "github_profile":     "github",
    "github_link":        "github",
    # Portfolio
    "portfolio":          "portfolio",
    "website":            "portfolio",
    "personal_website":   "portfolio",
    "blog":               "portfolio",
    "personal_site":      "portfolio",
    # Skills
    "skills":             "skills",
    "skill_set":          "skills",
    "skillset":           "skills",
    "competencies":       "skills",
    "technologies":       "skills",
    "tech_stack":         "skills",
    "expertise":          "skills",
    "tools":              "skills",
    "technical_skills":   "skills",
    "key_skills":         "skills",
    # Experience
    "years_experience":   "years_experience",
    "years_of_experience":"years_experience",
    "total_experience":   "years_experience",
    "experience_years":   "years_experience",
    "yoe":                "years_experience",
    "years_exp":          "years_experience",
    "total_yrs":          "years_experience",
    # Summary
    "summary":            "summary",
    "bio":                "summary",
    "about":              "summary",
    "overview":           "summary",
    "profile":            "summary",
    "objective":          "summary",
}

# List-type canonical keys
_LIST_KEYS = {"emails", "phones", "skills"}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "n/a", "na", ""}:
        return None
    return s


def _set_field(data: dict, canonical: str, value: str) -> None:
    """Write a value into data under its canonical key, handling list types."""
    if canonical in _LIST_KEYS:
        data.setdefault(canonical, [])
        # Skills may be comma-separated in a single cell
        if canonical == "skills":
            parts = [p.strip() for p in value.split(",") if p.strip()]
            for p in parts:
                if p not in data[canonical]:
                    data[canonical].append(p)
        else:
            if value not in data[canonical]:
                data[canonical].append(value)
    elif canonical not in data:
        data[canonical] = value


def parse_csv(path: str) -> list[dict]:
    """
    Parse a CSV file. Returns one record dict per row:
      {
        "source": "csv",
        "data": {...canonical fields...},
        "unrecognized_columns": [...]   # columns the parser couldn't map
      }

    Never raises.
    """
    if not _PANDAS_AVAILABLE:
        logger.error("pandas is required for CSV parsing")
        return []

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=True)
    except Exception as e:
        logger.warning("CSV parse error for %r: %s", path, e)
        return []

    if df.empty:
        logger.warning("CSV file %r is empty", path)
        return []

    # Map each column to its canonical key (or None if unrecognized)
    col_canonical: dict[str, str | None] = {}
    for col in df.columns:
        normalized = col.strip().lower().replace(" ", "_").replace("-", "_")
        col_canonical[col] = _COL_MAP.get(normalized)

    unrecognized_cols = [col for col, canon in col_canonical.items() if canon is None]

    # LLM fallback for unrecognized columns (run once per file, not per row)
    llm_col_map: dict[str, str | None] = {}
    if unrecognized_cols:
        logger.info("CSV: %d unrecognized columns: %s", len(unrecognized_cols), unrecognized_cols)
        try:
            from pipeline.llm_mapper import map_unknown_fields
            # Use first non-null value per column as sample
            sample = {}
            for col in unrecognized_cols:
                for val in df[col].dropna():
                    cleaned = _clean(val)
                    if cleaned:
                        sample[col] = cleaned
                        break
            if sample:
                llm_col_map = map_unknown_fields(sample)
                for col, canon in llm_col_map.items():
                    if canon:
                        col_canonical[col] = canon
                        logger.info("LLM mapped CSV column %r → %r", col, canon)
        except Exception as e:
            logger.debug("LLM mapper error: %s", e)

    # Final unrecognized after LLM pass
    still_unrecognized = [col for col, canon in col_canonical.items() if canon is None]

    records: list[dict] = []

    for _, row in df.iterrows():
        data: dict[str, Any] = {}

        for col, canonical in col_canonical.items():
            if not canonical:
                continue
            value = _clean(row.get(col))
            if value is None:
                continue
            _set_field(data, canonical, value)

        # Combine first_name + last_name → full_name
        if "full_name" not in data:
            first = data.pop("first_name", None)
            last  = data.pop("last_name", None)
            if first or last:
                data["full_name"] = " ".join(filter(None, [first, last])).strip()
        else:
            data.pop("first_name", None)
            data.pop("last_name", None)

        # Normalize years_experience to float
        if "years_experience" in data:
            try:
                data["years_experience"] = float(data["years_experience"])
            except (ValueError, TypeError):
                del data["years_experience"]

        if not data:
            continue

        records.append({
            "source": "csv",
            "data": data,
            "unrecognized_columns": still_unrecognized,
        })

    logger.debug("CSV parser extracted %d records from %r", len(records), path)
    return records

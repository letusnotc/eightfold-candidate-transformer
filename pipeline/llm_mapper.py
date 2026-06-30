"""
LLM Field Mapper — uses Gemini to map unknown CSV/JSON field names to
canonical candidate profile keys.

Called only when the alias map fails to recognize a field. Falls back
gracefully (returns empty dict) if GEMINI_API_KEY is not set or the
call fails.

Temperature is fixed at 0 for determinism — same input → same mapping.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Canonical keys the pipeline understands
CANONICAL_KEYS = [
    "full_name",        # full candidate name (string)
    "first_name",       # first name only — will be combined with last_name
    "last_name",        # last name only  — will be combined with first_name
    "emails",           # email address(es) (list)
    "phones",           # phone number(s) (list)
    "location",         # city / region / country string
    "linkedin",         # LinkedIn profile URL or slug
    "github",           # GitHub profile URL or username
    "portfolio",        # personal website / portfolio URL
    "title",            # current job title
    "company",          # current employer
    "skills",           # list of skills / technologies
    "years_experience", # total years of experience (number)
    "summary",          # bio / profile summary
    "education",        # education info (degree, institution)
    "experience",       # work experience entries
]

_PROMPT_TEMPLATE = """You are a data field mapper for a candidate/resume pipeline.

Your job: map unknown field names from a CSV or ATS JSON export to the canonical
candidate profile keys listed below. Use the sample value to help infer intent.

Canonical keys:
{canonical_keys}

Unknown fields (name → sample value):
{fields}

Rules:
- Return ONLY valid JSON — a flat object mapping each input field name to a
  canonical key string, or null if there is no reasonable match.
- "first_name" and "last_name" are valid outputs (the pipeline combines them).
- Do not invent canonical keys not in the list above.
- If a field is clearly irrelevant (e.g. "internal_score", "referral_bonus"), map it to null.

Example output:
{{"First Name": "first_name", "E-mail": "emails", "Current Role": "title", "DOB": null}}

Output ONLY the JSON object, no explanation."""


def _get_client():
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        logger.debug("google-genai not installed — LLM mapping unavailable")
        return None


def map_unknown_fields(
    unknown: dict[str, Any],
    model: str = "gemma-4-26b-a4b-it",
) -> dict[str, str | None]:
    """
    Ask Gemini to map *unknown* field names to canonical keys.

    Args:
        unknown: dict of {field_name: sample_value} for unrecognized fields
        model:   Gemini model ID to use

    Returns:
        dict of {field_name: canonical_key_or_None}
        Empty dict if LLM is unavailable or call fails.
    """
    if not unknown:
        return {}

    client = _get_client()
    if client is None:
        return {}

    # Build readable field list for the prompt
    field_lines = "\n".join(
        f'  "{k}": {json.dumps(str(v)[:80])}'
        for k, v in list(unknown.items())[:30]  # cap at 30 fields
    )

    prompt = _PROMPT_TEMPLATE.format(
        canonical_keys=json.dumps(CANONICAL_KEYS, indent=2),
        fields=field_lines,
    )

    try:
        from google.genai import types

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        # Strip markdown code fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        mapping = json.loads(raw)
        if not isinstance(mapping, dict):
            logger.warning("LLM mapper returned non-dict: %r", raw)
            return {}

        logger.info(
            "LLM mapper: %d/%d fields mapped",
            sum(1 for v in mapping.values() if v),
            len(mapping),
        )
        return mapping

    except Exception as e:
        logger.warning("LLM field mapping failed: %s", e)
        return {}

"""
Phone number normalizer — converts any phone string to E.164 format.
Never invents a number; returns None if unparseable.
"""

from __future__ import annotations

import logging
from typing import Optional

import phonenumbers

logger = logging.getLogger(__name__)


def normalize_phone(raw: str, default_region: str = "US") -> Optional[str]:
    """
    Try to parse *raw* and format to E.164.
    Strategy:
      1. Try with default_region hint first.
      2. If that fails, try without region (requires +country-code in string).
    Returns None if unparseable — never invents a number.
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip()

    # Attempt 1: with region hint
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    # Attempt 2: without region (needs leading '+' or country code)
    try:
        parsed = phonenumbers.parse(raw, None)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    logger.debug("Could not parse phone: %r", raw)
    return None


def normalize_phones(raw_list: list[str], default_region: str = "US") -> list[str]:
    """
    Normalize a list of raw phone strings.
    Deduplicates results and drops None values.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_list:
        normalized = normalize_phone(raw, default_region)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result

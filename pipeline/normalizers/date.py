"""
Date normalizer — parses any date string to YYYY-MM format.
Also computes total years of experience from an experience list.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta
from datetime import datetime

logger = logging.getLogger(__name__)

# Patterns that dateutil struggles with
_YYYY_MM_RE = re.compile(r"^(\d{4})[/-](\d{1,2})$")
_MM_YYYY_RE = re.compile(r"^(\d{1,2})[/-](\d{4})$")


def normalize_date(raw: str) -> Optional[str]:
    """
    Parse any date string → YYYY-MM format.
    Returns None if unparseable.

    Handles: "Jan 2023", "2023-01", "January 2023", "01/2023",
             "2023-01-15", "January 15 2023", etc.
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip()

    # "present" / "current" → None (caller decides what to do)
    if raw.lower() in {"present", "current", "now", "ongoing", "till date"}:
        return None

    # Explicit YYYY-MM
    m = _YYYY_MM_RE.match(raw)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    # Explicit MM/YYYY
    m = _MM_YYYY_RE.match(raw)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    # Fallback: dateutil
    try:
        dt = dateparser.parse(raw, default=datetime(2000, 1, 1))
        return dt.strftime("%Y-%m")
    except (ValueError, OverflowError, TypeError):
        logger.debug("Could not parse date: %r", raw)
        return None


def extract_years_experience(experience_list: list[dict]) -> Optional[float]:
    """
    Sum up months across all experience entries.
    Each entry is expected to have 'start' and 'end' as YYYY-MM strings
    (or 'end' = None / "present" = treat as today).

    Returns total years rounded to 1 decimal, or None if no valid dates.
    """
    now = datetime.utcnow()
    total_months = 0
    found_any = False

    for exp in experience_list:
        start_raw = exp.get("start")
        end_raw = exp.get("end")

        start_str = normalize_date(start_raw) if start_raw else None
        if not start_str:
            continue

        # Parse start
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m")
        except ValueError:
            continue

        # Parse end
        if end_raw and str(end_raw).lower() not in {"present", "current", "now", "ongoing"}:
            end_str = normalize_date(end_raw)
            if end_str:
                try:
                    end_dt = datetime.strptime(end_str, "%Y-%m")
                except ValueError:
                    end_dt = now
            else:
                end_dt = now
        else:
            end_dt = now

        delta = relativedelta(end_dt, start_dt)
        months = delta.years * 12 + delta.months
        if months > 0:
            total_months += months
            found_any = True

    if not found_any:
        return None

    return round(total_months / 12, 1)

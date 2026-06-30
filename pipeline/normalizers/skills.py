"""
Skills normalizer — maps raw skill strings to canonical names.
Loads alias mapping from skills_canonical.json.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level cache so we only read the file once
_CANONICAL_MAP: Optional[dict[str, str]] = None
_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "skills_canonical.json")


def load_canonical_skills(path: str = _DEFAULT_PATH) -> dict[str, str]:
    """
    Load the alias → canonical name mapping.
    Returns a flat dict: {alias_lower: canonical_name}
    File format: { "canonical": ["alias1", "alias2", ...], ... }
    """
    global _CANONICAL_MAP
    if _CANONICAL_MAP is not None:
        return _CANONICAL_MAP

    resolved = os.path.abspath(path)
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw: dict[str, list[str]] = json.load(f)
    except FileNotFoundError:
        logger.warning("skills_canonical.json not found at %s", resolved)
        _CANONICAL_MAP = {}
        return _CANONICAL_MAP
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in skills_canonical.json: %s", e)
        _CANONICAL_MAP = {}
        return _CANONICAL_MAP

    flat: dict[str, str] = {}
    for canonical, aliases in raw.items():
        # The canonical name itself is also a valid alias
        flat[canonical.lower().strip()] = canonical
        for alias in aliases:
            flat[alias.lower().strip()] = canonical

    _CANONICAL_MAP = flat
    logger.debug("Loaded %d skill aliases → %d canonical skills", len(flat), len(raw))
    return _CANONICAL_MAP


def canonicalize_skill(raw_skill: str, canonical_map: Optional[dict[str, str]] = None) -> str:
    """
    Lowercase and strip the raw skill, then check against all aliases.
    Returns:
      - canonical name if found in map
      - cleaned raw string otherwise (never returns None for an explicit mention)
    """
    if canonical_map is None:
        canonical_map = load_canonical_skills()

    if not raw_skill or not isinstance(raw_skill, str):
        return ""

    cleaned = raw_skill.strip()
    key = cleaned.lower()

    return canonical_map.get(key, cleaned)


def canonicalize_skills(raw_skills: list[str], canonical_map: Optional[dict[str, str]] = None) -> list[str]:
    """
    Canonicalize a list of raw skill strings.
    Deduplicates by canonical name (preserves first occurrence order).
    """
    if canonical_map is None:
        canonical_map = load_canonical_skills()

    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_skills:
        canon = canonicalize_skill(raw, canonical_map)
        if canon and canon not in seen:
            seen.add(canon)
            result.append(canon)
    return result


def reset_cache() -> None:
    """Reset the module-level skills cache (used in tests)."""
    global _CANONICAL_MAP
    _CANONICAL_MAP = None

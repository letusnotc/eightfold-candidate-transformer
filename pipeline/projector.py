"""
Projector — applies a user-supplied config JSON to reshape a CanonicalProfile
into a custom output dict.

Config format:
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"},
    {"path": "location.country", "type": "string"}
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"   # "null" | "omit" | "error"
}

Path resolution:
  "emails[0]"        → profile.emails[0]
  "skills[].name"    → [s.name for s in profile.skills]
  "location.country" → profile.location.country
  "full_name"        → profile.full_name
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pipeline.models import CanonicalProfile
from pipeline.normalizers.phone import normalize_phone
from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills

logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Runtime config-driven projection of CanonicalProfile → output dict."""

    def _resolve_path(self, profile: CanonicalProfile, path: str) -> Any:
        """
        Resolve a path expression against the profile.

        Supported syntax:
          "field"           → getattr(profile, field)
          "field[N]"        → getattr(profile, field)[N]
          "field[].sub"     → [item.sub for item in getattr(profile, field)]
          "obj.sub"         → getattr(getattr(profile, obj), sub)
        """
        if not path:
            return None

        # Array pluck: "skills[].name"
        if "[]." in path:
            parts = path.split("[].", 1)
            array_field = parts[0]
            sub_field = parts[1]
            arr = self._resolve_simple(profile, array_field)
            if not isinstance(arr, list):
                return None
            result = []
            for item in arr:
                val = self._get_nested(item, sub_field)
                if val is not None:
                    result.append(val)
            return result

        # Indexed: "emails[0]"
        import re
        idx_match = re.match(r"^([\w.]+)\[(\d+)\]$", path)
        if idx_match:
            field = idx_match.group(1)
            idx = int(idx_match.group(2))
            arr = self._resolve_simple(profile, field)
            if isinstance(arr, list) and idx < len(arr):
                return arr[idx]
            return None

        # Nested: "location.country"
        if "." in path:
            parts = path.split(".", 1)
            obj = self._resolve_simple(profile, parts[0])
            if obj is None:
                return None
            return self._get_nested(obj, parts[1])

        # Simple field
        return self._resolve_simple(profile, path)

    def _resolve_simple(self, profile: CanonicalProfile, field: str) -> Any:
        """Get a top-level attribute from profile, returning None if missing."""
        try:
            val = getattr(profile, field, None)
            # Convert Pydantic models to dict for JSON serialization
            if hasattr(val, "model_dump"):
                return val.model_dump()
            if isinstance(val, list):
                return [item.model_dump() if hasattr(item, "model_dump") else item for item in val]
            return val
        except Exception:
            return None

    def _get_nested(self, obj: Any, path: str) -> Any:
        """Recursively resolve a dotted path on a dict or object."""
        parts = path.split(".", 1)
        key = parts[0]
        rest = parts[1] if len(parts) > 1 else None

        if isinstance(obj, dict):
            val = obj.get(key)
        else:
            val = getattr(obj, key, None)
            if hasattr(val, "model_dump"):
                val = val.model_dump()

        if rest and val is not None:
            return self._get_nested(val, rest)
        return val

    def _apply_normalize(self, value: Any, normalize: str, field_config: dict) -> Any:
        """Apply a normalization transform to a value."""
        if normalize == "E164":
            if isinstance(value, str):
                return normalize_phone(value) or value
            return value

        if normalize == "canonical":
            canonical_map = load_canonical_skills()
            if isinstance(value, list):
                seen: set[str] = set()
                result = []
                for v in value:
                    canon = canonicalize_skill(str(v), canonical_map)
                    if canon and canon not in seen:
                        seen.add(canon)
                        result.append(canon)
                return result
            elif isinstance(value, str):
                return canonicalize_skill(value, canonical_map)
            return value

        if normalize == "lowercase":
            if isinstance(value, str):
                return value.lower()
            return value

        if normalize == "uppercase":
            if isinstance(value, str):
                return value.upper()
            return value

        return value

    def project(self, canonical: CanonicalProfile, config: dict) -> dict:
        """
        Apply field selection, renaming, normalization from *config*.

        Returns the projected output dict.
        """
        on_missing: str = config.get("on_missing", "null")
        fields_config: list[dict] = config.get("fields", [])
        include_confidence: bool = config.get("include_confidence", True)
        include_provenance: bool = config.get("include_provenance", True)

        output: dict = {}

        if not fields_config:
            # No field config → return full profile as dict
            result = canonical.model_dump()
            if not include_provenance:
                result.pop("provenance", None)
            return result

        for field_def in fields_config:
            output_path: str = field_def.get("path", "")
            source_path: str = field_def.get("from", output_path)
            normalize: Optional[str] = field_def.get("normalize")
            required: bool = field_def.get("required", False)

            # Resolve value
            value = self._resolve_path(canonical, source_path)

            # Apply normalization
            if value is not None and normalize:
                value = self._apply_normalize(value, normalize, field_def)

            # Handle missing
            if value is None:
                if on_missing == "null":
                    output[output_path] = None
                elif on_missing == "omit":
                    pass  # Don't add the key
                elif on_missing == "error":
                    output[output_path] = None  # Will be caught by validate()
                # required fields handled in validate()
            else:
                output[output_path] = value

        # Optionally inject confidence/provenance at the envelope level
        if include_confidence:
            output["_overall_confidence"] = canonical.overall_confidence

        if include_provenance:
            output["_provenance"] = [p.model_dump() for p in canonical.provenance]

        return output

    def validate(self, projected: dict, config: dict) -> list[str]:
        """
        Validate projected output against config.
        Returns a list of validation error messages (empty = valid).
        """
        errors: list[str] = []
        on_missing: str = config.get("on_missing", "null")
        fields_config: list[dict] = config.get("fields", [])

        for field_def in fields_config:
            path: str = field_def.get("path", "")
            required: bool = field_def.get("required", False)

            if required:
                value = projected.get(path)
                if value is None:
                    errors.append(f"Required field '{path}' is missing or null")

            if on_missing == "error":
                if path in projected and projected[path] is None:
                    errors.append(f"Field '{path}' has no value (on_missing=error)")

        return errors

"""
Tests for the ProjectionEngine.
Run: pytest tests/test_projector.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_profile(**kwargs):
    """Helper to create a CanonicalProfile with given fields."""
    from pipeline.models import CanonicalProfile, Skill, Location, Links
    defaults = {
        "candidate_id": "abc123",
        "full_name": "Test User",
        "emails": ["test@example.com", "test2@example.com"],
        "phones": ["+15551234567"],
        "skills": [
            Skill(name="python", confidence=0.9, sources=["csv"]),
            Skill(name="docker", confidence=0.8, sources=["github"]),
        ],
        "location": Location(city="San Francisco", region="CA", country="US"),
        "links": Links(github="https://github.com/testuser"),
        "years_experience": 5.0,
        "overall_confidence": 0.85,
    }
    defaults.update(kwargs)
    return CanonicalProfile(**defaults)


class TestProjectionEngine:
    def test_project_simple_field(self):
        """Simple field path → value copied."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {"fields": [{"path": "full_name", "type": "string"}], "on_missing": "null"}
        result = engine.project(profile, config)
        assert result["full_name"] == "Test User"

    def test_project_field_rename(self):
        """'from': 'emails[0]' → 'path': 'primary_email'."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "primary_email", "from": "emails[0]", "type": "string"}],
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert result["primary_email"] == "test@example.com"

    def test_project_array_pluck(self):
        """'skills[].name' → list of skill names."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "skills", "from": "skills[].name", "type": "string[]"}],
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert isinstance(result["skills"], list)
        assert "python" in result["skills"]
        assert "docker" in result["skills"]

    def test_project_nested_field(self):
        """'location.country' → nested field access."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "country", "from": "location.country", "type": "string"}],
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert result["country"] == "US"

    def test_project_on_missing_null(self):
        """Missing field → null when on_missing='null'."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile(headline=None)
        config = {
            "fields": [{"path": "headline", "type": "string"}],
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert "headline" in result
        assert result["headline"] is None

    def test_project_on_missing_omit(self):
        """Missing field → key absent when on_missing='omit'."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile(headline=None)
        config = {
            "fields": [{"path": "headline", "type": "string"}],
            "on_missing": "omit",
        }
        result = engine.project(profile, config)
        assert "headline" not in result

    def test_project_required_error(self):
        """Required field missing → in validation errors list."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile(headline=None)
        config = {
            "fields": [{"path": "headline", "type": "string", "required": True}],
            "on_missing": "null",
        }
        projected = engine.project(profile, config)
        errors = engine.validate(projected, config)
        assert len(errors) > 0
        assert any("headline" in e for e in errors)

    def test_project_no_errors_when_valid(self):
        """All required fields present → no errors."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "full_name", "type": "string", "required": True}],
            "on_missing": "null",
        }
        projected = engine.project(profile, config)
        errors = engine.validate(projected, config)
        assert errors == []

    def test_project_normalize_e164(self):
        """normalize='E164' applied to phone field."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile(phones=["+15551234567"])
        config = {
            "fields": [{"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"}],
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert result["phone"] == "+15551234567"

    def test_project_normalize_canonical(self):
        """normalize='canonical' applied to skill names."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}],
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert isinstance(result["skills"], list)

    def test_project_empty_config(self):
        """Empty fields list → returns full profile dict."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        result = engine.project(profile, {})
        assert "full_name" in result
        assert "emails" in result

    def test_project_include_confidence(self):
        """include_confidence=True adds _overall_confidence to output."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": True,
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert "_overall_confidence" in result

    def test_project_exclude_provenance(self):
        """include_provenance=False omits _provenance from output."""
        from pipeline.projector import ProjectionEngine
        engine = ProjectionEngine()
        profile = _make_profile()
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_provenance": False,
            "on_missing": "null",
        }
        result = engine.project(profile, config)
        assert "_provenance" not in result

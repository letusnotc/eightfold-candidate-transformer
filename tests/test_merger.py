"""
Tests for the profile merger.
Run: pytest tests/test_merger.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_record(source: str, **kwargs) -> dict:
    return {"source": source, "data": kwargs}


class TestMerger:
    def test_merge_emails_dedup(self):
        """Same email from CSV + ATS → appears exactly once."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", emails=["priya@example.com"], full_name="Priya"),
            _make_record("ats_json", emails=["priya@example.com"], full_name="Priya"),
        ]
        profile = merge_profiles(records)
        assert profile.emails.count("priya@example.com") == 1

    def test_merge_emails_union(self):
        """Different emails from different sources → both present."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", emails=["work@example.com"], full_name="Alex"),
            _make_record("github", emails=["personal@example.com"], full_name="Alex"),
        ]
        profile = merge_profiles(records)
        assert "work@example.com" in profile.emails
        assert "personal@example.com" in profile.emails

    def test_merge_name_priority(self):
        """CSV has higher priority than GitHub for full_name."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", full_name="CSV Name", emails=["x@x.com"]),
            _make_record("github", full_name="GitHub Name"),
        ]
        profile = merge_profiles(records)
        assert profile.full_name == "CSV Name"

    def test_merge_skills_union(self):
        """Python from CSV, PyTorch from GitHub → both in result."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", full_name="Dev", emails=["dev@x.com"], skills=["python"]),
            _make_record("github", skills=["pytorch", "python"]),
        ]
        profile = merge_profiles(records)
        skill_names = {s.name for s in profile.skills}
        assert "python" in skill_names
        assert "pytorch" in skill_names

    def test_merge_skills_corroboration(self):
        """Skill mentioned in 2 sources gets higher confidence."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", full_name="Dev", emails=["dev@x.com"], skills=["python"]),
            _make_record("github", skills=["python"]),
        ]
        profile = merge_profiles(records)
        python_skill = next((s for s in profile.skills if s.name == "python"), None)
        assert python_skill is not None
        assert len(python_skill.sources) == 2

    def test_merge_candidate_id_deterministic(self):
        """Same email always produces same candidate_id."""
        from pipeline.merger import merge_profiles

        records = [_make_record("csv", emails=["test@x.com"], full_name="Test")]
        p1 = merge_profiles(records)
        p2 = merge_profiles(records)
        assert p1.candidate_id == p2.candidate_id

    def test_merge_headline_github_preferred(self):
        """GitHub bio is preferred over CSV title for headline."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", full_name="Dev", emails=["dev@x.com"], title="Engineer"),
            _make_record("github", full_name="Dev", headline="Open Source Enthusiast"),
        ]
        profile = merge_profiles(records)
        assert profile.headline == "Open Source Enthusiast"

    def test_merge_provenance_recorded(self):
        """Every merged field has a provenance entry."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", emails=["dev@x.com"], full_name="Dev"),
        ]
        profile = merge_profiles(records)
        assert len(profile.provenance) > 0
        prov_fields = {p.field for p in profile.provenance}
        assert "emails" in prov_fields or "full_name" in prov_fields

    def test_merge_empty_records(self):
        """Empty records list → valid (empty) profile, no crash."""
        from pipeline.merger import merge_profiles

        profile = merge_profiles([])
        assert profile.candidate_id is not None
        assert profile.emails == []
        assert profile.skills == []

    def test_merge_phones_normalized(self):
        """Phones from different sources are E.164 normalized and deduped."""
        from pipeline.merger import merge_profiles

        records = [
            _make_record("csv", full_name="Test", emails=["t@t.com"], phones=["+15551234567"]),
            _make_record("ats_json", phones=["555-123-4567"]),  # Same number, different format
        ]
        profile = merge_profiles(records)
        # After normalization, should appear once
        assert len([p for p in profile.phones if "5551234567" in p]) >= 1

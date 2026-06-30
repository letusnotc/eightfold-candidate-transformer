"""
Tests for all normalizers.
Run: pytest tests/test_normalizers.py -v
"""

from __future__ import annotations

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Phone normalizer
# ---------------------------------------------------------------------------

class TestPhoneNormalizer:
    def test_phone_e164_india(self):
        """Indian number without country code → E.164 with region hint."""
        from pipeline.normalizers.phone import normalize_phone
        result = normalize_phone("098765 43210", default_region="IN")
        assert result == "+919876543210"

    def test_phone_e164_mumbai(self):
        """Mumbai number with formatting → E.164 with IN region hint."""
        from pipeline.normalizers.phone import normalize_phone
        result = normalize_phone("98201 23456", default_region="IN")
        assert result == "+919820123456"

    def test_phone_e164_with_plus(self):
        """Number with + prefix → parsed without region hint."""
        from pipeline.normalizers.phone import normalize_phone
        result = normalize_phone("+919876543210")
        assert result == "+919876543210"

    def test_phone_invalid(self):
        """Non-phone string → None."""
        from pipeline.normalizers.phone import normalize_phone
        assert normalize_phone("not-a-phone") is None
        assert normalize_phone("") is None
        assert normalize_phone(None) is None

    def test_phone_dedup_india(self):
        """Same Indian number in two formats → deduplicated to one E.164."""
        from pipeline.normalizers.phone import normalize_phones
        # +91-9876543210 and 09876543210 are the same Bangalore number
        result = normalize_phones(["+919876543210", "09876 543210"], "IN")
        assert len(result) == 1
        assert result[0] == "+919876543210"

    def test_phone_formatted_delhi(self):
        """Delhi number with spaces and no country code → E.164 with region IN."""
        from pipeline.normalizers.phone import normalize_phone
        result = normalize_phone("98112 34567", default_region="IN")
        assert result == "+919811234567"


# ---------------------------------------------------------------------------
# Date normalizer
# ---------------------------------------------------------------------------

class TestDateNormalizer:
    def test_date_month_year(self):
        """'Jan 2023' → '2023-01'."""
        from pipeline.normalizers.date import normalize_date
        assert normalize_date("Jan 2023") == "2023-01"

    def test_date_full_month(self):
        """'January 2023' → '2023-01'."""
        from pipeline.normalizers.date import normalize_date
        assert normalize_date("January 2023") == "2023-01"

    def test_date_yyyy_mm(self):
        """'2023-01' → '2023-01'."""
        from pipeline.normalizers.date import normalize_date
        assert normalize_date("2023-01") == "2023-01"

    def test_date_full_with_day(self):
        """'January 15, 2023' → '2023-01'."""
        from pipeline.normalizers.date import normalize_date
        assert normalize_date("January 15, 2023") == "2023-01"

    def test_date_slash_format(self):
        """'01/2023' → '2023-01'."""
        from pipeline.normalizers.date import normalize_date
        result = normalize_date("01/2023")
        assert result == "2023-01"

    def test_date_present(self):
        """'Present' → None (caller decides)."""
        from pipeline.normalizers.date import normalize_date
        assert normalize_date("present") is None
        assert normalize_date("Present") is None
        assert normalize_date("current") is None

    def test_date_invalid(self):
        """Unparseable string → None."""
        from pipeline.normalizers.date import normalize_date
        assert normalize_date("sometime last year") is None
        assert normalize_date("") is None
        assert normalize_date(None) is None

    def test_years_experience_computation(self):
        """Sum of experience months → years."""
        from pipeline.normalizers.date import extract_years_experience
        exp = [
            {"start": "2021-01", "end": "present"},
            {"start": "2018-06", "end": "2020-12"},
        ]
        result = extract_years_experience(exp)
        assert result is not None
        assert result > 0


# ---------------------------------------------------------------------------
# Skills normalizer
# ---------------------------------------------------------------------------

class TestSkillsNormalizer:
    def setup_method(self):
        """Reset the module-level cache before each test."""
        from pipeline.normalizers.skills import reset_cache
        reset_cache()

    def test_skill_canonical_sklearn(self):
        """'sklearn' maps to 'machine-learning'."""
        from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills
        canon_map = load_canonical_skills()
        assert canonicalize_skill("sklearn", canon_map) == "machine-learning"

    def test_skill_canonical_tensorflow(self):
        """'tensorflow' maps to 'tensorflow'."""
        from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills
        canon_map = load_canonical_skills()
        result = canonicalize_skill("tensorflow", canon_map)
        assert result == "tensorflow"

    def test_skill_canonical_case_insensitive(self):
        """'PYTHON' maps to 'python'."""
        from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills
        canon_map = load_canonical_skills()
        result = canonicalize_skill("PYTHON", canon_map)
        assert result == "python"

    def test_skill_unknown(self):
        """Unknown skill returns the cleaned raw string, never None."""
        from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills
        canon_map = load_canonical_skills()
        result = canonicalize_skill("obscurelib2025", canon_map)
        assert result == "obscurelib2025"  # Not None
        assert result != ""

    def test_skill_alias_pytorch(self):
        """'torch' alias maps to 'pytorch'."""
        from pipeline.normalizers.skills import canonicalize_skill, load_canonical_skills
        canon_map = load_canonical_skills()
        assert canonicalize_skill("torch", canon_map) == "pytorch"

    def test_skill_canonicalize_list(self):
        """List canonicalization deduplicates."""
        from pipeline.normalizers.skills import canonicalize_skills, load_canonical_skills
        canon_map = load_canonical_skills()
        result = canonicalize_skills(["sklearn", "scikit-learn", "python"], canon_map)
        # sklearn and scikit-learn should both map to machine-learning → deduped
        assert result.count("machine-learning") == 1


# ---------------------------------------------------------------------------
# Location normalizer
# ---------------------------------------------------------------------------

class TestLocationNormalizer:
    def test_location_us_state(self):
        """'San Francisco, CA' - city=SF, region=CA, country=US."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("San Francisco, CA")
        assert result["city"] == "San Francisco"
        assert result["region"] == "CA"
        assert result["country"] == "US"

    def test_location_india(self):
        """'Bangalore, India' - city=Bangalore, country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Bangalore, India")
        assert result["city"] == "Bangalore"
        assert result["country"] == "IN"

    def test_location_empty(self):
        """Empty string - all None."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("")
        assert result["city"] is None
        assert result["country"] is None

    def test_location_country_only(self):
        """'India' alone - country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("India")
        assert result["country"] == "IN"

    def test_location_three_parts(self):
        """'Bangalore, Karnataka, India' - city, region, country."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Bangalore, Karnataka, India")
        assert result["city"] == "Bangalore"
        assert result["country"] == "IN"

    def test_location_mumbai_state(self):
        """'Mumbai, Maharashtra, India' - city=Mumbai, country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Mumbai, Maharashtra, India")
        assert result["city"] == "Mumbai"
        assert result["country"] == "IN"

    def test_location_delhi(self):
        """'New Delhi, India' - city=New Delhi, country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("New Delhi, India")
        assert result["city"] == "New Delhi"
        assert result["country"] == "IN"

    def test_location_chennai(self):
        """'Chennai, Tamil Nadu, India' - city=Chennai, country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Chennai, Tamil Nadu, India")
        assert result["city"] == "Chennai"
        assert result["country"] == "IN"

    def test_location_hyderabad(self):
        """'Hyderabad, Telangana, India' - city=Hyderabad, country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Hyderabad, Telangana, India")
        assert result["city"] == "Hyderabad"
        assert result["country"] == "IN"

    def test_location_pune(self):
        """'Pune, Maharashtra, India' - city=Pune, country=IN."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Pune, Maharashtra, India")
        assert result["city"] == "Pune"
        assert result["country"] == "IN"

    def test_location_bharat_alias(self):
        """'Kolkata, Bharat' - country=IN via Bharat alias."""
        from pipeline.normalizers.location import normalize_location
        result = normalize_location("Kolkata, Bharat")
        assert result["city"] == "Kolkata"
        assert result["country"] == "IN"

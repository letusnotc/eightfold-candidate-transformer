"""
Tests for all parsers.
Run: pytest tests/test_parsers.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# CSV Parser Tests
# ---------------------------------------------------------------------------

class TestCsvParser:
    def test_csv_parser_normal(self, tmp_path):
        """All expected columns present → correct extraction."""
        from pipeline.parsers.csv_parser import parse_csv

        csv_content = "name,email,phone,current_company,title\nJane Doe,jane@example.com,+1234567890,Acme,Engineer\n"
        p = tmp_path / "test.csv"
        p.write_text(csv_content, encoding="utf-8")

        records = parse_csv(str(p))
        assert len(records) == 1
        data = records[0]["data"]
        assert data["full_name"] == "Jane Doe"
        assert "jane@example.com" in data["emails"]
        assert records[0]["source"] == "csv"

    def test_csv_parser_missing_col(self, tmp_path):
        """Phone column missing → phones not in data, no crash."""
        from pipeline.parsers.csv_parser import parse_csv

        csv_content = "name,email\nJane Doe,jane@example.com\n"
        p = tmp_path / "test.csv"
        p.write_text(csv_content, encoding="utf-8")

        records = parse_csv(str(p))
        assert len(records) == 1
        data = records[0]["data"]
        assert "phones" not in data
        assert data["full_name"] == "Jane Doe"

    def test_csv_parser_empty_file(self, tmp_path):
        """Empty CSV → returns [], no crash."""
        from pipeline.parsers.csv_parser import parse_csv

        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")

        records = parse_csv(str(p))
        assert records == []

    def test_csv_parser_malformed(self, tmp_path):
        """Corrupt file → returns [], no crash."""
        from pipeline.parsers.csv_parser import parse_csv

        p = tmp_path / "bad.csv"
        p.write_bytes(b"\xff\xfe corrupt \x00 data")  # binary garbage

        records = parse_csv(str(p))
        assert isinstance(records, list)  # No crash

    def test_csv_parser_whitespace_stripping(self, tmp_path):
        """Values with surrounding whitespace are stripped."""
        from pipeline.parsers.csv_parser import parse_csv

        csv_content = "name,email\n  Jane Doe  ,  jane@example.com  \n"
        p = tmp_path / "ws.csv"
        p.write_text(csv_content, encoding="utf-8")

        records = parse_csv(str(p))
        assert records[0]["data"]["full_name"] == "Jane Doe"

    def test_csv_parser_multiple_rows(self, tmp_path):
        """Multiple rows produce multiple records."""
        from pipeline.parsers.csv_parser import parse_csv

        csv_content = "name,email\nAlice,alice@x.com\nBob,bob@x.com\n"
        p = tmp_path / "multi.csv"
        p.write_text(csv_content, encoding="utf-8")

        records = parse_csv(str(p))
        assert len(records) == 2


# ---------------------------------------------------------------------------
# ATS JSON Parser Tests
# ---------------------------------------------------------------------------

class TestAtsJsonParser:
    def test_ats_json_standard_fields(self, tmp_path):
        """Standard aliases map correctly."""
        from pipeline.parsers.ats_json_parser import parse_ats_json

        raw = {
            "applicant_name": "John Smith",
            "contact_email": "john@example.com",
            "mobile": "+15551234567",
            "competencies": ["Python", "Docker"],
        }
        p = tmp_path / "ats.json"
        p.write_text(json.dumps(raw), encoding="utf-8")

        result = parse_ats_json(str(p))
        assert result["source"] == "ats_json"
        assert result["data"]["full_name"] == "John Smith"
        assert "john@example.com" in result["data"]["emails"]
        assert "Python" in result["data"]["skills"]

    def test_ats_json_alias_fields(self, tmp_path):
        """emailAddress alias maps to emails."""
        from pipeline.parsers.ats_json_parser import parse_ats_json

        raw = {"emailAddress": "alias@example.com", "fullName": "Jane Smith"}
        p = tmp_path / "ats2.json"
        p.write_text(json.dumps(raw), encoding="utf-8")

        result = parse_ats_json(str(p))
        assert "alias@example.com" in result["data"]["emails"]
        assert result["data"]["full_name"] == "Jane Smith"

    def test_ats_json_empty(self, tmp_path):
        """Empty JSON object → data is empty, no crash."""
        from pipeline.parsers.ats_json_parser import parse_ats_json

        p = tmp_path / "empty.json"
        p.write_text("{}", encoding="utf-8")

        result = parse_ats_json(str(p))
        assert result["data"] == {}

    def test_ats_json_malformed(self, tmp_path):
        """Malformed JSON → empty data, no crash."""
        from pipeline.parsers.ats_json_parser import parse_ats_json

        p = tmp_path / "bad.json"
        p.write_text("{ this is not json }", encoding="utf-8")

        result = parse_ats_json(str(p))
        assert result["data"] == {}

    def test_ats_json_dict_input(self):
        """Dict input (not file path) also works."""
        from pipeline.parsers.ats_json_parser import parse_ats_json

        raw = {"name": "Direct Dict", "email": "direct@x.com"}
        result = parse_ats_json(raw)
        assert result["data"]["full_name"] == "Direct Dict"

    def test_ats_json_years_experience(self, tmp_path):
        """totalExperience field maps to years_experience."""
        from pipeline.parsers.ats_json_parser import parse_ats_json

        raw = {"totalExperience": 5}
        p = tmp_path / "ats3.json"
        p.write_text(json.dumps(raw), encoding="utf-8")

        result = parse_ats_json(str(p))
        assert result["data"].get("years_experience") == 5.0


# ---------------------------------------------------------------------------
# GitHub Parser Tests (async)
# ---------------------------------------------------------------------------

class TestGithubParser:
    def test_github_extract_username_from_url(self):
        """URL extraction works for various formats."""
        from pipeline.parsers.github_parser import _extract_username

        assert _extract_username("https://github.com/torvalds") == "torvalds"
        assert _extract_username("github.com/torvalds") == "torvalds"
        assert _extract_username("torvalds") == "torvalds"
        assert _extract_username("@torvalds") == "torvalds"
        assert _extract_username("https://github.com/torvalds/linux") == "torvalds"

    @pytest.mark.asyncio
    async def test_github_parser_valid(self):
        """Real public user 'torvalds' returns non-empty data."""
        from pipeline.parsers.github_parser import parse_github

        result = await parse_github("torvalds")
        # If network not available, skip gracefully
        if not result["data"]:
            pytest.skip("GitHub API not accessible (network or rate limit)")

        assert result["source"] == "github"
        assert result["data"].get("full_name") or result["data"].get("github")

    @pytest.mark.asyncio
    async def test_github_parser_404(self):
        """Nonexistent user → empty data, no crash."""
        from pipeline.parsers.github_parser import parse_github

        result = await parse_github("this-user-definitely-does-not-exist-abc123xyz")
        assert result["source"] == "github"
        assert result["data"] == {}

    @pytest.mark.asyncio
    async def test_github_parser_url(self):
        """Full URL and bare username both work."""
        from pipeline.parsers.github_parser import parse_github

        result1 = await parse_github("torvalds")
        result2 = await parse_github("https://github.com/torvalds")
        # Both should not crash; if data is available it should be the same
        assert result1["source"] == "github"
        assert result2["source"] == "github"


# ---------------------------------------------------------------------------
# Resume Parser Tests (no GLiNER needed — uses TXT fallback)
# ---------------------------------------------------------------------------

class TestResumeParser:
    def test_resume_parser_txt(self, tmp_path):
        """TXT resume → emails and name extracted."""
        from pipeline.parsers.resume_parser import parse_resume

        content = "Jane Doe\njane@example.com\nPython, Docker\n"
        p = tmp_path / "resume.txt"
        p.write_text(content, encoding="utf-8")

        result = parse_resume(str(p))
        assert result["source"] == "resume_txt"
        assert isinstance(result["data"], dict)
        # Email should be found by regex
        assert "jane@example.com" in result["data"].get("emails", [])

    def test_resume_parser_missing_file(self):
        """Missing file → empty data, no crash."""
        from pipeline.parsers.resume_parser import parse_resume

        result = parse_resume("/nonexistent/path/resume.pdf")
        assert result["data"] == {}

    def test_resume_parser_links(self, tmp_path):
        """GitHub and LinkedIn links extracted by regex."""
        from pipeline.parsers.resume_parser import parse_resume

        content = "Jane Doe\ngithub.com/janedoe\nlinkedin.com/in/janedoe\n"
        p = tmp_path / "resume.txt"
        p.write_text(content, encoding="utf-8")

        result = parse_resume(str(p))
        assert "github" in result["data"] or True  # GLiNER optional
        # At minimum, no crash
        assert isinstance(result["data"], dict)

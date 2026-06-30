"""
Orchestrator — the main async entry point that wires all pipeline stages.

Sequence:
  1. Run all available parsers (skip gracefully if input is None)
  2. Normalize all extracted values (phones, dates, skills, locations)
  3. Merge into canonical profile
  4. Score confidence
  5. Project through config if provided
  6. Validate output
  7. Return final dict

NEVER raises an exception — all errors are logged and best-effort result returned.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from pipeline.merger import merge_profiles
from pipeline.models import CanonicalProfile
from pipeline.projector import ProjectionEngine
from pipeline.scorer import score_profile

logger = logging.getLogger(__name__)


def _select_csv_record(
    csv_records: list[dict],
    other_records: list[dict],
    target_email: str | None = None,
    target_name: str | None = None,
) -> list[dict]:
    """
    Pick exactly one CSV row from potentially many candidates.
    Priority:
      1. If only one row, use it.
      2. Explicit target_email or target_name match (user-selected candidate).
      3. Cross-source overlap with other parsers (GitHub, resume, notes).
      4. Fall back to first row.
    """
    if len(csv_records) <= 1:
        return csv_records

    # 1. Explicit target match — when user selected a specific candidate
    if target_email or target_name:
        t_email = (target_email or "").lower().strip()
        t_name  = (target_name  or "").lower().strip()
        for rec in csv_records:
            d = rec.get("data", {})
            row_emails = {e.lower().strip() for e in d.get("emails", [])}
            row_name   = (d.get("full_name") or "").lower().strip()
            if (t_email and t_email in row_emails) or (t_name and t_name == row_name):
                logger.info("CSV: target-matched row for %r", d.get("full_name"))
                return [rec]
        # Target explicitly set but not found in CSV — this candidate lives only in ATS/other source
        logger.info("CSV: target %r / %r not in CSV — skipping CSV entirely", target_email, target_name)
        return []

    # 2. Cross-source overlap (only when no explicit target)
    other_names:  set[str] = set()
    other_emails: set[str] = set()
    for rec in other_records:
        d = rec.get("data", {})
        n = d.get("full_name", "")
        if n:
            other_names.add(n.lower().strip())
        for e in d.get("emails", []):
            other_emails.add(e.lower().strip())

    if other_names or other_emails:
        for rec in csv_records:
            d = rec.get("data", {})
            row_name   = (d.get("full_name") or "").lower().strip()
            row_emails = {e.lower().strip() for e in d.get("emails", [])}
            if row_name in other_names or row_emails & other_emails:
                logger.info("CSV: cross-source matched row for %r", d.get("full_name"))
                return [rec]

    logger.info("CSV: no match found — using first row only")
    return [csv_records[0]]


def _select_ats_record(
    ats_records: list[dict],
    other_records: list[dict],
    target_email: str | None = None,
    target_name: str | None = None,
) -> list[dict]:
    """
    Pick exactly one ATS record from an array of candidates.
    Same priority as CSV selection.
    """
    if len(ats_records) <= 1:
        return ats_records

    # 1. Explicit target match — when user selected a specific candidate
    if target_email or target_name:
        t_email = (target_email or "").lower().strip()
        t_name  = (target_name  or "").lower().strip()
        for rec in ats_records:
            d = rec.get("data", {})
            row_emails = {e.lower().strip() for e in d.get("emails", [])}
            row_name   = (d.get("full_name") or "").lower().strip()
            if (t_email and t_email in row_emails) or (t_name and t_name == row_name):
                logger.info("ATS: target-matched record for %r", d.get("full_name"))
                return [rec]
        # Target explicitly set but not found in ATS — this candidate lives only in CSV/other source
        logger.info("ATS: target %r / %r not in ATS — skipping ATS entirely", target_email, target_name)
        return []

    # 2. Cross-source overlap (only when no explicit target)
    other_names:  set[str] = set()
    other_emails: set[str] = set()
    for rec in other_records:
        d = rec.get("data", {})
        n = d.get("full_name", "")
        if n:
            other_names.add(n.lower().strip())
        for e in d.get("emails", []):
            other_emails.add(e.lower().strip())

    if other_names or other_emails:
        for rec in ats_records:
            d = rec.get("data", {})
            row_name   = (d.get("full_name") or "").lower().strip()
            row_emails = {e.lower().strip() for e in d.get("emails", [])}
            if row_name in other_names or row_emails & other_emails:
                logger.info("ATS: cross-source matched record for %r", d.get("full_name"))
                return [rec]

    logger.info("ATS: no match found — using first record only")
    return [ats_records[0]]


async def _safe_parse_csv(path: str) -> list[dict]:
    try:
        from pipeline.parsers.csv_parser import parse_csv
        return parse_csv(path)
    except Exception as e:
        logger.error("CSV parser crashed (should not happen): %s", e)
        return []


async def _safe_parse_ats(path: str) -> list[dict]:
    """Parse ATS JSON and return ALL records (one per array element)."""
    try:
        from pipeline.parsers.ats_json_parser import parse_ats_json_all
        return parse_ats_json_all(path)
    except Exception as e:
        logger.error("ATS JSON parser crashed: %s", e)
        return []


async def _safe_parse_github(github_url: str) -> list[dict]:
    try:
        from pipeline.parsers.github_parser import parse_github
        result = await parse_github(github_url)
        return [result] if result.get("data") else []
    except Exception as e:
        logger.error("GitHub parser crashed: %s", e)
        return []


async def _safe_parse_resume(path: str) -> list[dict]:
    try:
        from pipeline.parsers.resume_parser import parse_resume
        result = parse_resume(path)
        return [result] if result.get("data") else []
    except Exception as e:
        logger.error("Resume parser crashed: %s", e)
        return []


async def _safe_parse_notes(path: str) -> list[dict]:
    try:
        from pipeline.parsers.notes_parser import parse_notes
        result = parse_notes(path)
        return [result] if result.get("data") else []
    except Exception as e:
        logger.error("Notes parser crashed: %s", e)
        return []


async def run_pipeline(
    csv_path:     Optional[str] = None,
    ats_path:     Optional[str] = None,
    resume_path:  Optional[str] = None,
    github_url:   Optional[str] = None,
    notes_path:   Optional[str] = None,
    config:       dict = {},
    target_email: Optional[str] = None,
    target_name:  Optional[str] = None,
) -> dict:
    """
    Run the full candidate transformation pipeline.

    Returns a dict with keys:
      - "profile": the canonical profile (or projected output)
      - "validation_errors": list of validation error strings
      - "pipeline_errors": any non-fatal errors logged during processing
      - "sources_used": list of source tags that contributed data
    """
    all_records: list[dict] = []
    csv_records: list[dict] = []
    pipeline_errors: list[str] = []

    # -------------------------------------------------------------------------
    # Stage 1 — Parse all available sources
    # CSV is parsed separately so we can select the right row after seeing
    # what other sources provide.
    # -------------------------------------------------------------------------
    if csv_path and os.path.exists(csv_path):
        try:
            csv_records = await _safe_parse_csv(csv_path)
            logger.info("CSV: extracted %d records", len(csv_records))
        except Exception as e:
            msg = f"CSV parsing failed: {e}"
            pipeline_errors.append(msg)
            logger.error(msg)
    elif csv_path:
        pipeline_errors.append(f"CSV file not found: {csv_path}")

    if ats_path and os.path.exists(ats_path):
        try:
            records = await _safe_parse_ats(ats_path)
            all_records.extend(records)
            logger.info("ATS JSON: extracted %d records", len(records))
        except Exception as e:
            msg = f"ATS JSON parsing failed: {e}"
            pipeline_errors.append(msg)
            logger.error(msg)
    elif ats_path:
        pipeline_errors.append(f"ATS JSON file not found: {ats_path}")

    if github_url:
        try:
            records = await _safe_parse_github(github_url)
            all_records.extend(records)
            logger.info("GitHub: extracted %d records", len(records))
        except Exception as e:
            msg = f"GitHub parsing failed: {e}"
            pipeline_errors.append(msg)
            logger.error(msg)

    if resume_path and os.path.exists(resume_path):
        try:
            records = await _safe_parse_resume(resume_path)
            all_records.extend(records)
            logger.info("Resume: extracted %d records", len(records))
        except Exception as e:
            msg = f"Resume parsing failed: {e}"
            pipeline_errors.append(msg)
            logger.error(msg)
    elif resume_path:
        pipeline_errors.append(f"Resume file not found: {resume_path}")

    if notes_path and os.path.exists(notes_path):
        try:
            records = await _safe_parse_notes(notes_path)
            all_records.extend(records)
            logger.info("Notes: extracted %d records", len(records))
        except Exception as e:
            msg = f"Notes parsing failed: {e}"
            pipeline_errors.append(msg)
            logger.error(msg)
    elif notes_path:
        pipeline_errors.append(f"Notes file not found: {notes_path}")

    # Select one CSV row now that we have signals from other sources
    if csv_records:
        selected = _select_csv_record(csv_records, all_records, target_email, target_name)
        all_records = selected + all_records

    # Select one ATS record if multiple were returned
    ats_records = [r for r in all_records if r.get("source") == "ats_json"]
    if len(ats_records) > 1:
        non_ats = [r for r in all_records if r.get("source") != "ats_json"]
        selected_ats = _select_ats_record(ats_records, non_ats, target_email, target_name)
        all_records = [r for r in all_records if r.get("source") != "ats_json"] + selected_ats

    sources_used = list({r["source"] for r in all_records})

    # Collect unrecognized field feedback from parsers
    unrecognized: dict[str, list[str]] = {}
    for r in all_records:
        src = r.get("source", "unknown")
        cols = r.get("unrecognized_columns") or r.get("unrecognized_fields") or []
        if cols:
            unrecognized[src] = cols

    # -------------------------------------------------------------------------
    # Stage 2 — Merge
    # -------------------------------------------------------------------------
    try:
        profile: CanonicalProfile = merge_profiles(all_records)
    except Exception as e:
        msg = f"Merge failed: {e}"
        pipeline_errors.append(msg)
        logger.error(msg)
        from pipeline.models import make_candidate_id
        profile = CanonicalProfile(candidate_id=make_candidate_id())

    # -------------------------------------------------------------------------
    # Stage 3 — Score
    # -------------------------------------------------------------------------
    try:
        profile = score_profile(profile)
    except Exception as e:
        msg = f"Scoring failed: {e}"
        pipeline_errors.append(msg)
        logger.error(msg)

    # -------------------------------------------------------------------------
    # Stage 4 — Project (optional)
    # -------------------------------------------------------------------------
    validation_errors: list[str] = []
    output_data: Any = profile.model_dump()

    if config and config.get("fields"):
        try:
            engine = ProjectionEngine()
            projected = engine.project(profile, config)
            validation_errors = engine.validate(projected, config)
            output_data = projected
        except Exception as e:
            msg = f"Projection failed: {e}"
            pipeline_errors.append(msg)
            logger.error(msg)
            # Fall back to full profile dict
            output_data = profile.model_dump()

    return {
        "profile": output_data,
        "validation_errors": validation_errors,
        "pipeline_errors": pipeline_errors,
        "sources_used": sources_used,
        "unrecognized_fields": unrecognized,
    }


async def run_sample_pipeline(config: dict = {}) -> dict:
    """
    Run the pipeline on the built-in sample data — FAST variant.

    Uses CSV + ATS JSON only (no GLiNER/resume/notes) so the API demo
    endpoint responds in milliseconds regardless of model warm-up time.
    """
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return await run_pipeline(
        csv_path=os.path.join(base, "samples", "sample_candidates.csv"),
        ats_path=os.path.join(base, "samples", "sample_ats.json"),
        config=config,
    )


async def run_sample_pipeline_full(config: dict = {}) -> dict:
    """
    Run the pipeline on ALL built-in sample sources (CSV + ATS + resume + notes).

    Triggers GLiNER model load on first call — takes 20-40s on first run,
    then ~1-2s on subsequent calls.  Used by CLI --sample flag.
    """
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return await run_pipeline(
        csv_path=os.path.join(base, "samples", "sample_candidates.csv"),
        ats_path=os.path.join(base, "samples", "sample_ats.json"),
        resume_path=os.path.join(base, "samples", "sample_resume.txt"),
        notes_path=os.path.join(base, "samples", "sample_notes.txt"),
        config=config,
    )

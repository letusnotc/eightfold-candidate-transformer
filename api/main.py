"""
FastAPI backend for the Eightfold Candidate Transformer.

Endpoints:
  GET  /health              — health check
  POST /transform           — transform uploaded files + GitHub URL
  POST /transform/sample    — run on built-in sample data (demo mode)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import shutil
import tempfile
from typing import Optional

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so `pipeline` is importable
# whether uvicorn is launched from api/ OR from the project root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load .env from project root (no-op if file absent or python-dotenv not installed)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except ImportError:
    pass


from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Eightfold Candidate Transformer",
    description="Multi-source candidate data transformation pipeline",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _save_upload(upload: UploadFile, tmpdir: str, filename: str) -> str:
    """Save an uploaded file to tmpdir and return its path."""
    dest = os.path.join(tmpdir, filename)
    with open(dest, "wb") as f:
        content = await upload.read()
        f.write(content)
    return dest


def _ext_for(upload: UploadFile) -> str:
    """Get file extension from uploaded filename."""
    if upload.filename:
        _, ext = os.path.splitext(upload.filename)
        return ext.lower()
    return ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Lightweight candidate listing helpers (no full pipeline, just name+email)
# ---------------------------------------------------------------------------

def _list_from_csv(path: str) -> list[dict]:
    try:
        import pandas as pd
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        return []

    name_cols  = {"name", "full_name", "fullname", "candidate_name", "applicant_name", "candidate"}
    email_cols = {"email", "email_address", "emailaddress", "contact_email", "mail", "e-mail"}

    name_col  = next((c for c in df.columns if c.strip().lower() in name_cols), None)
    email_col = next((c for c in df.columns if c.strip().lower() in email_cols), None)

    # Also try first_name + last_name
    fname_col = next((c for c in df.columns if c.strip().lower() in {"first_name", "firstname", "fname"}), None)
    lname_col = next((c for c in df.columns if c.strip().lower() in {"last_name", "lastname", "surname"}), None)

    results = []
    for _, row in df.iterrows():
        name = (str(row[name_col]).strip() if name_col else None) or None
        if not name and fname_col and lname_col:
            first = str(row.get(fname_col, "")).strip()
            last  = str(row.get(lname_col, "")).strip()
            name  = " ".join(filter(None, [first, last])) or None
        email = (str(row[email_col]).strip().lower() if email_col else None) or None
        if name or email:
            results.append({"name": name, "email": email})
    return results


def _list_from_ats(path: str) -> list[dict]:
    try:
        import json as _json
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    name_keys  = {"applicant_name", "name", "fullname", "full_name",
                  "candidate_name", "candidatename", "applicantname"}
    email_keys = {"contact_email", "email", "emailaddress", "email_address",
                  "contactemail", "mail"}

    results = []
    for record in data:
        if not isinstance(record, dict):
            continue
        name = email = None
        for k, v in record.items():
            if not v:
                continue
            kl = k.lower()
            if kl in name_keys and not name:
                name = str(v).strip() or None
            elif kl in email_keys and not email:
                email = str(v).strip().lower() or None
        if name or email:
            results.append({"name": name, "email": email})
    return results


@app.post("/api/candidates")
async def list_candidates(
    csv_file: Optional[UploadFile] = File(None),
    ats_file: Optional[UploadFile] = File(None),
):
    """
    Lightweight endpoint: reads candidate names + emails from CSV and/or ATS JSON.
    Returns a merged list with which sources each candidate appears in.
    Used by the frontend to let the user pick a specific candidate before running
    the full pipeline.
    """
    tmpdir = tempfile.mkdtemp(prefix="eightfold_cands_")
    try:
        csv_path = ats_path = None
        if csv_file and csv_file.filename:
            csv_path = await _save_upload(csv_file, tmpdir, "candidates.csv")
        if ats_file and ats_file.filename:
            ats_path = await _save_upload(ats_file, tmpdir, "ats.json")

        csv_list = _list_from_csv(csv_path) if csv_path else []
        ats_list = _list_from_ats(ats_path) if ats_path else []

        # Merge by email (primary key), then by lowercase name as fallback
        merged: dict[str, dict] = {}

        def _key(c: dict) -> str:
            return (c.get("email") or "").lower() or (c.get("name") or "").lower()

        for c in csv_list:
            k = _key(c)
            if not k:
                continue
            if k not in merged:
                merged[k] = {"name": c.get("name"), "email": c.get("email"), "sources": []}
            merged[k]["sources"].append("csv")

        for c in ats_list:
            k = _key(c)
            if not k:
                continue
            if k not in merged:
                merged[k] = {"name": c.get("name"), "email": c.get("email"), "sources": []}
            if not merged[k]["name"] and c.get("name"):
                merged[k]["name"] = c["name"]
            if not merged[k]["email"] and c.get("email"):
                merged[k]["email"] = c["email"]
            merged[k]["sources"].append("ats_json")

        candidates = list(merged.values())
        return {"candidates": candidates, "total": len(candidates)}

    except Exception as e:
        logger.error("list_candidates error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/transform")
async def transform(
    csv_file:       Optional[UploadFile] = File(None),
    ats_file:       Optional[UploadFile] = File(None),
    resume_file:    Optional[UploadFile] = File(None),
    notes_file:     Optional[UploadFile] = File(None),
    github_url:     Optional[str] = Form(None),
    config:         Optional[str] = Form("{}"),
    target_email:   Optional[str] = Form(None),
    target_name:    Optional[str] = Form(None),
):
    """
    Transform candidate data from multiple sources into a canonical profile.

    Accepts multipart form data with optional:
      - csv_file:    recruiter CSV
      - ats_file:    ATS JSON
      - resume_file: PDF, DOCX, or TXT resume
      - notes_file:  recruiter notes .txt
      - github_url:  GitHub username or URL (form field, not file)
      - config:      output config JSON string
    """
    # Parse config
    try:
        config_dict: dict = json.loads(config or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'config' field")

    tmpdir = tempfile.mkdtemp(prefix="eightfold_")
    csv_path = ats_path = resume_path = notes_path = None

    try:
        # Save uploads to temp dir
        if csv_file and csv_file.filename:
            csv_path = await _save_upload(csv_file, tmpdir, "candidates" + (_ext_for(csv_file) or ".csv"))

        if ats_file and ats_file.filename:
            ats_path = await _save_upload(ats_file, tmpdir, "ats" + (_ext_for(ats_file) or ".json"))

        if resume_file and resume_file.filename:
            resume_path = await _save_upload(resume_file, tmpdir, "resume" + (_ext_for(resume_file) or ".txt"))

        if notes_file and notes_file.filename:
            notes_path = await _save_upload(notes_file, tmpdir, "notes" + (_ext_for(notes_file) or ".txt"))

        # Validate at least one source provided
        has_input = any([csv_path, ats_path, resume_path, notes_path, github_url])
        if not has_input:
            raise HTTPException(
                status_code=400,
                detail="Please provide at least one input source (csv_file, ats_file, resume_file, notes_file, or github_url)",
            )

        # Run pipeline
        from pipeline.orchestrator import run_pipeline
        result = await run_pipeline(
            csv_path=csv_path,
            ats_path=ats_path,
            resume_path=resume_path,
            github_url=github_url or None,
            notes_path=notes_path,
            config=config_dict,
            target_email=target_email or None,
            target_name=target_name or None,
        )

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Transform endpoint error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
    finally:
        # Always clean up temp files
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


@app.post("/transform/sample")
async def transform_sample(config: Optional[str] = Form(default="{}")):
    """
    Run the pipeline on built-in sample data.
    Useful for demos, UI testing, and health checks.
    """
    try:
        config_dict: dict = json.loads(config or "{}")
    except json.JSONDecodeError:
        config_dict = {}

    try:
        from pipeline.orchestrator import run_sample_pipeline
        result = await run_sample_pipeline(config=config_dict)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error("Sample transform error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sample pipeline error: {str(e)}")

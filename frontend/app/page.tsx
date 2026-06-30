"use client";

import { useState, useEffect, useRef } from "react";
import InputPanel from "@/components/InputPanel";
import ConfigPanel from "@/components/ConfigPanel";
import ProfilePanel from "@/components/ProfilePanel";
import CandidateSearch, { type CandidateHint } from "@/components/CandidateSearch";
import { transformCandidate, runSample } from "@/lib/api";

export type PipelineResult = {
  profile: Record<string, unknown>;
  validation_errors: string[];
  pipeline_errors: string[];
  sources_used: string[];
};

export type AppConfig = {
  includeConfidence: boolean;
  includeProvenance: boolean;
  onMissing: "null" | "omit" | "error";
  fields: string[];
};

const DEFAULT_FIELDS = [
  "full_name", "emails", "phones", "skills",
  "experience", "education", "location", "headline",
  "years_experience", "links",
];

const DEFAULT_CONFIG: AppConfig = {
  includeConfidence: true,
  includeProvenance: true,
  onMissing: "null",
  fields: [...DEFAULT_FIELDS],
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [files, setFiles] = useState<{ csv?: File; ats?: File; resume?: File; notes?: File }>({});
  const [githubUrl, setGithubUrl]     = useState("");
  const [config, setConfig]           = useState<AppConfig>(DEFAULT_CONFIG);
  const [result, setResult]           = useState<PipelineResult | null>(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState<string | null>(null);

  // Candidate selection state
  const [candidates, setCandidates]           = useState<CandidateHint[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateHint | null>(null);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const fetchController = useRef<AbortController | null>(null);

  const hasInput = !!(files.csv || files.ats || files.resume || files.notes || githubUrl.trim());
  // Can run: if csv/ats uploaded, a candidate must be selected (or only 1 found)
  // Resume and GitHub are single-person inputs — pipeline cross-matches them automatically
  const needsCandidateSelection =
    (!!files.csv || !!files.ats) &&
    candidates.length > 1 &&
    !files.resume &&
    !githubUrl.trim();
  const canRun = hasInput && (!needsCandidateSelection || !!selectedCandidate);

  // Auto-fetch candidates whenever CSV or ATS file changes
  useEffect(() => {
    if (!files.csv && !files.ats) {
      setCandidates([]);
      setSelectedCandidate(null);
      return;
    }

    // Cancel any in-flight request
    fetchController.current?.abort();
    fetchController.current = new AbortController();

    setCandidatesLoading(true);
    setCandidates([]);
    setSelectedCandidate(null);

    const form = new FormData();
    if (files.csv) form.append("csv_file", files.csv);
    if (files.ats) form.append("ats_file", files.ats);

    fetch(`${API}/api/candidates`, {
      method: "POST",
      body: form,
      signal: fetchController.current.signal,
    })
      .then((r) => r.json())
      .then((data) => {
        const list: CandidateHint[] = data.candidates ?? [];
        setCandidates(list);
        // Auto-select if only one candidate
        if (list.length === 1) setSelectedCandidate(list[0]);
      })
      .catch((e) => { if (e.name !== "AbortError") console.warn("candidates fetch:", e); })
      .finally(() => setCandidatesLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files.csv, files.ats]);

  const buildApiConfig = () => ({
    fields: config.fields.map((f) => ({ path: f, type: "string" })),
    include_confidence: config.includeConfidence,
    include_provenance: config.includeProvenance,
    on_missing: config.onMissing,
  });

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      if (files.csv)    formData.append("csv_file",    files.csv);
      if (files.ats)    formData.append("ats_file",    files.ats);
      if (files.resume) formData.append("resume_file", files.resume);
      if (files.notes)  formData.append("notes_file",  files.notes);
      if (githubUrl.trim()) formData.append("github_url", githubUrl.trim());
      formData.append("config", JSON.stringify(buildApiConfig()));
      if (selectedCandidate?.email) formData.append("target_email", selectedCandidate.email);
      if (selectedCandidate?.name)  formData.append("target_name",  selectedCandidate.name);

      const data = await transformCandidate(formData);
      setResult(data as PipelineResult);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline error");
    } finally {
      setLoading(false);
    }
  };

  const handleSample = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await runSample();
      setResult(data as PipelineResult);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sample pipeline error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      {/* Top bar */}
      <header style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        padding: "0 24px",
        height: 54,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        position: "sticky",
        top: 0,
        zIndex: 10,
        boxShadow: "var(--shadow-sm)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 30, height: 30, background: "var(--accent)",
            borderRadius: 7, display: "flex", alignItems: "center",
            justifyContent: "center", flexShrink: 0,
          }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="3"    width="12" height="1.5" rx="0.75" fill="white"/>
              <rect x="2" y="7.25" width="12" height="1.5" rx="0.75" fill="white"/>
              <rect x="2" y="11.5" width="7"  height="1.5" rx="0.75" fill="white"/>
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-1)", lineHeight: 1.2 }}>
              Candidate Data Transformer
            </div>
            <div style={{ fontSize: 11, color: "var(--text-3)", lineHeight: 1 }}>
              Multi-source pipeline by Eightfold AI
            </div>
          </div>
        </div>

        <button
          className="btn-secondary"
          onClick={handleSample}
          disabled={loading}
          style={{ width: "auto", gap: 6 }}
          id="run-sample-btn"
        >
          {loading
            ? <span className="spinner" style={{ width: 13, height: 13 }} />
            : <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><polygon points="2,1 12,6.5 2,12" fill="currentColor"/></svg>
          }
          Run sample data
        </button>
      </header>

      {/* Error banner */}
      {error && (
        <div style={{
          margin: "12px 24px 0", padding: "10px 14px",
          background: "var(--danger-bg)", border: "1px solid #fca5a5",
          borderRadius: 8, color: "var(--danger)", fontSize: 13, fontWeight: 500,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M7 4v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <circle cx="7" cy="10" r="0.75" fill="currentColor"/>
          </svg>
          {error}
        </div>
      )}

      {/* Main layout */}
      <main style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: 16,
        padding: "16px 24px 32px",
        maxWidth: 1440,
        margin: "0 auto",
        alignItems: "start",
      }}>
        {/* Left panels */}
        <div style={{ display: "flex", gap: 16 }}>
          <InputPanel
            files={files}
            setFiles={setFiles}
            githubUrl={githubUrl}
            setGithubUrl={setGithubUrl}
            loading={loading}
            hasInput={hasInput}
            canRun={canRun}
            onRun={handleRun}
            candidateSearch={
              (files.csv || files.ats) && !files.resume && !githubUrl.trim() ? (
                <div style={{ position: "relative" }}>
                  <CandidateSearch
                    candidates={candidates}
                    selected={selectedCandidate}
                    onSelect={setSelectedCandidate}
                    loading={candidatesLoading}
                  />
                </div>
              ) : null
            }
            needsCandidateSelection={needsCandidateSelection}
          />
          <ConfigPanel config={config} setConfig={setConfig} />
        </div>
        <ProfilePanel result={result} loading={loading} />
      </main>
    </div>
  );
}

"use client";

import React, { useRef, useState } from "react";
import {
  FileSpreadsheet, FileJson, FileText, StickyNote,
  Github, Upload, X, Play, Loader,
} from "lucide-react";

type FileKey = "csv" | "ats" | "resume" | "notes";

const FILE_CONFIGS: {
  key: FileKey;
  label: string;
  accept: string;
  Icon: React.ElementType;
  hint: string;
}[] = [
  { key: "csv",    label: "Recruiter CSV",   accept: ".csv",            Icon: FileSpreadsheet, hint: ".csv" },
  { key: "ats",    label: "ATS JSON",        accept: ".json",           Icon: FileJson,        hint: ".json" },
  { key: "resume", label: "Resume",          accept: ".pdf,.docx,.txt", Icon: FileText,        hint: "PDF / DOCX / TXT" },
  { key: "notes",  label: "Recruiter Notes", accept: ".txt",            Icon: StickyNote,      hint: ".txt" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type Props = {
  files: Partial<Record<FileKey, File>>;
  setFiles: (f: Partial<Record<FileKey, File>>) => void;
  githubUrl: string;
  setGithubUrl: (s: string) => void;
  loading: boolean;
  hasInput: boolean;
  canRun: boolean;
  onRun: () => void;
  candidateSearch?: React.ReactNode;
  needsCandidateSelection?: boolean;
};

export default function InputPanel({
  files, setFiles, githubUrl, setGithubUrl, loading, hasInput, canRun, onRun,
  candidateSearch, needsCandidateSelection,
}: Props) {
  const [dragging, setDragging] = useState<FileKey | null>(null);
  const refs = {
    csv:    useRef<HTMLInputElement>(null),
    ats:    useRef<HTMLInputElement>(null),
    resume: useRef<HTMLInputElement>(null),
    notes:  useRef<HTMLInputElement>(null),
  };

  const handleFile = (key: FileKey, file: File | null) => {
    if (!file) return;
    setFiles({ ...files, [key]: file });
  };

  const removeFile = (key: FileKey) => {
    const next = { ...files };
    delete next[key];
    setFiles(next);
  };

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>
      <div>
        <div className="label">Input Sources</div>
        <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 3 }}>
          Upload any combination of sources
        </p>
      </div>

      {/* File upload zones */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {FILE_CONFIGS.map(({ key, label, accept, Icon, hint }) => {
          const file = files[key];
          return (
            <div
              key={key}
              className={`upload-zone${file ? " has-file" : ""}${dragging === key ? " drag-over" : ""}`}
              onClick={() => refs[key].current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(key); }}
              onDragLeave={() => setDragging(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(null);
                const f = e.dataTransfer.files[0];
                if (f) handleFile(key, f);
              }}
              id={`upload-${key}`}
            >
              <input
                ref={refs[key]}
                type="file"
                accept={accept}
                style={{ display: "none" }}
                onChange={(e) => handleFile(key, e.target.files?.[0] ?? null)}
              />
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Icon
                  size={15}
                  color={file ? "var(--success)" : "var(--text-3)"}
                  strokeWidth={1.75}
                  style={{ flexShrink: 0 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13, fontWeight: 600,
                    color: file ? "var(--text-1)" : "var(--text-2)",
                  }}>
                    {label}
                  </div>
                  {file ? (
                    <div style={{
                      fontSize: 11, color: "var(--success)",
                      marginTop: 1, display: "flex", gap: 6,
                    }}>
                      <span style={{
                        overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap", maxWidth: 160,
                      }}>
                        {file.name}
                      </span>
                      <span style={{ color: "var(--text-3)", flexShrink: 0 }}>
                        {formatBytes(file.size)}
                      </span>
                    </div>
                  ) : (
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 1 }}>
                      Click or drop - {hint}
                    </div>
                  )}
                </div>
                {file ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); removeFile(key); }}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--text-3)",
                      borderRadius: 4,
                      padding: 3,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      flexShrink: 0,
                      lineHeight: 1,
                    }}
                    title="Remove file"
                  >
                    <X size={13} />
                  </button>
                ) : (
                  <Upload size={12} color="var(--text-3)" style={{ flexShrink: 0 }} />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* GitHub URL */}
      <div>
        <label style={{
          fontSize: 12, fontWeight: 600, color: "var(--text-2)",
          display: "flex", alignItems: "center", gap: 5, marginBottom: 6,
        }}>
          <Github size={13} strokeWidth={1.75} />
          GitHub Username or URL
        </label>
        <input
          type="text"
          value={githubUrl}
          onChange={(e) => setGithubUrl(e.target.value)}
          placeholder="torvalds  or  github.com/torvalds"
          id="github-url-input"
        />
      </div>

      <hr className="divider" />

      {/* Active source tags */}
      {hasInput && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          {files.csv    && <span className="skill-badge source-csv"    style={{ fontSize: 11 }}>CSV</span>}
          {files.ats    && <span className="skill-badge source-ats"    style={{ fontSize: 11 }}>ATS JSON</span>}
          {files.resume && <span className="skill-badge source-resume" style={{ fontSize: 11 }}>Resume</span>}
          {files.notes  && <span className="skill-badge source-notes"  style={{ fontSize: 11 }}>Notes</span>}
          {githubUrl    && <span className="skill-badge source-github"  style={{ fontSize: 11 }}>GitHub</span>}
        </div>
      )}

      {/* Candidate search — shown when CSV or ATS JSON is uploaded */}
      {candidateSearch}

      {/* Warning if candidate selection is required */}
      {needsCandidateSelection && !loading && (
        <div style={{
          fontSize: 12, color: "var(--warning)",
          background: "var(--warning-bg)",
          border: "1px solid #fde68a",
          borderRadius: 6, padding: "6px 10px",
        }}>
          Multiple candidates found in CSV/ATS — select one to process.
        </div>
      )}

      {/* Run button */}
      <button
        className="btn-primary"
        onClick={onRun}
        disabled={!canRun || loading}
        id="run-pipeline-btn"
      >
        {loading ? (
          <>
            <Loader size={14} style={{ animation: "spin 0.7s linear infinite" }} />
            Processing...
          </>
        ) : (
          <>
            <Play size={13} fill="white" />
            Run Pipeline
          </>
        )}
      </button>
    </div>
  );
}

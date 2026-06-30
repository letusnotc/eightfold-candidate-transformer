"use client";

import { useState, useRef, useEffect } from "react";
import { Search, User, X, CheckCircle } from "lucide-react";

export type CandidateHint = {
  name: string | null;
  email: string | null;
  sources: string[];
};

type Props = {
  candidates: CandidateHint[];
  selected: CandidateHint | null;
  onSelect: (c: CandidateHint | null) => void;
  loading: boolean;
};

function sourceBadge(src: string) {
  const cls = src === "csv" ? "source-csv" : src === "ats_json" ? "source-ats" : "source-merged";
  const label = src === "csv" ? "CSV" : src === "ats_json" ? "ATS JSON" : src;
  return (
    <span key={src} className={`skill-badge ${cls}`} style={{ fontSize: 10, padding: "1px 6px" }}>
      {label}
    </span>
  );
}

export default function CandidateSearch({ candidates, selected, onSelect, loading }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const filtered = query.trim()
    ? candidates.filter((c) => {
        const q = query.toLowerCase();
        return (
          c.name?.toLowerCase().includes(q) ||
          c.email?.toLowerCase().includes(q)
        );
      })
    : candidates;

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current && !inputRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (loading) {
    return (
      <div style={{
        padding: "10px 12px",
        borderRadius: 8,
        background: "var(--bg)",
        border: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 8,
        fontSize: 13, color: "var(--text-3)",
      }}>
        <span className="spinner" style={{ width: 13, height: 13 }} />
        Reading candidates from files...
      </div>
    );
  }

  if (candidates.length === 0) return null;

  // If only 1 candidate, show as auto-selected info row
  if (candidates.length === 1 && selected) {
    return (
      <div style={{
        padding: "9px 12px",
        borderRadius: 8,
        background: "var(--success-bg)",
        border: "1px solid #bbf7d0",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <CheckCircle size={14} color="var(--success)" />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
            {selected.name ?? selected.email ?? "Unknown"}
          </div>
          {selected.email && (
            <div style={{ fontSize: 11, color: "var(--text-3)" }}>{selected.email}</div>
          )}
        </div>
        <div style={{ display: "flex", gap: 3 }}>
          {selected.sources.map(sourceBadge)}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 5, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
        {candidates.length} candidates found — select one
      </div>

      {/* Selected chip */}
      {selected && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "7px 10px", marginBottom: 6,
          background: "var(--accent-bg)",
          border: "1px solid var(--accent-border)",
          borderRadius: 7,
        }}>
          <CheckCircle size={13} color="var(--accent)" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", lineHeight: 1.2 }}>
              {selected.name ?? selected.email}
            </div>
            {selected.email && selected.name && (
              <div style={{ fontSize: 11, color: "var(--text-3)" }}>{selected.email}</div>
            )}
          </div>
          <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
            {selected.sources.map(sourceBadge)}
          </div>
          <button
            onClick={() => { onSelect(null); setQuery(""); }}
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-3)", padding: 2, display: "flex",
              flexShrink: 0,
            }}
            title="Clear selection"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Search input */}
      <div style={{ position: "relative" }}>
        <div style={{
          position: "absolute", left: 10, top: "50%",
          transform: "translateY(-50%)", pointerEvents: "none",
        }}>
          <Search size={13} color="var(--text-3)" />
        </div>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder="Search by name or email..."
          style={{ paddingLeft: 30, fontSize: 13 }}
        />
      </div>

      {/* Dropdown */}
      {open && filtered.length > 0 && (
        <div
          ref={dropdownRef}
          style={{
            position: "absolute",
            zIndex: 50,
            width: "calc(100% - 0px)",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0,0,0,0.10)",
            marginTop: 4,
            overflow: "hidden",
            maxHeight: 240,
            overflowY: "auto",
          }}
        >
          {filtered.map((c, i) => {
            const isSelected = selected?.email === c.email && selected?.name === c.name;
            const inBoth = c.sources.includes("csv") && c.sources.includes("ats_json");
            return (
              <button
                key={i}
                onClick={() => { onSelect(c); setOpen(false); setQuery(""); }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  width: "100%", padding: "9px 12px", border: "none",
                  background: isSelected ? "var(--accent-bg)" : "transparent",
                  cursor: "pointer", textAlign: "left",
                  borderBottom: i < filtered.length - 1 ? "1px solid var(--border)" : "none",
                  transition: "background 0.1s",
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) (e.currentTarget as HTMLElement).style.background = "var(--bg)";
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) (e.currentTarget as HTMLElement).style.background = "transparent";
                }}
              >
                <div style={{
                  width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                  background: inBoth ? "var(--accent-bg)" : "var(--bg)",
                  border: `1px solid ${inBoth ? "var(--accent-border)" : "var(--border)"}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <User size={13} color={inBoth ? "var(--accent)" : "var(--text-3)"} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", lineHeight: 1.2 }}>
                    {c.name ?? c.email ?? "Unknown"}
                  </div>
                  {c.email && c.name && (
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 1 }}>{c.email}</div>
                  )}
                </div>

                <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
                  {c.sources.map(sourceBadge)}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {open && filtered.length === 0 && query && (
        <div style={{
          marginTop: 4, padding: "10px 12px",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 8, fontSize: 13, color: "var(--text-3)",
        }}>
          No candidates match "{query}"
        </div>
      )}
    </div>
  );
}

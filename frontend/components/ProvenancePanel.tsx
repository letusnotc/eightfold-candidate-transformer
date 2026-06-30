"use client";

import { GitBranch } from "lucide-react";

type ProvenanceEntry = {
  field: string;
  source: string;
  method: string;
};

type Props = {
  provenance: unknown;
};

const SOURCE_LABEL_MAP: Record<string, string> = {
  csv:         "CSV",
  ats_json:    "ATS JSON",
  github:      "GitHub",
  resume_pdf:  "Resume PDF",
  resume_docx: "Resume DOCX",
  resume_txt:  "Resume TXT",
  notes:       "Notes",
  computed:    "Computed",
  merged:      "Merged",
};

const METHOD_COLOR: Record<string, string> = {
  direct:     "var(--accent)",
  regex:      "var(--success)",
  gliner_ner: "#c2410c",
  heuristic:  "var(--warning)",
  union:      "#7e22ce",
};

export default function ProvenancePanel({ provenance }: Props) {
  if (!provenance || !Array.isArray(provenance) || provenance.length === 0) {
    return (
      <div style={{
        padding: "48px 0",
        textAlign: "center",
        color: "var(--text-3)",
        fontSize: 13,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
      }}>
        <div style={{
          width: 40, height: 40,
          borderRadius: 10,
          background: "var(--bg)",
          border: "1.5px dashed var(--border)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <GitBranch size={18} color="var(--text-3)" />
        </div>
        <div>
          No provenance data available.
          <br />
          <span style={{ fontSize: 12, color: "var(--accent)" }}>
            Enable "Provenance trail" in Config.
          </span>
        </div>
      </div>
    );
  }

  const entries = provenance as ProvenanceEntry[];

  return (
    <div className="fade-in">
      <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 12 }}>
        {entries.length} provenance entries recorded
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 12,
        }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["Field", "Source", "Method"].map((h) => (
                <th key={h} style={{
                  textAlign: "left",
                  padding: "6px 12px",
                  color: "var(--text-3)",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  fontSize: 10,
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => {
              const srcKey = entry.source?.split("_")[0] ?? "unknown";
              return (
                <tr
                  key={i}
                  style={{
                    background: i % 2 === 0 ? "var(--bg)" : "transparent",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = "var(--accent-bg)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background =
                      i % 2 === 0 ? "var(--bg)" : "transparent";
                  }}
                >
                  <td style={{
                    padding: "7px 12px",
                    color: "var(--text-1)",
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11,
                  }}>
                    {entry.field}
                  </td>
                  <td style={{ padding: "7px 12px" }}>
                    <span
                      className={`source-${srcKey}`}
                      style={{
                        display: "inline-block",
                        padding: "2px 7px",
                        borderRadius: 4,
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    >
                      {SOURCE_LABEL_MAP[entry.source] ?? entry.source}
                    </span>
                  </td>
                  <td style={{ padding: "7px 12px" }}>
                    <span style={{
                      color: METHOD_COLOR[entry.method] ?? "var(--text-3)",
                      fontSize: 11,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 500,
                    }}>
                      {entry.method}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

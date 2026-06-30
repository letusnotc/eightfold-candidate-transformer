"use client";

import { useState } from "react";
import type { PipelineResult } from "@/app/page";
import ProvenancePanel from "./ProvenancePanel";
import {
  MapPin, Mail, Phone, Github, Linkedin, Globe,
  Download, User, Braces, GitBranch, Loader,
  AlertTriangle, AlertCircle, GraduationCap, Briefcase,
} from "lucide-react";

type Props = {
  result: PipelineResult | null;
  loading: boolean;
};

type Tab = "profile" | "json" | "provenance";

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "#16a34a" : pct >= 60 ? "#ca8a04" : "#dc2626";
  const bg    = pct >= 80 ? "var(--success-bg)" : pct >= 60 ? "var(--warning-bg)" : "var(--danger-bg)";
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--text-3)" }}>Overall confidence</span>
        <span style={{
          fontSize: 12, fontWeight: 700, color,
          background: bg, padding: "1px 8px", borderRadius: 999,
        }}>
          {pct}%
        </span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function InfoRow({ Icon, label, value, href }: {
  Icon: React.ElementType; label: string; value: string; href?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 9, padding: "4px 0" }}>
      <Icon size={14} color="var(--text-3)" strokeWidth={1.75} style={{ marginTop: 2, flexShrink: 0 }} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
          {label}
        </div>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 13, color: "var(--accent)", marginTop: 1, display: "block", wordBreak: "break-all", textDecoration: "none" }}
          >
            {value}
          </a>
        ) : (
          <div style={{ fontSize: 13, color: "var(--text-1)", marginTop: 1, wordBreak: "break-all" }}>
            {value}
          </div>
        )}
      </div>
    </div>
  );
}

function ProfileView({ profile }: { profile: Record<string, unknown> }) {
  const p = profile as Record<string, unknown>;
  const loc      = p.location as Record<string, string> | undefined;
  const links    = p.links as { linkedin?: string; github?: string; portfolio?: string; other?: string[] } | undefined;
  const skills   = (p.skills as { name: string; confidence: number; sources: string[] }[] | string[] | undefined) ?? [];
  const experience = (p.experience as { company?: string; title?: string; start?: string; end?: string }[]) ?? [];
  const education  = (p.education as { institution?: string; degree?: string; field?: string; end_year?: number }[]) ?? [];
  const emails   = (p.emails as string[]) ?? [];
  const phones   = (p.phones as string[]) ?? [];
  const confidence = typeof p.overall_confidence === "number" ? p.overall_confidence
    : typeof p._overall_confidence === "number" ? p._overall_confidence : null;

  const locationStr = loc
    ? [loc.city, loc.region, loc.country].filter(Boolean).join(", ")
    : null;

  return (
    <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Hero */}
      <div style={{
        background: "var(--accent-bg)",
        border: "1px solid var(--accent-border)",
        borderRadius: 10,
        padding: "18px 20px",
      }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text-1)", marginBottom: 4 }}>
          {(p.full_name as string) ?? "Unknown Candidate"}
        </div>
        {!!p.headline && (
          <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 10 }}>
            {p.headline as string}
          </div>
        )}
        {!!p.title && !p.headline && (
          <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 10 }}>
            {p.title as string}{p.company ? ` at ${p.company as string}` : ""}
          </div>
        )}
        {locationStr && (
          <div style={{ fontSize: 12, color: "var(--text-3)", display: "flex", alignItems: "center", gap: 4, marginBottom: 12 }}>
            <MapPin size={12} />
            {locationStr}
          </div>
        )}
        {confidence !== null && <ConfidenceBar value={confidence} />}
      </div>

      {/* Contact */}
      {(emails.length > 0 || phones.length > 0 || links?.github || links?.linkedin || links?.portfolio || (links?.other ?? []).length > 0) && (
        <div>
          <div className="label" style={{ marginBottom: 8 }}>Contact</div>
          <div className="card" style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 2 }}>
            {emails.map((e, i) => (
              <InfoRow key={i} Icon={Mail} label="Email" value={e} href={`mailto:${e}`} />
            ))}
            {phones.map((ph, i) => (
              <InfoRow key={i} Icon={Phone} label="Phone" value={ph} />
            ))}
            {links?.linkedin  && <InfoRow Icon={Linkedin} label="LinkedIn"  value={links.linkedin}  href={links.linkedin} />}
            {links?.github    && <InfoRow Icon={Github}   label="GitHub"    value={links.github}    href={links.github} />}
            {links?.portfolio && <InfoRow Icon={Globe}    label="Portfolio" value={links.portfolio} href={links.portfolio} />}
            {(links?.other ?? []).map((url, i) => {
              const domain = (() => { try { return new URL(url).hostname.replace("www.", ""); } catch { return url; } })();
              return <InfoRow key={i} Icon={Globe} label={domain} value={url} href={url} />;
            })}
          </div>
        </div>
      )}

      {/* Skills */}
      {skills.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 8 }}>Skills ({skills.length})</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {skills.map((s, i) => {
              const name = typeof s === "string" ? s : s.name;
              const sources = typeof s === "string" ? undefined : s.sources;
              return (
                <span className="skill-badge" key={i} title={sources?.join(", ")}>
                  {name}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Experience */}
      {experience.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 5 }}>
            <Briefcase size={11} /> Experience
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {experience.map((e, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 4 }}>
                  <div className="timeline-dot" />
                  {i < experience.length - 1 && <div className="timeline-line" style={{ height: 36 }} />}
                </div>
                <div style={{ paddingBottom: 14 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                    {e.title ?? "Unknown Role"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-2)" }}>
                    {e.company ?? "Unknown Company"}
                    {(e.start || e.end) && (
                      <span style={{ marginLeft: 6, color: "var(--text-3)" }}>
                        {e.start}{e.end ? ` - ${e.end}` : e.start ? " - Present" : ""}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Education */}
      {education.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 5 }}>
            <GraduationCap size={11} /> Education
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {education.map((e, i) => (
              <div key={i} className="card" style={{ padding: "10px 14px" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                  {e.institution ?? "Unknown Institution"}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 1 }}>
                  {[e.degree, e.field].filter(Boolean).join(", ")}
                  {e.end_year && <span style={{ marginLeft: 6, color: "var(--text-3)" }}>{e.end_year}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Years of experience */}
      {typeof p.years_experience === "number" && (
        <div className="card" style={{
          padding: "12px 14px",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <div style={{
            width: 40, height: 40,
            borderRadius: 8,
            background: "var(--accent-bg)",
            border: "1px solid var(--accent-border)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, fontWeight: 700, color: "var(--accent)",
          }}>
            {p.years_experience}
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
              {p.years_experience} years total experience
            </div>
            <div style={{ fontSize: 11, color: "var(--text-3)" }}>
              computed from experience timeline
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function JsonView({ data }: { data: unknown }) {
  const [copied, setCopied] = useState(false);
  const str = JSON.stringify(data, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(str).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button className="btn-secondary" onClick={handleCopy} style={{ fontSize: 12, padding: "5px 12px" }}>
          {copied ? "Copied" : "Copy JSON"}
        </button>
      </div>
      <pre className="json-output">
        {str.split("\n").map((line, i) => {
          const highlighted = line
            .replace(/"([^"]+)":/g, '<span class="json-key">"$1"</span>:')
            .replace(/: "([^"]*)"/g, ': <span class="json-str">"$1"</span>')
            .replace(/: (\d+\.?\d*)/g, ': <span class="json-num">$1</span>')
            .replace(/: (true|false)/g, ': <span class="json-bool">$1</span>')
            .replace(/: null/g, ': <span class="json-null">null</span>');
          return <span key={i} dangerouslySetInnerHTML={{ __html: highlighted + "\n" }} />;
        })}
      </pre>
    </div>
  );
}

const TAB_ICONS: Record<Tab, React.ElementType> = {
  profile:    User,
  json:       Braces,
  provenance: GitBranch,
};

const TAB_LABELS: Record<Tab, string> = {
  profile:    "Profile",
  json:       "JSON",
  provenance: "Provenance",
};

export default function ProfilePanel({ result, loading }: Props) {
  const [tab, setTab] = useState<Tab>("profile");

  const downloadJson = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "candidate_profile.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="card" style={{
      padding: 24,
      minHeight: 520,
      display: "flex",
      flexDirection: "column",
      gap: 16,
    }}>
      {/* Panel header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div className="label">Output</div>
          {result?.sources_used && result.sources_used.length > 0 && (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 5 }}>
              {result.sources_used.map((s) => {
                const srcKey = s.split("_")[0];
                return (
                  <span key={s} className={`skill-badge source-${srcKey}`} style={{ fontSize: 10, padding: "2px 7px" }}>
                    {s}
                  </span>
                );
              })}
            </div>
          )}
        </div>
        {result && (
          <button className="btn-secondary" onClick={downloadJson} style={{ fontSize: 12, gap: 5 }}>
            <Download size={12} />
            Download
          </button>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          padding: "60px 0",
        }}>
          <Loader size={28} color="var(--accent)" style={{ animation: "spin 0.8s linear infinite" }} />
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)" }}>Running pipeline</div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 3 }}>
              Parsing, normalizing, merging, scoring
            </div>
          </div>
        </div>
      )}

      {/* Empty */}
      {!loading && !result && (
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          padding: "60px 0",
          color: "var(--text-3)",
        }}>
          <div style={{
            width: 52, height: 52,
            borderRadius: 14,
            background: "var(--bg)",
            border: "1.5px dashed var(--border)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <User size={22} color="var(--text-3)" />
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)" }}>No results yet</div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 3, lineHeight: 1.5 }}>
              Upload sources and click Run Pipeline,<br />
              or use the sample data button above.
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {!loading && result && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Pipeline errors */}
          {result.pipeline_errors?.length > 0 && (
            <div style={{
              padding: "10px 12px",
              borderRadius: 7,
              background: "var(--warning-bg)",
              border: "1px solid #fde68a",
              fontSize: 12,
              color: "var(--warning)",
              display: "flex",
              flexDirection: "column",
              gap: 3,
            }}>
              {result.pipeline_errors.map((e, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <AlertTriangle size={12} style={{ marginTop: 1, flexShrink: 0 }} />
                  {e}
                </div>
              ))}
            </div>
          )}

          {/* Validation errors */}
          {result.validation_errors?.length > 0 && (
            <div style={{
              padding: "10px 12px",
              borderRadius: 7,
              background: "var(--danger-bg)",
              border: "1px solid #fca5a5",
              fontSize: 12,
              color: "var(--danger)",
              display: "flex",
              flexDirection: "column",
              gap: 3,
            }}>
              {result.validation_errors.map((e, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <AlertCircle size={12} style={{ marginTop: 1, flexShrink: 0 }} />
                  {e}
                </div>
              ))}
            </div>
          )}

          {/* Tab bar */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
            {(["profile", "json", "provenance"] as Tab[]).map((t) => {
              const Icon = TAB_ICONS[t];
              return (
                <button
                  key={t}
                  id={`tab-${t}`}
                  onClick={() => setTab(t)}
                  className={`tab-btn${tab === t ? " active" : ""}`}
                  style={{ display: "flex", alignItems: "center", gap: 5 }}
                >
                  <Icon size={12} strokeWidth={1.75} />
                  {TAB_LABELS[t]}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflowY: "auto", paddingRight: 2 }}>
            {tab === "profile"    && <ProfileView profile={result.profile as Record<string, unknown>} />}
            {tab === "json"       && <JsonView data={result} />}
            {tab === "provenance" && (
              <ProvenancePanel provenance={(result.profile as Record<string, unknown>)?._provenance} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

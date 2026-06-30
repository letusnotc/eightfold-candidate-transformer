"use client";

import type { AppConfig } from "@/app/page";

const AVAILABLE_FIELDS = [
  { key: "full_name",          label: "Full Name" },
  { key: "emails",             label: "Emails" },
  { key: "phones",             label: "Phones" },
  { key: "skills",             label: "Skills" },
  { key: "experience",         label: "Experience" },
  { key: "education",          label: "Education" },
  { key: "location",           label: "Location" },
  { key: "headline",           label: "Headline" },
  { key: "years_experience",   label: "Years Exp." },
  { key: "links",              label: "Links" },
  { key: "provenance",         label: "Provenance" },
  { key: "overall_confidence", label: "Confidence" },
];

type Props = {
  config: AppConfig;
  setConfig: (c: AppConfig) => void;
};

function Toggle({ checked, onChange, id }: { checked: boolean; onChange: (v: boolean) => void; id: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      id={id}
      onClick={() => onChange(!checked)}
      style={{
        width: 34,
        height: 18,
        borderRadius: 9,
        border: "none",
        background: checked ? "var(--accent)" : "#cbd5e1",
        cursor: "pointer",
        position: "relative",
        transition: "background 0.2s",
        flexShrink: 0,
        padding: 0,
      }}
    >
      <div style={{
        width: 13,
        height: 13,
        borderRadius: "50%",
        background: "white",
        position: "absolute",
        top: "50%",
        transform: "translateY(-50%)",
        left: checked ? 18 : 3,
        transition: "left 0.2s",
        boxShadow: "0 1px 2px rgba(0,0,0,0.15)",
      }} />
    </button>
  );
}

export default function ConfigPanel({ config, setConfig }: Props) {
  const toggleField = (key: string) => {
    const fields = config.fields.includes(key)
      ? config.fields.filter((f) => f !== key)
      : [...config.fields, key];
    setConfig({ ...config, fields });
  };

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>
      <div>
        <div className="label">Output Config</div>
        <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 3 }}>
          Control what the pipeline returns
        </p>
      </div>

      {/* Toggles */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[
          { key: "includeConfidence", label: "Confidence scores", id: "toggle-confidence" },
          { key: "includeProvenance", label: "Provenance trail",  id: "toggle-provenance" },
        ].map(({ key, label, id }) => (
          <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, color: "var(--text-2)" }}>{label}</span>
            <Toggle
              id={id}
              checked={config[key as keyof AppConfig] as boolean}
              onChange={(v) => setConfig({ ...config, [key]: v })}
            />
          </div>
        ))}
      </div>

      <hr className="divider" />

      {/* On missing value */}
      <div>
        <div className="label" style={{ marginBottom: 8 }}>On missing value</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {(["null", "omit", "error"] as const).map((opt) => {
            const active = config.onMissing === opt;
            return (
              <label
                key={opt}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                  padding: "6px 10px",
                  borderRadius: 7,
                  background: active ? "var(--accent-bg)" : "transparent",
                  border: `1px solid ${active ? "var(--accent-border)" : "transparent"}`,
                  transition: "all 0.15s",
                }}
              >
                <input
                  type="radio"
                  name="onMissing"
                  id={`on-missing-${opt}`}
                  value={opt}
                  checked={active}
                  onChange={() => setConfig({ ...config, onMissing: opt })}
                  style={{ accentColor: "var(--accent)", margin: 0 }}
                />
                <span style={{
                  fontSize: 12, fontFamily: "monospace",
                  color: active ? "var(--accent)" : "var(--text-2)",
                  fontWeight: active ? 600 : 400,
                }}>
                  {opt}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <hr className="divider" />

      {/* Fields */}
      <div>
        <div className="label" style={{ marginBottom: 8 }}>Fields to include</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "5px 6px" }}>
          {AVAILABLE_FIELDS.map(({ key, label }) => {
            const active = config.fields.includes(key);
            return (
              <label
                key={key}
                id={`field-toggle-${key}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  cursor: "pointer",
                  fontSize: 12,
                  color: active ? "var(--accent)" : "var(--text-2)",
                  transition: "color 0.15s",
                  userSelect: "none",
                  padding: "2px 0",
                }}
              >
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => toggleField(key)}
                  style={{ accentColor: "var(--accent)", width: 13, height: 13, margin: 0 }}
                />
                {label}
              </label>
            );
          })}
        </div>
      </div>

      {/* Presets */}
      <div>
        <div className="label" style={{ marginBottom: 7 }}>Presets</div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            className="btn-secondary"
            style={{ fontSize: 12, padding: "5px 10px" }}
            onClick={() => setConfig({
              ...config,
              fields: AVAILABLE_FIELDS.map((f) => f.key),
              includeConfidence: true,
              includeProvenance: true,
              onMissing: "null",
            })}
          >
            All fields
          </button>
          <button
            className="btn-secondary"
            style={{ fontSize: 12, padding: "5px 10px" }}
            onClick={() => setConfig({
              ...config,
              fields: ["full_name", "emails", "phones", "skills", "years_experience"],
              includeConfidence: false,
              includeProvenance: false,
              onMissing: "omit",
            })}
          >
            Compact
          </button>
        </div>
      </div>
    </div>
  );
}

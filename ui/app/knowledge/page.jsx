"use client";

import { useState } from "react";
import { apiGet, apiPostForm } from "@/lib/api";

const TABS = [
  { key: "search",  label: "Search Knowledge Base" },
  { key: "rubrics", label: "Company Rubrics" },
];

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState("search");

  return (
    <div style={{ maxWidth: "860px", margin: "0 auto" }}>
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ marginBottom: "0.25rem" }}>Knowledge Base</h1>
        <p className="text-muted">
          Manage the documents the AI uses for candidate screening, interview planning, and offer drafting.
        </p>
      </div>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: "0.25rem", marginBottom: "2rem", borderBottom: "2px solid var(--border)" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: "0.6rem 1.25rem", fontSize: "0.875rem",
              fontWeight: activeTab === t.key ? 700 : 500,
              border: "none",
              borderBottom: `2px solid ${activeTab === t.key ? "var(--indigo-600)" : "transparent"}`,
              marginBottom: "-2px", cursor: "pointer",
              backgroundColor: "transparent",
              color: activeTab === t.key ? "var(--indigo-600)" : "var(--gray-500)",
              transition: "all 0.15s",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "search"  && <SearchTab />}
      {activeTab === "rubrics" && <UploadTab namespace="company_rubrics" label="Company Rubrics" description="Hiring standards, seniority levels, interview process guidelines, and salary/compensation bands. The AI uses this to screen candidates and draft offer letters." accept=".pdf,.txt,.docx,.md,.csv" />}
    </div>
  );
}


// ── Search tab ────────────────────────────────────────────────────────────────

function SearchTab() {
  const namespace = "company_rubrics";
  const [query, setQuery]         = useState("");
  const [results, setResults]     = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) { setError("Enter a search query."); return; }
    setLoading(true); setError(null); setResults([]);
    try {
      const data = await apiGet(`/rag/search?namespace=${namespace}&query=${encodeURIComponent(query)}`);
      setResults(data.results || []);
      if (!data.results?.length) setError("No results found. Try a different query or upload documents first.");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSearch} style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.75rem", alignItems: "flex-end" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.3rem" }}>Query</label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={namespace === "company_rubrics" ? "e.g. senior engineer expectations" : "e.g. senior engineer salary San Francisco"}
              style={{ width: "100%", padding: "0.55rem 0.75rem", border: "1px solid #e2e8f0", borderRadius: "6px", fontSize: "0.875rem" }}
            />
          </div>
          <button type="submit" disabled={loading} className="button button-primary" style={{ padding: "0.55rem 1.5rem" }}>
            {loading ? "Searching..." : "Search"}
          </button>
        </div>
      </form>

      {error && (
        <div style={{ padding: "0.75rem 1rem", backgroundColor: "#fee2e2", borderRadius: "6px", marginBottom: "1rem" }}>
          <p style={{ fontSize: "0.875rem", color: "#991b1b", margin: 0 }}>{error}</p>
        </div>
      )}

      {results.length > 0 && (
        <div>
          <p className="text-small text-muted" style={{ marginBottom: "0.75rem" }}>{results.length} result{results.length !== 1 ? "s" : ""}</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {results.map((r, i) => (
              <div key={i} style={{ padding: "1rem", backgroundColor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                  {r.metadata?.source && (
                    <p style={{ fontSize: "0.8rem", color: "#64748b", margin: 0 }}>
                      {r.metadata.source}
                    </p>
                  )}
                  {r.score != null && (
                    <span style={{ fontSize: "0.75rem", backgroundColor: "#dbeafe", color: "#1e40af", padding: "0.2rem 0.5rem", borderRadius: "4px" }}>
                      {(r.score * 100).toFixed(0)}% match
                    </span>
                  )}
                </div>
                <p style={{ fontSize: "0.875rem", lineHeight: 1.6, color: "#1e293b", margin: 0, whiteSpace: "pre-wrap" }}>
                  {r.text || r.content || "(No text)"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ── Upload tab ─────────────────────────────────────────────────────────────────

function UploadTab({ namespace, label, description, accept }) {
  const [file, setFile]           = useState(null);
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess]     = useState(null);
  const [error, setError]         = useState(null);
  const [dragging, setDragging]   = useState(false);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true); setError(null); setSuccess(null);
    try {
      const form = new FormData();
      form.append("namespace", namespace);
      form.append("document_file", file);
      form.append("document_name", file.name);
      const data = await apiPostForm("/rag/index", form);
      setSuccess(data.message || "Uploaded successfully.");
      setFile(null);
      if (namespace === "company_rubrics") {
        localStorage.setItem("hiregraph_rubrics_uploaded", "true");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ margin: "0 0 0.4rem" }}>{label}</h3>
        <p className="text-muted" style={{ marginBottom: "1.25rem", fontSize: "0.9rem" }}>{description}</p>

        {/* Formatting guidance - structured docs retrieve far more reliably */}
        {namespace === "company_rubrics" && (
          <div style={{
            marginBottom: "1.25rem", padding: "0.9rem 1rem",
            backgroundColor: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: "8px",
            fontSize: "0.85rem", color: "#1e3a8a", lineHeight: 1.6,
          }}>
            <strong>📑 For best results, structure your rubric into labelled sections.</strong>
            {" "}Start each section with a heading line like{" "}
            <code style={{ background: "#dbeafe", padding: "0 0.3rem", borderRadius: "4px" }}>SECTION 4 - INTERVIEW PROCESS AND ROUNDS FORMAT</code>{" "}
            wrapped in <code style={{ background: "#dbeafe", padding: "0 0.3rem", borderRadius: "4px" }}>=====</code> rule lines.
            The AI splits on these headings and keeps each section together, so a
            query like “interview process” reliably retrieves the right section.
            Recommended headings: hiring standards &amp; seniority, scoring criteria per role,
            interview process &amp; rounds, salary &amp; equity, bias rules, JD details.
          </div>
        )}

        {/* Drop zone */}
        <div
          onClick={() => !file && document.getElementById(`file-${namespace}`)?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault(); setDragging(false);
            const f = e.dataTransfer.files[0];
            if (f) setFile(f);
          }}
          style={{
            border: `2px dashed ${dragging ? "#3b82f6" : file ? "#22c55e" : "#cbd5e1"}`,
            borderRadius: "8px", padding: "2rem", textAlign: "center",
            cursor: file ? "default" : "pointer",
            backgroundColor: dragging ? "#eff6ff" : file ? "#f0fdf4" : "#f8fafc",
            transition: "all 0.15s", marginBottom: "1rem",
          }}
        >
          {file ? (
            <div>
              <p style={{ fontWeight: 600, color: "#166534", margin: "0 0 0.25rem" }}>
                {file.name}
              </p>
              <p className="text-small text-muted" style={{ margin: 0 }}>
                {(file.size / 1024).toFixed(0)} KB
              </p>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}
              >
                Remove
              </button>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: "2rem", marginBottom: "0.4rem" }}>📁</div>
              <p style={{ fontWeight: 600, margin: "0 0 0.2rem", color: "#1e293b" }}>Click or drag a file here</p>
              <p className="text-small text-muted" style={{ margin: 0 }}>Accepted: {accept}</p>
            </div>
          )}
          <input
            id={`file-${namespace}`}
            type="file"
            accept={accept}
            style={{ display: "none" }}
            onChange={(e) => { if (e.target.files[0]) setFile(e.target.files[0]); e.target.value = ""; }}
          />
        </div>

        {error && (
          <p style={{ fontSize: "0.875rem", color: "#dc2626", marginBottom: "0.75rem" }}>{error}</p>
        )}
        {success && (
          <p style={{ fontSize: "0.875rem", color: "#16a34a", marginBottom: "0.75rem" }}>{success}</p>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="button button-primary"
          style={{ width: "100%" }}
        >
          {uploading ? "Uploading..." : `Upload to ${label}`}
        </button>
      </div>

      <div style={{ padding: "1rem", backgroundColor: "#f8fafc", borderRadius: "8px", fontSize: "0.875rem", color: "#64748b" }}>
        <strong style={{ color: "#1e293b" }}>How this works:</strong>{" "}
        Uploaded documents are chunked and stored in a vector database. During screening the AI retrieves relevant sections to calibrate scoring against your hiring bar. During offer drafting it retrieves your compensation bands to justify salary recommendations.
      </div>
    </div>
  );
}

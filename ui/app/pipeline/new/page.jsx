"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { apiPostForm } from "@/lib/api";
import Link from "next/link";

export default function NewPipelinePage() {
  const router = useRouter();
  const [jdText, setJdText]       = useState("");
  const [files, setFiles]         = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]         = useState(null);
  const [dragging, setDragging]   = useState(false);
  const fileInputRef              = useRef(null);

  const addFiles = (incoming) => {
    const valid = Array.from(incoming).filter(f => f.name.endsWith(".pdf") || f.name.endsWith(".docx"));
    setFiles(prev => {
      const existing = new Set(prev.map(f => `${f.name}-${f.size}`));
      return [...prev, ...valid.filter(f => !existing.has(`${f.name}-${f.size}`))];
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!jdText.trim())    { setError("Paste the job description text first."); return; }
    if (!files.length)     { setError("Add at least one resume file."); return; }
    setSubmitting(true);
    try {
      const form = new FormData();
      form.append("job_description_text", jdText);
      files.forEach(f => form.append("resume_files", f));
      const result = await apiPostForm("/pipeline/start", form);
      if (result.thread_id) router.push(`/pipeline/${result.thread_id}`);
      else setError("Pipeline created but no ID returned.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 780, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <Link href="/" style={{ fontSize: "0.82rem", color: "var(--gray-400)", display: "inline-flex", alignItems: "center", gap: "0.3rem", marginBottom: "1rem" }}>
          ← Back
        </Link>
        <h1 style={{ marginBottom: "0.35rem" }}>New Pipeline</h1>
        <p className="text-muted" style={{ margin: 0 }}>
          Paste the job description and upload resumes. The AI handles the rest.
        </p>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: "1.5rem" }}>{error}</div>}

      <form onSubmit={handleSubmit}>
        <div style={{ display: "grid", gap: "1.25rem" }}>

          {/* JD Section */}
          <div className="card" style={{ padding: "1.75rem" }}>
            <div style={{ marginBottom: "1rem" }}>
              <h3 style={{ marginBottom: "0.25rem" }}>Job Description</h3>
              <p className="text-muted" style={{ margin: 0, fontSize: "0.82rem" }}>
                Paste the full JD. The AI extracts title, required skills, seniority, and salary range.
              </p>
            </div>
            <textarea
              value={jdText}
              onChange={e => setJdText(e.target.value)}
              placeholder={"We are looking for a Senior Backend Engineer...\n\nRequirements:\n- 5+ years of Python experience\n- Strong knowledge of distributed systems\n- Experience with FastAPI, Docker, Kubernetes\n\nNice to have:\n- Familiarity with LLMs\n- AWS/GCP experience"}
              rows={13}
              required
              style={{
                padding: "0.85rem 1rem", lineHeight: "1.7", fontSize: "0.875rem",
                borderColor: jdText ? "var(--indigo-500)" : "var(--border)",
                background: jdText ? "var(--indigo-50)" : "var(--surface)",
              }}
            />
            {jdText && (
              <p style={{ fontSize: "0.75rem", color: "var(--gray-400)", marginTop: "0.4rem" }}>
                {jdText.split(/\s+/).filter(Boolean).length} words
              </p>
            )}
          </div>

          {/* Resumes Section */}
          <div className="card" style={{ padding: "1.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
              <div>
                <h3 style={{ marginBottom: "0.25rem" }}>Candidate Resumes</h3>
                <p className="text-muted" style={{ margin: 0, fontSize: "0.82rem" }}>
                  Upload PDF or DOCX files. Each file = one candidate.
                </p>
              </div>
              {files.length > 0 && (
                <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--indigo-600)" }}>
                  {files.length} file{files.length > 1 ? "s" : ""}
                </span>
              )}
            </div>

            {/* Drop zone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
              style={{
                border: `2px dashed ${dragging ? "var(--indigo-500)" : files.length ? "var(--green-400)" : "var(--border)"}`,
                borderRadius: "var(--radius-lg)", padding: "2.5rem 1rem", textAlign: "center",
                cursor: "pointer", transition: "all 0.15s",
                background: dragging ? "var(--indigo-50)" : files.length ? "var(--green-50)" : "var(--gray-50)",
                marginBottom: files.length ? "1rem" : 0,
              }}
            >
              <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>
                {files.length ? "✅" : "📂"}
              </div>
              <p style={{ fontWeight: 600, color: "var(--gray-700)", margin: "0 0 0.2rem" }}>
                {files.length ? "Add more files" : "Click or drag files here"}
              </p>
              <p style={{ fontSize: "0.8rem", color: "var(--gray-400)", margin: 0 }}>PDF or DOCX accepted</p>
              <input
                ref={fileInputRef}
                type="file" accept=".pdf,.docx" multiple
                style={{ display: "none" }}
                onChange={e => { addFiles(e.target.files); e.target.value = ""; }}
              />
            </div>

            {/* File chips */}
            {files.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {files.map((f, i) => (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "0.55rem 0.85rem",
                    background: "var(--green-50)", border: "1px solid #bbf7d0",
                    borderRadius: "var(--radius)", fontSize: "0.85rem",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                      <span style={{ fontSize: "1rem" }}>{f.name.endsWith(".pdf") ? "📄" : "📝"}</span>
                      <span style={{ fontWeight: 600, color: "var(--green-700)" }}>{f.name}</span>
                      <span style={{ color: "var(--gray-400)", fontSize: "0.75rem" }}>{(f.size / 1024).toFixed(0)} KB</span>
                    </div>
                    <button type="button" onClick={() => setFiles(prev => prev.filter((_, j) => j !== i))}
                      style={{ color: "var(--red-500)", fontWeight: 700, fontSize: "1.1rem", lineHeight: 1, padding: "0 0.2rem" }}>
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
            <Link href="/" className="button button-secondary" style={{ textDecoration: "none" }}>
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting || !jdText.trim() || !files.length}
              className="button button-primary"
              style={{ minWidth: 160, padding: "0.7rem 1.5rem" }}
            >
              {submitting ? (
                <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <div className="loading" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Starting...
                </span>
              ) : "Start Pipeline →"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

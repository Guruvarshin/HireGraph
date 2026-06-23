"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import Link from "next/link";

const STAGE_LABELS = {
  jd_parsing:             "Parsing JD",
  resume_screening:       "Screening",
  shortlist_review:       "Review Shortlist",
  interview_planning:     "Planning Interviews",
  finalist_review:        "Approve Plans",
  awaiting_feedback:      "Awaiting Feedback",
  interview_evaluation:   "Evaluating",
  offer_candidates_review:"Select for Offers",
  offer_drafting:         "Drafting Offers",
  offer_review:           "Review Offers",
  sending_offers:         "Sending Offers",
  completed:              "Completed",
};

const STATUS_STYLES = {
  processing:                { dot: "#6366f1", bg: "#eef2ff", text: "#4338ca" },
  awaiting_human:            { dot: "#f59e0b", bg: "#fffbeb", text: "#b45309" },
  awaiting_interview_feedback:{ dot: "#f59e0b", bg: "#fffbeb", text: "#b45309" },
  completed:                 { dot: "#22c55e", bg: "#f0fdf4", text: "#15803d" },
  failed:                    { dot: "#ef4444", bg: "#fef2f2", text: "#dc2626" },
};

export default function HomePage() {
  const [pipelines, setPipelines] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  useEffect(() => { fetchPipelines(); }, []);

  const fetchPipelines = async () => {
    try {
      setLoading(true); setError(null);
      const data = await apiGet("/pipeline");
      setPipelines(data.runs || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  };

  return (
    <div>
      {/* Page header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "2rem" }}>
        <div>
          <h1 style={{ marginBottom: "0.3rem" }}>Pipelines</h1>
          <p className="text-muted" style={{ margin: 0 }}>Manage your active and completed recruiting pipelines</p>
        </div>
        <Link
          href="/pipeline/new"
          className="button button-primary"
          style={{ textDecoration: "none", padding: "0.65rem 1.25rem" }}
        >
          + New Pipeline
        </Link>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div style={{ textAlign: "center", padding: "5rem 0" }}>
          <div className="loading" style={{ width: 28, height: 28, margin: "0 auto 1rem" }} />
          <p className="text-muted">Loading pipelines...</p>
        </div>
      ) : pipelines.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "5rem 2rem",
          background: "var(--surface)", border: "2px dashed var(--border)",
          borderRadius: "var(--radius-xl)",
        }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🚀</div>
          <h3 style={{ marginBottom: "0.5rem" }}>No pipelines yet</h3>
          <p className="text-muted" style={{ marginBottom: "1.75rem" }}>
            Create your first pipeline to start screening candidates
          </p>
          <Link href="/pipeline/new" className="button button-primary" style={{ textDecoration: "none" }}>
            Create Pipeline
          </Link>
        </div>
      ) : (
        <div className="grid">
          {pipelines.map((p) => {
            const st = STATUS_STYLES[p.status] || STATUS_STYLES.processing;
            return (
              <Link key={p.thread_id} href={`/pipeline/${p.thread_id}`} style={{ textDecoration: "none" }}>
                <div className="card" style={{ height: "100%", cursor: "pointer", transition: "all 0.18s" }}
                  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-md)"; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}
                >
                  {/* Title row */}
                  <div style={{ marginBottom: "1rem" }}>
                    <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem", color: "var(--gray-900)" }}>
                      {p.job_title || "Untitled Position"}
                    </h3>
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: "0.4rem",
                      fontSize: "0.75rem", fontWeight: 600, padding: "0.25rem 0.65rem",
                      borderRadius: "var(--radius-full)", background: st.bg, color: st.text,
                    }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: st.dot, animation: p.status === "processing" ? "spin 1s linear infinite" : undefined }} />
                      {STAGE_LABELS[p.current_stage] || p.current_stage}
                    </span>
                  </div>

                  {/* Stats row */}
                  <div style={{ display: "flex", gap: "1.25rem", marginBottom: "1.25rem" }}>
                    {p.shortlist_count > 0 && (
                      <div>
                        <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--gray-900)", lineHeight: 1 }}>{p.shortlist_count}</div>
                        <div style={{ fontSize: "0.72rem", color: "var(--gray-400)", marginTop: "0.1rem" }}>shortlisted</div>
                      </div>
                    )}
                  </div>

                  {/* Footer */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border-light)", paddingTop: "0.85rem" }}>
                    <span style={{ fontSize: "0.78rem", color: "var(--gray-400)" }}>{formatDate(p.created_at)}</span>
                    <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--indigo-600)" }}>
                      View →
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

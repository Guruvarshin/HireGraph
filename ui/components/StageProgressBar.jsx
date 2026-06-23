const STAGES = [
  { key: "jd_parsing",              label: "Parse JD"         },
  { key: "resume_screening",         label: "Screen"           },
  { key: "shortlist_review",         label: "Shortlist"        },
  { key: "interview_planning",       label: "Plan"             },
  { key: "finalist_review",          label: "Approve Plans"    },
  { key: "awaiting_feedback",        label: "Feedback"         },
  { key: "interview_evaluation",     label: "Evaluate"         },
  { key: "offer_candidates_review",  label: "Select Offers"    },
  { key: "offer_drafting",           label: "Draft Offers"     },
  { key: "offer_review",             label: "Review Offers"    },
  { key: "sending_offers",           label: "Send"             },
  { key: "completed",                label: "Done"             },
];

export default function StageProgressBar({ currentStage }) {
  const currentIdx = STAGES.findIndex(s => s.key === currentStage);

  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: "var(--radius-lg)", padding: "1.25rem 1.5rem",
    }}>
      {/* Step nodes */}
      <div style={{ display: "flex", alignItems: "center", overflowX: "auto", gap: 0 }}>
        {STAGES.map((stage, idx) => {
          const done    = idx < currentIdx;
          const current = idx === currentIdx;
          const pending = idx > currentIdx;

          return (
            <div key={stage.key} style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
              {/* Node */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 56 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "0.72rem", fontWeight: 700, transition: "all 0.2s",
                  background: done    ? "var(--green-500)"  :
                              current ? "var(--indigo-600)" : "var(--gray-100)",
                  color:      done    ? "#fff"              :
                              current ? "#fff"              : "var(--gray-400)",
                  border: current ? "3px solid var(--indigo-100)" : "none",
                  boxShadow: current ? "0 0 0 3px rgba(99,102,241,0.15)" : "none",
                }}>
                  {done ? (
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  ) : current ? (
                    <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#fff" }} />
                  ) : (
                    <span>{idx + 1}</span>
                  )}
                </div>
                <span style={{
                  fontSize: "0.65rem", marginTop: "0.35rem", fontWeight: current ? 700 : 500,
                  color: done ? "var(--green-600)" : current ? "var(--indigo-600)" : "var(--gray-400)",
                  textAlign: "center", lineHeight: 1.2, maxWidth: 60,
                }}>
                  {stage.label}
                </span>
              </div>

              {/* Connector */}
              {idx < STAGES.length - 1 && (
                <div style={{
                  height: 2, width: 24, flexShrink: 0, marginBottom: 18,
                  background: done ? "var(--green-400)" : "var(--gray-200)",
                  transition: "background 0.3s",
                }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

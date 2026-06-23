import { useState, useEffect } from "react";

export default function FeedbackForm({ candidate, plan, feedback, onChange }) {
  const rounds = plan?.rounds || [];

  const makeInitial = () =>
    rounds.reduce((acc, round) => {
      acc[round.round_number] = {
        round_number: round.round_number,
        interviewer_name: "",
        recommendation: "maybe",
        technical_score: 3,
        communication_score: 3,
        culture_score: 3,
        notes: "",
        conducted: true,   // false = round was skipped (candidate rejected earlier)
      };
      return acc;
    }, {});

  const [roundFeedback, setRoundFeedback] = useState(makeInitial);
  // Index of the round after which the candidate was rejected (-1 = not rejected early)
  const [rejectedAfterRound, setRejectedAfterRound] = useState(-1);

  // Notify parent on every change
  useEffect(() => {
    if (!onChange) return;
    // Strip the internal `conducted` UI flag before sending to parent/API
    const conducted = Object.values(roundFeedback)
      .filter((fb) => fb.conducted)
      .map(({ conducted: _, ...rest }) => rest);
    onChange({
      candidate_id: candidate.candidate_id,
      round_feedbacks: conducted,
    });
  }, [roundFeedback, rejectedAfterRound]);

  const update = (roundNum, field, value) => {
    setRoundFeedback((prev) => ({
      ...prev,
      [roundNum]: {
        ...prev[roundNum],
        [field]:
          ["technical_score", "communication_score", "culture_score"].includes(field)
            ? parseInt(value, 10)
            : value,
      },
    }));
  };

  const handleRejectedAfter = (roundNum) => {
    const newVal = rejectedAfterRound === roundNum ? -1 : roundNum;
    setRejectedAfterRound(newVal);
    // Mark rounds after this one as not-conducted
    setRoundFeedback((prev) => {
      const updated = { ...prev };
      rounds.forEach((r) => {
        updated[r.round_number] = {
          ...updated[r.round_number],
          conducted: newVal === -1 || r.round_number <= newVal,
        };
      });
      return updated;
    });
  };

  const conductedCount = Object.values(roundFeedback).filter((fb) => fb.conducted && fb.interviewer_name.trim()).length;
  const totalConducted = Object.values(roundFeedback).filter((fb) => fb.conducted).length;

  const getRoundTypeLabel = (type) =>
    (type || "").split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

  const inputStyle = {
    width: "100%", padding: "0.5rem",
    border: "1px solid #e5e7eb", borderRadius: "4px", fontSize: "0.875rem",
  };

  return (
    <div className="card" style={{ marginBottom: "1.5rem" }}>
      {/* Header */}
      <div style={{ marginBottom: "1rem" }}>
        <h3 className="card-title" style={{ marginBottom: "0.15rem" }}>{candidate.name}</h3>
        {candidate.email && (
          <p className="text-small" style={{ color: "#3b82f6", margin: "0 0 0.25rem" }}>✉ {candidate.email}</p>
        )}
        <p className="text-small text-muted" style={{ margin: 0 }}>
          {conductedCount} of {totalConducted} conducted round{totalConducted !== 1 ? "s" : ""} filled in
          {rejectedAfterRound !== -1 && (
            <span style={{ marginLeft: "0.5rem", color: "#dc2626", fontWeight: 500 }}>
              (Rejected after Round {rejectedAfterRound})
            </span>
          )}
        </p>
      </div>

      {/* Progress bar */}
      {totalConducted > 0 && (
        <div style={{ marginBottom: "1.25rem" }}>
          <div style={{ width: "100%", height: "5px", backgroundColor: "#e5e7eb", borderRadius: "3px", overflow: "hidden" }}>
            <div style={{ width: `${(conductedCount / totalConducted) * 100}%`, height: "100%", backgroundColor: "#2563eb", transition: "width 0.2s" }} />
          </div>
        </div>
      )}

      {rounds.map((round) => {
        const fb = roundFeedback[round.round_number] || {};
        const isSkipped = !fb.conducted;
        const isRejectionPoint = rejectedAfterRound === round.round_number;

        return (
          <div key={round.round_number} style={{
            border: `1px solid ${isSkipped ? "#e5e7eb" : isRejectionPoint ? "#fca5a5" : "#e5e7eb"}`,
            borderRadius: "6px", marginBottom: "0.75rem",
            opacity: isSkipped ? 0.5 : 1,
            backgroundColor: isSkipped ? "#f9fafb" : "#fff",
          }}>
            {/* Round header */}
            <div style={{ padding: "0.75rem 1rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <p style={{ fontWeight: 600, fontSize: "0.9rem", margin: 0 }}>
                  Round {round.round_number}: {getRoundTypeLabel(round.type)}
                  {isSkipped && <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", color: "#9ca3af" }}>(Not conducted)</span>}
                </p>
                <p className="text-small text-muted" style={{ margin: 0 }}>{round.duration_minutes} min</p>
              </div>
              {/* Rejected-after toggle — only show on conducted rounds */}
              {!isSkipped && (
                <button
                  type="button"
                  onClick={() => handleRejectedAfter(round.round_number)}
                  style={{
                    fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "4px",
                    border: `1px solid ${isRejectionPoint ? "#dc2626" : "#e5e7eb"}`,
                    backgroundColor: isRejectionPoint ? "#fee2e2" : "#f9fafb",
                    color: isRejectionPoint ? "#dc2626" : "#64748b",
                    cursor: "pointer", flexShrink: 0, marginLeft: "0.75rem",
                  }}
                  title="Mark candidate as rejected after this round — subsequent rounds won't be evaluated"
                >
                  {isRejectionPoint ? "✗ Rejected here (undo)" : "Rejected after this round?"}
                </button>
              )}
            </div>

            {/* Round body — only for conducted rounds */}
            {!isSkipped && (
              <div style={{ padding: "0 1rem 1rem" }}>
                <div style={{ marginBottom: "0.75rem" }}>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 500, marginBottom: "0.3rem" }}>
                    Interviewer Name <span style={{ color: "#dc2626" }}>*</span>
                  </label>
                  <input type="text" value={fb.interviewer_name || ""} style={inputStyle}
                    onChange={(e) => update(round.round_number, "interviewer_name", e.target.value)}
                    placeholder="e.g. Jane Smith" />
                </div>

                <div style={{ marginBottom: "0.75rem" }}>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 500, marginBottom: "0.3rem" }}>Recommendation</label>
                  <select value={fb.recommendation || "maybe"} style={inputStyle}
                    onChange={(e) => update(round.round_number, "recommendation", e.target.value)}>
                    <option value="strong_hire">Strong Hire</option>
                    <option value="hire">Hire</option>
                    <option value="maybe">Maybe</option>
                    <option value="no_hire">No Hire</option>
                  </select>
                </div>

                <div style={{ padding: "0.75rem", backgroundColor: "#f9fafb", borderRadius: "4px", marginBottom: "0.75rem" }}>
                  <p style={{ fontSize: "0.8rem", fontWeight: 500, marginBottom: "0.6rem" }}>Scores (1–5)</p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
                    {[["technical_score", "Technical"], ["communication_score", "Communication"], ["culture_score", "Culture Fit"]].map(([key, label]) => (
                      <div key={key}>
                        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.2rem" }}>{label}</label>
                        <select value={fb[key] || 3} style={inputStyle}
                          onChange={(e) => update(round.round_number, key, e.target.value)}>
                          <option value="1">1 – Poor</option>
                          <option value="2">2 – Below Avg</option>
                          <option value="3">3 – Average</option>
                          <option value="4">4 – Good</option>
                          <option value="5">5 – Excellent</option>
                        </select>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 500, marginBottom: "0.3rem" }}>Notes</label>
                  <textarea value={fb.notes || ""} rows={3} style={{ ...inputStyle, fontFamily: "inherit" }}
                    onChange={(e) => update(round.round_number, "notes", e.target.value)}
                    placeholder="Strengths, concerns, specific examples..." />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

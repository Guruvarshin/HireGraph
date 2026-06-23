import { useState } from "react";

export default function EvaluationCard({ candidate, evaluation, onApprove }) {
  const [approved, setApproved] = useState(evaluation?.human_approved ?? null);

  if (!evaluation) {
    return (
      <div className="card">
        <p className="text-muted">No evaluation available for this candidate.</p>
      </div>
    );
  }


  const getRecommendationStyle = (rec) => {
    switch (rec) {
      case "strong_hire":
        return { bg: "#dcfce7", color: "#166534", label: "Strong Hire" };
      case "hire":
        return { bg: "#d1fae5", color: "#065f46", label: "Hire" };
      case "maybe":
        return { bg: "#fef3c7", color: "#92400e", label: "Maybe" };
      case "no_hire":
        return { bg: "#fee2e2", color: "#991b1b", label: "No Hire" };
      default:
        return { bg: "#f3f4f6", color: "#374151", label: "Unknown" };
    }
  };

  const recStyle = getRecommendationStyle(evaluation.final_recommendation);


  const ConfidenceBar = ({ confidence }) => {
    const percentage = (confidence || 0) * 100;
    const color = confidence >= 0.8 ? "#16a34a" : confidence >= 0.6 ? "#ea580c" : "#dc2626";

    return (
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
          <span style={{ fontSize: "0.875rem", fontWeight: "500" }}>Decision Confidence</span>
          <span style={{ fontSize: "0.875rem", fontWeight: "600" }}>
            {(percentage.toFixed(0))}%
          </span>
        </div>
        <div
          style={{
            width: "100%",
            height: "8px",
            backgroundColor: "#e5e7eb",
            borderRadius: "4px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${percentage}%`,
              height: "100%",
              backgroundColor: color,
              transition: "width 0.2s",
            }}
          />
        </div>
        <p className="text-small text-muted" style={{ marginTop: "0.5rem" }}>
          {confidence >= 0.8
            ? "High confidence. Interviewer feedback was consistent and clear."
            : confidence >= 0.6
              ? "Moderate confidence. Some variation in interviewer opinions, but a clear trend."
              : "Low confidence. Significant disagreement between interviewers. Review dissenting notes carefully."}
        </p>
      </div>
    );
  };


  const handleApprove = () => {
    setApproved(true);
    onApprove(candidate, true);
  };

  const handleReject = () => {
    setApproved(false);
    onApprove(candidate, false);
  };


  return (
    <div className="card" style={{ marginBottom: "1.5rem" }}>
      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <h3 className="card-title">{candidate.name}</h3>
        <p className="text-small text-muted">Interview Evaluation</p>
      </div>

      {}
      <div
        style={{
          padding: "1.5rem",
          backgroundColor: recStyle.bg,
          borderRadius: "8px",
          marginBottom: "1.5rem",
          textAlign: "center",
        }}
      >
        <h2 style={{ color: recStyle.color, marginBottom: "0.5rem" }}>
          {recStyle.label}
        </h2>
        <div
          style={{
            fontSize: "2.5rem",
            fontWeight: "700",
            color: recStyle.color,
            marginBottom: "0.5rem",
          }}
        >
          {evaluation.composite_score}
        </div>
        <p style={{ color: recStyle.color, fontSize: "0.875rem" }}>
          Composite Score (0-100)
        </p>
      </div>

      {}
      <div style={{ marginBottom: "1.5rem", padding: "1rem", backgroundColor: "#f9fafb", borderRadius: "4px" }}>
        <ConfidenceBar confidence={evaluation.confidence} />
      </div>

      {}
      <div
        style={{
          padding: "1rem",
          backgroundColor: evaluation.recommended_for_offer ? "#d1fae5" : "#fee2e2",
          borderRadius: "4px",
          marginBottom: "1.5rem",
        }}
      >
        <p
          style={{
            color: evaluation.recommended_for_offer ? "#065f46" : "#991b1b",
            fontWeight: "500",
            fontSize: "0.875rem",
          }}
        >
          {evaluation.recommended_for_offer
            ? "✓ AI Recommends for Offer"
            : "✗ AI Does Not Recommend for Offer"}
        </p>
        <p className="text-small" style={{ color: evaluation.recommended_for_offer ? "#065f46" : "#991b1b", marginTop: "0.25rem" }}>
          {evaluation.recommended_for_offer
            ? "Based on interview feedback, this candidate meets the bar for an offer."
            : "Interview feedback suggests this candidate may not be the right fit."}
        </p>
      </div>

      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "0.75rem" }}>
          Evaluation Reasoning
        </h4>
        <p className="text-small" style={{ color: "#374151", lineHeight: "1.6" }}>
          {evaluation.reasoning || "No reasoning provided."}
        </p>
      </div>

      {}
      {evaluation.dissenting_notes && (
        <div
          style={{
            padding: "1rem",
            backgroundColor: "#fef3c7",
            borderLeft: "4px solid #ea580c",
            borderRadius: "4px",
            marginBottom: "1.5rem",
          }}
        >
          <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "0.5rem", color: "#92400e" }}>
            ⚠ Dissenting Notes
          </h4>
          <p className="text-small" style={{ color: "#92400e", lineHeight: "1.6" }}>
            {evaluation.dissenting_notes}
          </p>
          <p className="text-small" style={{ color: "#92400e", marginTop: "0.5rem", fontStyle: "italic" }}>
            Interviewers had conflicting opinions. Review their feedback carefully before making a final decision.
          </p>
        </div>
      )}

      {}
      <div
        style={{
          padding: "1rem",
          backgroundColor:
            approved === true ? "#dcfce7" : approved === false ? "#fee2e2" : "#f3f4f6",
          borderRadius: "4px",
          marginBottom: "1rem",
        }}
      >
        <p
          style={{
            fontSize: "0.875rem",
            color:
              approved === true ? "#166534" : approved === false ? "#991b1b" : "#6b7280",
            marginBottom: "0.5rem",
          }}
        >
          {approved === true
            ? "✓ Selected for Offer"
            : approved === false
              ? "✗ Not Selected"
              : "• Awaiting your decision"}
        </p>
      </div>

      {}
      <div style={{ display: "flex", gap: "0.75rem" }}>
        <button
          className="button"
          style={{
            flex: 1,
            padding: "0.75rem",
            backgroundColor: approved === true ? "#16a34a" : "#e5e7eb",
            color: approved === true ? "white" : "#1f2937",
            fontWeight: "500",
            cursor: "pointer",
          }}
          onClick={handleApprove}
        >
          ✓ Select for Offer
        </button>
        <button
          className="button"
          style={{
            flex: 1,
            padding: "0.75rem",
            backgroundColor: approved === false ? "#dc2626" : "#e5e7eb",
            color: approved === false ? "white" : "#1f2937",
            fontWeight: "500",
            cursor: "pointer",
          }}
          onClick={handleReject}
        >
          ✗ Do Not Offer
        </button>
      </div>
    </div>
  );
}

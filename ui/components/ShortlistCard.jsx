import { useState } from "react";

export default function ShortlistCard({
  candidate,
  score,
  onApprove,
  onEmailChange,
}) {
  const placeholderEmails = ["placeholder@example.com", ""];
  const initialEmail = placeholderEmails.includes(candidate.email) ? "" : (candidate.email || "");
  const [email, setEmail] = useState(initialEmail);
  const [approved, setApproved] = useState(score?.human_approved ?? null);
  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  if (!score) {
    return (
      <div className="card">
        <p className="text-muted">No screening score available for this candidate.</p>
      </div>
    );
  }


  const dims = score.dimension_scores || {};
  const overallScore = score.overall_score || 0;


  const handleApprove = () => {
    setApproved(true);
    onApprove(candidate, true);
  };

  const handleReject = () => {
    setApproved(false);
    onApprove(candidate, false);
  };

  const handleEmailChange = (newEmail) => {
    setEmail(newEmail);
    onEmailChange(candidate.candidate_id, newEmail);
  };


  const ScoreBar = ({ label, value, maxValue = 100 }) => {
    const percentage = (value / maxValue) * 100;
    const color = value >= 80 ? "#16a34a" : value >= 60 ? "#ea580c" : "#dc2626";

    return (
      <div style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
          <span style={{ fontSize: "0.875rem", fontWeight: "500" }}>{label}</span>
          <span style={{ fontSize: "0.875rem", fontWeight: "600" }}>{value}</span>
        </div>
        <div style={{ width: "100%", height: "8px", backgroundColor: "#e5e7eb", borderRadius: "4px" }}>
          <div
            style={{
              width: `${percentage}%`,
              height: "100%",
              backgroundColor: color,
              borderRadius: "4px",
              transition: "width 0.2s",
            }}
          />
        </div>
      </div>
    );
  };


  const BiasFlags = ({ flags }) => {
    if (!flags || flags.length === 0) {
      return <p className="text-small text-muted">No bias signals detected.</p>;
    }

    return (
      <div>
        {flags.map((flag, idx) => (
          <div
            key={idx}
            style={{
              padding: "0.75rem",
              marginBottom: "0.5rem",
              backgroundColor: "#fef3c7",
              borderLeft: "3px solid #ea580c",
              borderRadius: "4px",
              fontSize: "0.875rem",
              color: "#92400e",
            }}
          >
            {flag}
          </div>
        ))}
      </div>
    );
  };


  const approvalBadgeStyle =
    approved === true
      ? { color: "#166534", backgroundColor: "#dcfce7" }
      : approved === false
        ? { color: "#991b1b", backgroundColor: "#fee2e2" }
        : { color: "#6b7280", backgroundColor: "#f3f4f6" };


  return (
    <div className="card" style={{ marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <h3 className="card-title" style={{ margin: 0 }}>{candidate.name}</h3>
            {score.recommended_for_shortlist ? (
              <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.2rem 0.5rem", borderRadius: "999px", backgroundColor: "#dcfce7", color: "#166534" }}>
                AI Recommended
              </span>
            ) : (
              <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.2rem 0.5rem", borderRadius: "999px", backgroundColor: "#fef3c7", color: "#92400e" }}>
                Below Threshold
              </span>
            )}
          </div>
          <p className="text-small text-muted" style={{ marginTop: "0.25rem" }}>
            {candidate.file_name}
          </p>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: "2rem", fontWeight: "700", color: overallScore >= 70 ? "#16a34a" : overallScore >= 50 ? "#ea580c" : "#dc2626" }}>
            {overallScore}
          </div>
          <p className="text-small text-muted">/ 100</p>
        </div>
      </div>

      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <label style={{ display: "block", fontSize: "0.875rem", fontWeight: "500", marginBottom: "0.5rem" }}>
          Candidate Email <span style={{ color: "#dc2626" }}>*</span>
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => handleEmailChange(e.target.value)}
          placeholder="jane@example.com"
          style={{
            width: "100%",
            padding: "0.5rem",
            border: `1px solid ${email && !emailValid ? "#dc2626" : emailValid ? "#22c55e" : "#e5e7eb"}`,
            borderRadius: "4px",
            fontSize: "0.875rem",
          }}
        />
        {!emailValid && (
          <p style={{ marginTop: "0.25rem", fontSize: "0.8rem", color: "#dc2626" }}>
            A valid email is required before you can approve this candidate.
          </p>
        )}
      </div>

      {}
      <div style={{ marginBottom: "1.5rem", padding: "1rem", backgroundColor: "#f9fafb", borderRadius: "4px" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "1rem" }}>Score Breakdown</h4>
        <ScoreBar label="Skills Match" value={dims.skills_match || 0} />
        <ScoreBar label="Experience Relevance" value={dims.experience_relevance || 0} />
        <ScoreBar label="Seniority Signal" value={dims.seniority_signal || 0} />
        <ScoreBar label="Resume Quality" value={dims.resume_quality || 0} />
      </div>

      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "0.5rem" }}>Screener's Analysis</h4>
        <p className="text-small" style={{ color: "#374151", lineHeight: "1.6" }}>
          {score.reasoning || "No reasoning provided."}
        </p>
      </div>

      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "0.75rem" }}>Bias Check</h4>
        <BiasFlags flags={score.bias_flags} />
        <p className="text-small text-muted" style={{ marginTop: "0.75rem" }}>
          These flags highlight potential sources of bias. Review them to ensure your decision is based on skills and
          experience, not demographic factors.
        </p>
      </div>

      {}
      <div
        style={{
          padding: "1rem",
          backgroundColor: approvalBadgeStyle.backgroundColor,
          borderRadius: "4px",
          marginBottom: "1rem",
        }}
      >
        <p style={{ color: approvalBadgeStyle.color, fontSize: "0.875rem", marginBottom: "0.75rem" }}>
          {approved === true
            ? "✓ Approved for interview"
            : approved === false
              ? "✗ Rejected"
              : "• No decision yet"}
        </p>
      </div>

      {}
      <div style={{ display: "flex", gap: "0.75rem" }}>
        <button
          className="button"
          disabled={!emailValid}
          style={{
            flex: 1,
            padding: "0.75rem",
            backgroundColor: !emailValid ? "#e5e7eb" : approved === true ? "#16a34a" : "#e5e7eb",
            color: !emailValid ? "#9ca3af" : approved === true ? "white" : "#1f2937",
            fontWeight: "500",
            cursor: emailValid ? "pointer" : "not-allowed",
            opacity: emailValid ? 1 : 0.6,
          }}
          onClick={emailValid ? handleApprove : undefined}
          title={!emailValid ? "Enter a valid candidate email first" : ""}
        >
          ✓ Approve
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
          ✗ Reject
        </button>
      </div>
    </div>
  );
}

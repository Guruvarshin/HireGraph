import { useState } from "react";

// IST is UTC+5:30
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

// Parse a UTC ISO string → { date: "YYYY-MM-DD", time: "HH:MM" } in IST
function isoToParts(iso) {
  if (!iso) return { date: "", time: "" };
  try {
    const istMs  = new Date(iso).getTime() + IST_OFFSET_MS;
    const istStr = new Date(istMs).toISOString(); // now in "IST" expressed as UTC
    return { date: istStr.slice(0, 10), time: istStr.slice(11, 16) };
  } catch {
    return { date: "", time: "" };
  }
}

// Build UTC ISO string from IST date + time (HH:MM 24-hr)
function partsToIso(date, time) {
  if (!date || !time) return null;
  const istMs = new Date(`${date}T${time}:00.000Z`).getTime();
  return new Date(istMs - IST_OFFSET_MS).toISOString();
}

// 24-hour half-hour slots - IST
const TIME_OPTIONS = Array.from({ length: 24 * 2 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, "0");
  const m = i % 2 === 0 ? "00" : "30";
  return { value: `${h}:${m}`, label: `${h}:${m} IST` };
});

function isValidEmail(e) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((e || "").trim());
}

const PLACEHOLDER_EMAILS = ["placeholder@example.com", "", null, undefined];

export default function InterviewPlanCard({ candidate, plan, onUpdatePlan, onApprove, onCandidateEmailChange }) {
  const [expandedRound, setExpandedRound] = useState(0);
  const [approved, setApproved] = useState(null);
  const [rounds, setRounds] = useState(plan?.rounds || []);

  const needsCandidateEmail = PLACEHOLDER_EMAILS.includes(candidate?.email);
  const [candidateEmail, setCandidateEmail] = useState(
    needsCandidateEmail ? "" : (candidate?.email || "")
  );
  const candidateEmailValid = isValidEmail(candidateEmail);
  // Show the email at the top once it's valid (either pre-filled or just entered)
  const displayEmail = candidateEmailValid ? candidateEmail : null;

  const updateRounds = (updated) => {
    setRounds(updated);
    onUpdatePlan({ ...plan, rounds: updated });
  };

  const handleEmailChange = (roundIdx, interpIdx, newEmail) => {
    updateRounds(rounds.map((r, ri) => {
      if (ri !== roundIdx) return r;
      const emails = [...(r.interviewer_emails || [])];
      emails[interpIdx] = newEmail;
      return { ...r, interviewer_emails: emails };
    }));
  };

  const handleDateChange = (roundIdx, newDate) => {
    const { time } = isoToParts(rounds[roundIdx]?.scheduled_at);
    updateRounds(rounds.map((r, ri) =>
      ri === roundIdx ? { ...r, scheduled_at: partsToIso(newDate, time || "09:00") } : r
    ));
  };

  const handleTimeChange = (roundIdx, newTime) => {
    const { date } = isoToParts(rounds[roundIdx]?.scheduled_at);
    updateRounds(rounds.map((r, ri) =>
      ri === roundIdx ? { ...r, scheduled_at: partsToIso(date || "", newTime) } : r
    ));
  };

  // Validation: every approved round needs date + all interviewer emails
  const roundErrors = (roundIdx) => {
    const r = rounds[roundIdx];
    const errs = [];
    const { date, time } = isoToParts(r.scheduled_at);
    if (!date) errs.push("date");
    if (!time) errs.push("time");
    (r.interviewers || []).forEach((role, i) => {
      if (!isValidEmail((r.interviewer_emails || [])[i]))
        errs.push(`email for ${role}`);
    });
    return errs;
  };

  const allRoundsValid = rounds.every((_, i) => roundErrors(i).length === 0) &&
    (!needsCandidateEmail || candidateEmailValid);

  const handleApprove = () => {
    if (!allRoundsValid) return;
    setApproved(true);
    onApprove(plan, true);
  };

  const handleReject = () => {
    setApproved(false);
    onApprove(plan, false);
  };

  const getRoundLabel = (type) =>
    (type || "").split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

  const inputBase = {
    width: "100%", padding: "0.55rem 0.75rem",
    border: "1px solid #e2e8f0", borderRadius: "6px",
    fontSize: "0.875rem", backgroundColor: "#fff",
  };

  return (
    <div className="card" style={{ marginBottom: "1.5rem" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.25rem" }}>
        <h3 className="card-title" style={{ marginBottom: "0.2rem" }}>{candidate.name}</h3>
        {displayEmail && (
          <p className="text-small" style={{ margin: "0 0 0.25rem", color: "#3b82f6" }}>
            ✉ {displayEmail}
          </p>
        )}
        <p className="text-small text-muted" style={{ margin: 0 }}>
          {rounds.length} interview round{rounds.length !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Candidate email - only shown if missing */}
      {needsCandidateEmail && (
        <div style={{
          marginBottom: "1.25rem", padding: "1rem",
          backgroundColor: "#fffbeb", border: "1px solid #fcd34d", borderRadius: "8px",
        }}>
          <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem", color: "#92400e" }}>
            Candidate Email <span style={{ color: "#dc2626" }}>*</span>
          </label>
          <p className="text-small" style={{ color: "#92400e", marginBottom: "0.6rem" }}>
            No email was found in the resume. Enter it to send the interview invite.
          </p>
          <input
            type="email"
            value={candidateEmail}
            onChange={(e) => {
              setCandidateEmail(e.target.value);
              if (onCandidateEmailChange) onCandidateEmailChange(candidate.candidate_id, e.target.value);
            }}
            placeholder="candidate@example.com"
            style={{
              ...inputBase,
              borderColor: candidateEmail ? (candidateEmailValid ? "#22c55e" : "#fca5a5") : "#fcd34d",
              backgroundColor: candidateEmailValid ? "#f0fdf4" : "#fff",
            }}
          />
          {candidateEmail && !candidateEmailValid && (
            <p style={{ fontSize: "0.75rem", color: "#dc2626", marginTop: "0.25rem" }}>Enter a valid email address.</p>
          )}
        </div>
      )}

      {/* Rounds */}
      <div style={{ marginBottom: "1.25rem" }}>
        {rounds.map((round, roundIdx) => {
          const isExpanded = expandedRound === roundIdx;
          const errs = roundErrors(roundIdx);
          const complete = errs.length === 0;
          const { date, time } = isoToParts(round.scheduled_at);

          return (
            <div key={roundIdx} style={{
              border: `1px solid ${complete ? "#86efac" : "#e5e7eb"}`,
              borderRadius: "8px", marginBottom: "0.75rem", overflow: "hidden",
            }}>
              {/* Accordion header */}
              <div
                onClick={() => setExpandedRound(isExpanded ? -1 : roundIdx)}
                style={{
                  padding: "0.9rem 1rem", cursor: "pointer",
                  backgroundColor: isExpanded ? "#f0f9ff" : complete ? "#f0fdf4" : "#f9fafb",
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}
              >
                <div>
                  <h4 style={{ fontWeight: 600, margin: 0, fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    Round {round.round_number}: {round.title || getRoundLabel(round.type)}
                    <span style={{
                      fontSize: "0.68rem", fontWeight: 600, padding: "0.1rem 0.5rem",
                      borderRadius: "999px", background: "#eef2ff", color: "#4338ca",
                    }}>
                      {getRoundLabel(round.type)}
                    </span>
                  </h4>
                  {round.focus && (
                    <p className="text-small text-muted" style={{ margin: "0.2rem 0 0", fontStyle: "italic" }}>
                      {round.focus}
                    </p>
                  )}
                  <p className="text-small text-muted" style={{ margin: "0.15rem 0 0" }}>
                    {round.duration_minutes} min
                    {complete
                      ? ` · ${date} at ${TIME_OPTIONS.find(t => t.value === time)?.label || time}`
                      : ` · ${errs.length} field${errs.length !== 1 ? "s" : ""} required`}
                  </p>
                </div>
                <span style={{ fontSize: "1.2rem", color: complete ? "#16a34a" : "#94a3b8" }}>
                  {complete ? "✓" : isExpanded ? "−" : "+"}
                </span>
              </div>

              {/* Expanded body */}
              {isExpanded && (
                <div style={{ padding: "1.25rem", borderTop: "1px solid #e5e7eb" }}>

                  {/* Date + Time - side by side */}
                  <div style={{ marginBottom: "1.25rem" }}>
                    <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                      Date & Time <span style={{ color: "#dc2626" }}>*</span>{" "}
                      <span style={{ fontSize: "0.75rem", color: "#64748b", fontWeight: 400 }}>IST (UTC+5:30)</span>
                    </label>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                      <div>
                        <input
                          type="date"
                          value={date}
                          onChange={(e) => handleDateChange(roundIdx, e.target.value)}
                          style={{
                            ...inputBase,
                            borderColor: date ? "#22c55e" : "#fca5a5",
                            backgroundColor: date ? "#f0fdf4" : "#fff",
                          }}
                        />
                        {!date && <p style={{ fontSize: "0.75rem", color: "#dc2626", marginTop: "0.2rem" }}>Pick a date</p>}
                      </div>
                      <div>
                        <select
                          value={time || ""}
                          onChange={(e) => handleTimeChange(roundIdx, e.target.value)}
                          style={{
                            ...inputBase,
                            borderColor: time ? "#22c55e" : "#fca5a5",
                            backgroundColor: time ? "#f0fdf4" : "#fff",
                          }}
                        >
                          <option value="">-- Select time --</option>
                          {TIME_OPTIONS.map((t) => (
                            <option key={t.value} value={t.value}>{t.label}</option>
                          ))}
                        </select>
                        {!time && <p style={{ fontSize: "0.75rem", color: "#dc2626", marginTop: "0.2rem" }}>Pick a time</p>}
                      </div>
                    </div>
                  </div>

                  {/* Interviewer Emails */}
                  <div style={{ marginBottom: "1.25rem" }}>
                    <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                      Interviewer Emails <span style={{ color: "#dc2626" }}>*</span>
                    </label>
                    {(round.interviewers || []).map((roleName, interpIdx) => {
                      const val = (round.interviewer_emails || [])[interpIdx] || "";
                      const valid = isValidEmail(val);
                      return (
                        <div key={interpIdx} style={{ marginBottom: "0.6rem" }}>
                          <p style={{ fontSize: "0.75rem", color: "#64748b", marginBottom: "0.2rem" }}>{roleName}</p>
                          <input
                            type="email"
                            value={val}
                            onChange={(e) => handleEmailChange(roundIdx, interpIdx, e.target.value)}
                            placeholder="interviewer@company.com"
                            style={{
                              ...inputBase,
                              borderColor: val ? (valid ? "#22c55e" : "#fca5a5") : "#e2e8f0",
                              backgroundColor: val && valid ? "#f0fdf4" : "#fff",
                            }}
                          />
                          {val && !valid && (
                            <p style={{ fontSize: "0.75rem", color: "#dc2626", marginTop: "0.2rem" }}>Enter a valid email</p>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Suggested Must-Ask Questions */}
                  <div>
                    <p style={{ fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                      Suggested Must-Ask Questions
                    </p>
                    <ol style={{ paddingLeft: "1.25rem", margin: 0 }}>
                      {(round.questions || []).map((q, qi) => (
                        <li key={qi} style={{ fontSize: "0.875rem", lineHeight: 1.6, marginBottom: "0.5rem", color: "#1e293b" }}>
                          {q}
                        </li>
                      ))}
                    </ol>
                    <p className="text-small text-muted" style={{ marginTop: "0.6rem" }}>
                      AI-generated from this candidate's resume. Adapt freely.
                    </p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Status */}
      <div style={{
        padding: "0.9rem 1rem", borderRadius: "6px", marginBottom: "1rem",
        backgroundColor: approved === true ? "#dcfce7" : approved === false ? "#fee2e2" : "#f8fafc",
        border: `1px solid ${approved === true ? "#86efac" : approved === false ? "#fca5a5" : "#e2e8f0"}`,
      }}>
        <p style={{ fontSize: "0.875rem", fontWeight: 500, margin: 0,
          color: approved === true ? "#166534" : approved === false ? "#991b1b" : "#475569" }}>
          {approved === true ? "✓ Approved. Candidate advances to interviews."
            : approved === false ? "✗ Rejected. Candidate will not be interviewed."
            : "Fill in all fields, then approve or reject this plan."}
        </p>
        {approved === false && (
          <p className="text-small" style={{ color: "#991b1b", margin: "0.25rem 0 0" }}>
            This candidate is dropped from this pipeline.
          </p>
        )}
        {!approved && !allRoundsValid && (
          <p className="text-small" style={{ color: "#dc2626", margin: "0.25rem 0 0" }}>
            Complete date, time, and interviewer emails for all rounds before approving.
          </p>
        )}
      </div>

      {/* Buttons */}
      <div style={{ display: "flex", gap: "0.75rem" }}>
        <button
          onClick={handleApprove}
          disabled={!allRoundsValid}
          style={{
            flex: 1, padding: "0.75rem", borderRadius: "6px", fontWeight: 600, fontSize: "0.9rem",
            cursor: allRoundsValid ? "pointer" : "not-allowed",
            backgroundColor: allRoundsValid ? (approved === true ? "#16a34a" : "#22c55e") : "#e5e7eb",
            color: allRoundsValid ? "white" : "#9ca3af",
            border: "none", opacity: allRoundsValid ? 1 : 0.6,
          }}
          title={!allRoundsValid ? "Complete all required fields first" : ""}
        >
          ✓ Approve Plan
        </button>
        <button
          onClick={handleReject}
          style={{
            flex: 1, padding: "0.75rem", borderRadius: "6px", fontWeight: 600, fontSize: "0.9rem",
            cursor: "pointer", border: "1px solid #fca5a5",
            backgroundColor: approved === false ? "#dc2626" : "#fee2e2",
            color: approved === false ? "white" : "#991b1b",
          }}
        >
          ✗ Reject Candidate
        </button>
      </div>
    </div>
  );
}

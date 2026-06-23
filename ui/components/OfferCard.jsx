import { useState } from "react";

export default function OfferCard({ candidate, offer, onUpdate, onApprove }) {
  // Support both prop names for backwards compatibility
  const handleUpdate = onUpdate || onApprove;
  const [approved, setApproved] = useState(offer?.human_approved ?? null);
  const [salary, setSalary] = useState(offer?.human_modified_salary || offer?.base_salary || 0);
  const [equity, setEquity] = useState(offer?.human_modified_equity || offer?.equity || "");
  const [startDate, setStartDate] = useState(offer?.human_modified_start_date || offer?.start_date || "");
  const [letterText, setLetterText] = useState(offer?.offer_letter_text || "");
  const letterModified = letterText !== (offer?.offer_letter_text || "");

  if (!offer) {
    return (
      <div className="card">
        <p className="text-muted">No offer available for this candidate.</p>
      </div>
    );
  }


  const salaryModified = salary !== offer.base_salary;
  const equityModified = equity !== (offer.equity || "");
  const dateModified = startDate !== (offer.start_date || "");


  const handleApprove = () => {
    setApproved(true);
    handleUpdate({
      ...offer,
      human_approved: true,
      human_modified_salary: salaryModified ? salary : null,
      human_modified_equity: equityModified ? equity : null,
      human_modified_start_date: dateModified ? startDate : null,
      offer_letter_text: letterText,
    });
  };

  const handleReject = () => {
    setApproved(false);
    handleUpdate({
      ...offer,
      human_approved: false,
    });
  };


  const formatSalary = (num) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(num);
  };


  return (
    <div className="card" style={{ marginBottom: "1.5rem" }}>
      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <h3 className="card-title">{candidate.name}</h3>
        <p className="text-small text-muted">Job Offer</p>
      </div>

      {}
      <div style={{ marginBottom: "1.5rem", padding: "1rem", backgroundColor: "#f9fafb", borderRadius: "4px" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "1rem" }}>Offer Details</h4>

        {}
        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", fontSize: "0.875rem", fontWeight: "500", marginBottom: "0.5rem" }}>
            Base Salary (Annual)
          </label>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              <input
                type="number"
                value={salary}
                onChange={(e) => setSalary(parseInt(e.target.value, 10))}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #e5e7eb",
                  borderRadius: "4px",
                  fontSize: "0.875rem",
                }}
              />
              <p className="text-small text-muted" style={{ marginTop: "0.25rem" }}>
                {formatSalary(salary)}
              </p>
            </div>
            {salaryModified && (
              <span style={{ fontSize: "0.75rem", backgroundColor: "#fef3c7", color: "#92400e", padding: "0.25rem 0.5rem", borderRadius: "4px" }}>
                Modified
              </span>
            )}
          </div>
        </div>

        {}
        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", fontSize: "0.875rem", fontWeight: "500", marginBottom: "0.5rem" }}>
            Equity (Optional)
          </label>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              <input
                type="text"
                value={equity}
                onChange={(e) => setEquity(e.target.value)}
                placeholder="e.g., 0.1% stock options"
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #e5e7eb",
                  borderRadius: "4px",
                  fontSize: "0.875rem",
                }}
              />
            </div>
            {equityModified && (
              <span style={{ fontSize: "0.75rem", backgroundColor: "#fef3c7", color: "#92400e", padding: "0.25rem 0.5rem", borderRadius: "4px" }}>
                Modified
              </span>
            )}
          </div>
        </div>

        {}
        <div>
          <label style={{ display: "block", fontSize: "0.875rem", fontWeight: "500", marginBottom: "0.5rem" }}>
            Suggested Start Date
          </label>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #e5e7eb",
                  borderRadius: "4px",
                  fontSize: "0.875rem",
                }}
              />
            </div>
            {dateModified && (
              <span style={{ fontSize: "0.75rem", backgroundColor: "#fef3c7", color: "#92400e", padding: "0.25rem 0.5rem", borderRadius: "4px" }}>
                Modified
              </span>
            )}
          </div>
        </div>
      </div>

      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "0.75rem" }}>
          Salary Justification
        </h4>

        {}
        {offer.market_data_used && (
          <div style={{ padding: "0.75rem", backgroundColor: "#f0f9ff", borderRadius: "4px", marginBottom: "1rem" }}>
            <p style={{ fontSize: "0.75rem", fontWeight: "500", color: "#1e40af", marginBottom: "0.25rem" }}>
              Market Data Used
            </p>
            <p className="text-small" style={{ color: "#1e40af", fontStyle: "italic" }}>
              "{offer.market_data_used}"
            </p>
          </div>
        )}

        {}
        <p className="text-small" style={{ color: "#374151", lineHeight: "1.6" }}>
          {offer.salary_reasoning || "No reasoning provided."}
        </p>
      </div>

      {/* Offer Letter — editable */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
          <h4 style={{ fontSize: "0.875rem", fontWeight: "600", margin: 0 }}>Offer Letter</h4>
          {letterModified && (
            <span style={{ fontSize: "0.75rem", backgroundColor: "#fef3c7", color: "#92400e", padding: "0.2rem 0.5rem", borderRadius: "4px" }}>
              Edited
            </span>
          )}
        </div>
        <textarea
          value={letterText}
          onChange={(e) => setLetterText(e.target.value)}
          rows={16}
          style={{
            width: "100%",
            padding: "0.85rem 1rem",
            border: `1px solid ${letterModified ? "#fcd34d" : "#e5e7eb"}`,
            borderRadius: "6px",
            fontSize: "0.875rem",
            lineHeight: "1.7",
            color: "#1e293b",
            fontFamily: "inherit",
            resize: "vertical",
            backgroundColor: letterModified ? "#fffbeb" : "#f9fafb",
          }}
        />
        <p className="text-small text-muted" style={{ marginTop: "0.4rem" }}>
          Edit directly above. This exact text will be emailed to {candidate.email} once approved.
        </p>
      </div>

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
            ? "✓ Approved for Sending"
            : approved === false
              ? "✗ Rejected"
              : "• Awaiting your approval"}
        </p>
        {approved === null && (
          <p className="text-small" style={{ color: "#6b7280" }}>
            Review the details above. You can modify salary, equity, or start date before sending.
          </p>
        )}
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
          ✓ Approve & Send
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

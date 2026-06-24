"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiPostForm } from "@/lib/api";
import { getRecruiterId, setRecruiterEmail } from "@/lib/user";

const RUBRICS_KEY = "hiregraph_rubrics_uploaded";

function Step({ number, title, done, children }) {
  return (
    <div style={{
      border: `1.5px solid ${done ? "var(--green-400)" : "var(--border)"}`,
      borderRadius: "var(--radius-lg)", padding: "1.5rem",
      marginBottom: "1rem", background: "var(--surface)",
      boxShadow: done ? "0 0 0 4px rgba(34,197,94,0.06)" : "var(--shadow-xs)",
      transition: "all 0.2s",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.85rem", marginBottom: done ? 0 : "1.25rem" }}>
        <div style={{
          width: 34, height: 34, borderRadius: "50%", flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "0.85rem", fontWeight: 700,
          background: done ? "var(--green-500)" : "var(--indigo-600)",
          color: "#fff",
        }}>
          {done ? (
            <svg width="14" height="14" viewBox="0 0 12 12" fill="none">
              <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          ) : number}
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "0.95rem" }}>{title}</h3>
          {done && <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--green-600)", fontWeight: 600 }}>Complete</p>}
        </div>
      </div>
      {!done && children}
    </div>
  );
}

export default function SetupPage() {
  const router = useRouter();
  const [gmailConnected, setGmailConnected] = useState(false);
  const [rubricsUploaded, setRubricsUploaded] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Gmail auth callback feedback
  const [authSuccess, setAuthSuccess] = useState(false);
  const [authError, setAuthError] = useState(null);

  // Recruiter profile
  const [recruiterName, setRecruiterName] = useState("");
  const [recruiterRole, setRecruiterRole] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  // Rubrics upload state
  const [rubricFile, setRubricFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("auth_success") === "true") {
      const email = params.get("user_email");
      const name  = params.get("user_name");
      if (email) {
        setRecruiterEmail(email);          // save email as the stable identity
        if (name && !recruiterName) setRecruiterName(decodeURIComponent(name));
      }
      setAuthSuccess(true);
      window.history.replaceState({}, "", "/setup");
    }
    if (params.get("auth_error")) {
      setAuthError(decodeURIComponent(params.get("auth_error")));
      window.history.replaceState({}, "", "/setup");
    }

    // checkGmail first - it confirms whether we have a real email identity.
    // Only call checkRubrics after, so getRecruiterId() returns the email not a UUID.
    checkGmail().then(() => checkRubrics());
  }, []);

  const checkGmail = async () => {
    try {
      const data = await apiGet("/auth/status");
      setGmailConnected(data.authenticated);
      if (data.name) { setRecruiterName(data.name); setProfileSaved(true); }
      if (data.role) setRecruiterRole(data.role);
    } catch {
      setGmailConnected(false);
    } finally {
      setCheckingAuth(false);
    }
    // always returns so callers can chain .then()
  };

  const handleSaveProfile = async () => {
    if (!recruiterName.trim() || !recruiterRole.trim()) return;
    setSavingProfile(true);
    try {
      const params = new URLSearchParams({ name: recruiterName.trim(), role: recruiterRole.trim() });
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/profile?${params}`,
        { method: "PATCH", headers: { "X-Recruiter-ID": getRecruiterId() } }
      );
      setProfileSaved(true);
    } catch {
      // ignore silently
    } finally {
      setSavingProfile(false);
    }
  };

  const checkRubrics = async () => {
    try {
      const data = await apiGet("/rag/rubrics-status");
      if (data.loaded) {
        setRubricsUploaded(true);
        localStorage.setItem(RUBRICS_KEY, "true");
      }
    } catch {
      // silently ignore - rubric check is best-effort
    }
  };

  const handleConnectGmail = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    window.location.href = `${apiUrl}/auth/google`;
  };

  const handleDisconnectGmail = async () => {
    try {
      const { clearRecruiterEmail } = await import("@/lib/user");
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/logout`,
        { method: "DELETE", headers: { "X-Recruiter-ID": getRecruiterId() } }
      );
      clearRecruiterEmail();
      setGmailConnected(false);
      setProfileSaved(false);
    } catch {
      // ignore
    }
  };

  const handleRubricsUpload = async () => {
    if (!rubricFile) return;
    setUploading(true);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("namespace", "company_rubrics");
      form.append("document_file", rubricFile);
      form.append("document_name", rubricFile.name);
      await apiPostForm("/rag/index", form);
      localStorage.setItem(RUBRICS_KEY, "true");
      setRubricsUploaded(true);
      setRubricFile(null);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleProceed = () => router.push("/");

  // Gmail + profile are required; rubric is optional
  const canProceed = gmailConnected && profileSaved;

  return (
    <div style={{ maxWidth: 520, margin: "2.5rem auto", padding: "0 1rem" }}>
      <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
        <div style={{ fontSize: "2.75rem", marginBottom: "0.75rem" }}>🎯</div>
        <h1 style={{ fontSize: "1.8rem", marginBottom: "0.4rem" }}>Welcome to HireGraph</h1>
        <p className="text-muted" style={{ margin: 0 }}>Two quick steps and you're ready to hire smarter.</p>
      </div>

      {authSuccess && (
        <div className="alert alert-success" style={{ marginBottom: "1.25rem" }}>
          Gmail connected successfully ✓
        </div>
      )}
      {authError && (
        <div className="alert alert-error" style={{ marginBottom: "1.25rem" }}>
          Google sign-in failed: {authError}
        </div>
      )}

      {/* Step 1 - Gmail + Profile */}
      <Step number="1" title="Connect your Google account" done={gmailConnected && profileSaved}>
        {!gmailConnected ? (
          <>
            <p className="text-small text-muted" style={{ marginBottom: "1rem" }}>
              HireGraph sends offer letters and schedules interviews via your Gmail and Google Calendar.
            </p>
            <button onClick={handleConnectGmail} className="button button-primary" style={{ width: "100%" }}>
              Sign in with Google
            </button>
          </>
        ) : (
          <>
            <p className="text-small" style={{ color: "#16a34a", marginBottom: "1rem", fontWeight: 500 }}>
              Google account connected.
            </p>
            <p className="text-small text-muted" style={{ marginBottom: "1rem" }}>
              Enter your name and role so offer letters and emails are signed correctly.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.3rem" }}>
                  Your Name <span style={{ color: "#dc2626" }}>*</span>
                </label>
                <input
                  type="text"
                  value={recruiterName}
                  onChange={(e) => { setRecruiterName(e.target.value); setProfileSaved(false); }}
                  placeholder="e.g. Sarah Chen"
                  style={{ width: "100%", padding: "0.55rem 0.75rem", border: "1px solid #e2e8f0", borderRadius: "6px", fontSize: "0.875rem" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.3rem" }}>
                  Your Role <span style={{ color: "#dc2626" }}>*</span>
                </label>
                <input
                  type="text"
                  value={recruiterRole}
                  onChange={(e) => { setRecruiterRole(e.target.value); setProfileSaved(false); }}
                  placeholder="e.g. Head of Engineering"
                  style={{ width: "100%", padding: "0.55rem 0.75rem", border: "1px solid #e2e8f0", borderRadius: "6px", fontSize: "0.875rem" }}
                />
              </div>
            </div>
            <button
              onClick={handleSaveProfile}
              disabled={savingProfile || !recruiterName.trim() || !recruiterRole.trim()}
              className="button button-primary"
              style={{ width: "100%" }}
            >
              {savingProfile ? "Saving..." : profileSaved ? "Saved" : "Save Profile"}
            </button>
          </>
        )}
      </Step>

      {/* Step 2 - Company rubric (optional) */}
      <Step number="2" title="Upload company hiring rubric (optional)" done={rubricsUploaded}>
        <p className="text-small text-muted" style={{ marginBottom: "1rem" }}>
          Upload your hiring standards, seniority levels, interview process, and salary/compensation bands.
          The AI uses this to screen candidates and draft offer letters.
          {" "}<strong>Only needs to be uploaded once.</strong> It applies to all pipelines.
        </p>
        {!rubricsUploaded && (
          <>
            <label style={{
              display: "flex", flexDirection: "column", alignItems: "center",
              padding: "1.5rem", border: "2px dashed var(--border)", borderRadius: "var(--radius-lg)",
              cursor: "pointer", background: "var(--gray-50)", marginBottom: "0.75rem",
              transition: "all 0.15s",
            }}>
              <span style={{ fontSize: "1.5rem", marginBottom: "0.3rem" }}>📄</span>
              <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--gray-700)" }}>
                {rubricFile ? rubricFile.name : "Click to choose file"}
              </span>
              <span style={{ fontSize: "0.75rem", color: "var(--gray-400)", marginTop: "0.2rem" }}>PDF, DOCX, TXT or MD</span>
              <input type="file" accept=".pdf,.txt,.docx,.md" style={{ display: "none" }}
                onChange={e => setRubricFile(e.target.files[0] || null)} />
            </label>
            {uploadError && (
              <p style={{ color: "var(--red-600)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{uploadError}</p>
            )}
            {!gmailConnected && (
              <p style={{ fontSize: "0.8rem", color: "#b45309", marginBottom: "0.5rem" }}>
                Sign in with Google first so the rubric is saved to your company's account.
              </p>
            )}
            <button onClick={handleRubricsUpload} disabled={!rubricFile || uploading || !gmailConnected}
              className="button button-primary" style={{ width: "100%" }}>
              {uploading ? "Uploading..." : "Upload Rubric"}
            </button>
          </>
        )}
      </Step>

      {/* Proceed */}
      {canProceed && (
        <div style={{ textAlign: "center", marginTop: "1.75rem" }}>
          <button onClick={handleProceed} className="button button-primary"
            style={{ padding: "0.85rem 3rem", fontSize: "0.95rem" }}>
            Start Hiring →
          </button>
          {!rubricsUploaded && (
            <p className="text-small text-muted" style={{ marginTop: "0.5rem" }}>
              You can upload the rubric later. The AI will still work without it.
            </p>
          )}
        </div>
      )}

      {/* Re-upload rubric option if already done */}
      {rubricsUploaded && (
        <div style={{ marginTop: "1rem", textAlign: "center" }}>
          <button
            onClick={() => { localStorage.removeItem(RUBRICS_KEY); setRubricsUploaded(false); }}
            style={{ background: "none", border: "none", color: "#64748b", fontSize: "0.8rem", cursor: "pointer", textDecoration: "underline" }}
          >
            Replace rubric file
          </button>
          {gmailConnected && (
            <span style={{ margin: "0 0.5rem", color: "#cbd5e1" }}>·</span>
          )}
          {gmailConnected && (
            <button
              onClick={handleDisconnectGmail}
              style={{ background: "none", border: "none", color: "#64748b", fontSize: "0.8rem", cursor: "pointer", textDecoration: "underline" }}
            >
              Disconnect Gmail
            </button>
          )}
        </div>
      )}
    </div>
  );
}

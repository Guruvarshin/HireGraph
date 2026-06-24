"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";
import StageProgressBar from "@/components/StageProgressBar";
import ShortlistCard from "@/components/ShortlistCard";
import InterviewPlanCard from "@/components/InterviewPlanCard";
import FeedbackForm from "@/components/FeedbackForm";
import EvaluationCard from "@/components/EvaluationCard";
import OfferCard from "@/components/OfferCard";

const PROCESSING_STAGES = ["jd_parsing", "resume_screening", "interview_planning", "interview_evaluation", "offer_drafting", "sending_offers"];

export default function PipelineDetailPage() {
  const params = useParams();
  const router = useRouter();
  const threadId = params.id;

  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Local editable copies for stages that need batch submit
  const [localShortlist, setLocalShortlist] = useState(null);
  const [localPlans, setLocalPlans] = useState(null);
  const [localFeedback, setLocalFeedback] = useState({});
  const [localEvaluations, setLocalEvaluations] = useState(null);
  const [localOffers, setLocalOffers] = useState(null);

  const fetchState = useCallback(async () => {
    try {
      setError(null);
      const data = await apiGet(`/pipeline/${threadId}`);
      setState(data);
      // Initialize local state copies when stage changes
      setLocalShortlist(null);
      setLocalPlans(null);
      setLocalFeedback({});
      setLocalEvaluations(null);
      setLocalOffers(null);
    } catch (err) {
      setError(err.message);
    }
  }, [threadId]);

  useEffect(() => {
    if (!threadId) return;
    setLoading(true);
    fetchState().finally(() => setLoading(false));
  }, [threadId, fetchState]);

  // Auto-poll while pipeline is in an AI-processing stage
  useEffect(() => {
    if (!state) return;
    const stage = state.current_stage;
    if (!PROCESSING_STAGES.includes(stage)) return;

    const timer = setInterval(() => {
      fetchState();
    }, 4000);
    return () => clearInterval(timer);
  }, [state?.current_stage, fetchState]);

  // --- Shortlist ---
  // Show ALL screened candidates (not just AI-recommended ones).
  // Sort: AI-recommended first, then by score descending.
  const allScreened = (state?.candidates ?? [])
    .filter((c) => c.score)
    .sort((a, b) => {
      const aRec = a.score?.recommended_for_shortlist ? 1 : 0;
      const bRec = b.score?.recommended_for_shortlist ? 1 : 0;
      if (bRec !== aRec) return bRec - aRec;
      return (b.score?.overall_score ?? 0) - (a.score?.overall_score ?? 0);
    });

  // localShortlist shadows allScreened for local edits (approvals, email changes)
  const activeShortlist = localShortlist ?? allScreened;

  // Initialise local shortlist from allScreened on first render of this stage
  useEffect(() => {
    if (state?.current_stage === "shortlist_review" && !localShortlist && allScreened.length > 0) {
      setLocalShortlist(allScreened);
    }
  }, [state?.current_stage, state?.candidates]);

  const handleShortlistToggle = (candidateId, approved) => {
    const updated = activeShortlist.map((c) =>
      c.candidate_id === candidateId
        ? { ...c, score: { ...(c.score || {}), human_approved: approved } }
        : c
    );
    setLocalShortlist(updated);
  };

  const handleShortlistEmailChange = (candidateId, email) => {
    // Update the shortlist display
    setLocalShortlist((prev) =>
      (prev ?? allScreened).map((c) => c.candidate_id === candidateId ? { ...c, email } : c)
    );
    // Mirror the change into localCandidates so every downstream stage sees the correct email
    setLocalCandidates((prev) =>
      (prev ?? state?.candidates ?? []).map((c) => c.candidate_id === candidateId ? { ...c, email } : c)
    );
  };

  const handleSubmitShortlist = async () => {
    const approved = activeShortlist.filter((c) => c.score?.human_approved === true);
    if (approved.length === 0) {
      setError("Approve at least one candidate to proceed.");
      return;
    }
    const missingEmail = approved.filter(
      (c) => !c.email || c.email === "placeholder@example.com" || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c.email)
    );
    if (missingEmail.length > 0) {
      setError(`Enter a valid email for: ${missingEmail.map((c) => c.name).join(", ")}`);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiPost(`/pipeline/${threadId}/approve-shortlist`, {
        candidates: activeShortlist,
        ...(localCandidates ? { all_candidates: localCandidates } : {}),
      });
      await fetchState();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // --- Interview Plans ---
  const activePlans = localPlans ?? state?.interview_plans ?? [];
  const [localCandidates, setLocalCandidates] = useState(null);

  const handlePlanCandidateEmailChange = (candidateId, email) => {
    const base = localCandidates ?? state?.candidates ?? [];
    setLocalCandidates(base.map((c) => c.candidate_id === candidateId ? { ...c, email } : c));
  };

  const handlePlanUpdate = (updatedPlan) => {
    const updated = activePlans.map((p) =>
      p.candidate_id === updatedPlan.candidate_id ? updatedPlan : p
    );
    setLocalPlans(updated);
  };

  const handlePlanApprovalToggle = (planCandidateId, approved) => {
    const updated = activePlans.map((p) =>
      p.candidate_id === planCandidateId ? { ...p, human_approved: approved } : p
    );
    setLocalPlans(updated);
  };

  const handleSubmitPlans = async () => {
    const anyApproved = activePlans.some((p) => p.human_approved === true);
    if (!anyApproved) {
      setError("Approve at least one interview plan to proceed.");
      return;
    }
    // Check all approved plans have dates set on every round
    const allCandidates = localCandidates ?? state?.candidates ?? [];
    const missingDates = activePlans
      .filter((p) => p.human_approved === true)
      .flatMap((p) =>
        (p.rounds || [])
          .filter((r) => !r.scheduled_at)
          .map((r) => `${allCandidates.find((c) => c.candidate_id === p.candidate_id)?.name || p.candidate_id}, Round ${r.round_number}`)
      );
    if (missingDates.length > 0) {
      setError(`Set a date & time for: ${missingDates.join(", ")}`);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // Only send approved plans - rejected ones are dropped from the pipeline entirely
      const approvedPlansOnly = activePlans.filter((p) => p.human_approved === true);
      await apiPost(`/pipeline/${threadId}/approve-plans`, {
        interview_plans: approvedPlansOnly,
        ...(localCandidates ? { candidates: localCandidates } : {}),
      });
      // Auto-send interview invites immediately after plans are confirmed
      try {
        const inviteResult = await apiPost(`/pipeline/${threadId}/send-invites`, {});
        if (inviteResult.failed?.length > 0) {
          setError(`Plans confirmed. Some invites failed: ${inviteResult.failed.map(f => f.reason).join(", ")}`);
        }
      } catch (inviteErr) {
        // Non-fatal - plans are saved, just warn about invites
        setError(`Plans confirmed but invite sending failed: ${inviteErr.message}`);
      }
      await fetchState();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // --- Feedback ---
  const handleFeedbackChange = (candidateId, feedbackData) => {
    setLocalFeedback((prev) => ({ ...prev, [candidateId]: feedbackData }));
  };

  const handleSubmitAllFeedback = async () => {
    const feedbackList = candidatesWithPlans.map((c) => localFeedback[c.candidate_id]).filter(Boolean);

    if (feedbackList.length === 0) {
      setError("Fill in feedback for at least one candidate.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await apiPost(`/pipeline/${threadId}/feedback`, { interview_feedback: feedbackList });
      await apiPost(`/pipeline/${threadId}/resume-evaluator`, {});
      await fetchState();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // --- Evaluations ---
  const activeEvaluations = localEvaluations ?? state?.evaluations ?? [];

  const handleEvaluationToggle = (candidateId, approved) => {
    const updated = activeEvaluations.map((e) =>
      e.candidate_id === candidateId ? { ...e, human_approved: approved } : e
    );
    setLocalEvaluations(updated);
  };

  const handleSubmitEvaluations = async () => {
    const anyApproved = activeEvaluations.some((e) => e.human_approved === true);
    if (!anyApproved) {
      setError("Select at least one candidate for an offer to proceed.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiPost(`/pipeline/${threadId}/approve-offer-candidates`, { evaluations: activeEvaluations });
      await fetchState();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // --- Offers ---
  const activeOffers = localOffers ?? state?.offer_drafts ?? [];

  const handleOfferUpdate = (updatedOffer) => {
    const updated = activeOffers.map((o) =>
      o.candidate_id === updatedOffer.candidate_id ? updatedOffer : o
    );
    setLocalOffers(updated);
  };

  const handleSubmitOffers = async () => {
    const anyApproved = activeOffers.some((o) => o.human_approved === true);
    if (!anyApproved) {
      setError("Approve at least one offer to proceed.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiPost(`/pipeline/${threadId}/approve-offers`, { offer_drafts: activeOffers });
      await fetchState();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // --- Send Interview Invites ---
  const handleSendInvites = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await apiPost(`/pipeline/${threadId}/send-invites`, {});
      alert(result.message || "Invites sent.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "5rem" }}>
        <div className="loading" style={{ width: 28, height: 28, margin: "0 auto 1rem" }} />
        <p className="text-muted">Loading pipeline...</p>
      </div>
    );
  }

  if (!state) {
    return (
      <div className="card" style={{ borderColor: "var(--red-500)", background: "var(--red-50)", textAlign: "center", padding: "3rem" }}>
        <h2 style={{ color: "var(--red-600)", marginBottom: "0.5rem" }}>Pipeline Not Found</h2>
        <p style={{ color: "var(--red-600)", marginBottom: "1.5rem" }}>No pipeline with ID {threadId}.</p>
        <button className="button button-primary" onClick={() => router.push("/")}>Back to Home</button>
      </div>
    );
  }

  const stage = state.current_stage;
  const jd = state.job_description || {};
  const candidates = state.candidates || [];
  const shortlist = state.shortlist || [];
  const plans = state.interview_plans || [];
  const evaluations = state.evaluations || [];
  const offers = state.offer_drafts || [];

  // Candidates with a stored interview plan (rejected plans are never stored)
  const candidatesWithPlans = candidates.filter((c) =>
    plans.some((p) => p.candidate_id === c.candidate_id)
  );

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
        <div>
          <button onClick={() => router.push("/")}
            style={{ fontSize: "0.8rem", color: "var(--gray-400)", cursor: "pointer", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
            ← All Pipelines
          </button>
          <h1 style={{ margin: 0, fontSize: "1.6rem" }}>{jd.title || "Untitled Pipeline"}</h1>
        </div>
        {state.error_message && (
          <div className="alert alert-warning" style={{ maxWidth: 340, margin: 0, fontSize: "0.8rem" }}>
            {state.error_message}
          </div>
        )}
      </div>

      {/* Stage Progress */}
      <div style={{ marginBottom: "2rem" }}>
        <StageProgressBar currentStage={stage} />
      </div>

      {/* Action error */}
      {error && (
        <div className="card" style={{ marginBottom: "1.5rem", borderColor: "#dc2626", backgroundColor: "#fef2f2" }}>
          <p style={{ color: "#991b1b", margin: 0 }}>{error}</p>
        </div>
      )}

      {/* ===== Stage-specific content ===== */}

      {PROCESSING_STAGES.includes(stage) ? (
        <div className="card" style={{ textAlign: "center", padding: "4rem 2rem" }}>
          <div style={{
            width: 56, height: 56, borderRadius: "50%",
            background: "var(--indigo-50)", display: "flex", alignItems: "center",
            justifyContent: "center", margin: "0 auto 1.5rem",
          }}>
            <div className="loading" style={{ width: 24, height: 24 }} />
          </div>
          <h2 style={{ marginBottom: "0.5rem" }}>AI is working</h2>
          <p className="text-muted" style={{ maxWidth: 360, margin: "0 auto 0.75rem" }}>
            {stage === "jd_parsing"          && "Parsing and structuring the job description."}
            {stage === "resume_screening"     && "Reading and scoring all candidate resumes."}
            {stage === "interview_planning"   && "Generating tailored interview plans."}
            {stage === "interview_evaluation" && "Synthesising interviewer feedback."}
            {stage === "offer_drafting"       && "Drafting personalised offer letters."}
            {stage === "sending_offers"       && "Sending approved offers via Gmail."}
          </p>
          <span style={{ fontSize: "0.78rem", color: "var(--gray-400)" }}>Auto-refreshing every 4 seconds</span>
        </div>

      ) : stage === "shortlist_review" ? (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Review Shortlist</h2>
              <p className="text-muted" style={{ marginTop: "0.25rem" }}>
                Approve or reject each candidate, then confirm your decisions to proceed.
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              <p className="text-small text-muted" style={{ marginBottom: "0.5rem" }}>
                {activeShortlist.filter((c) => c.score?.human_approved === true).length} approved ·{" "}
                {activeShortlist.filter((c) => c.score?.human_approved === false).length} rejected
              </p>
              <button
                onClick={handleSubmitShortlist}
                disabled={submitting}
                className="button button-primary"
                style={{ padding: "0.75rem 1.5rem" }}
              >
                {submitting ? "Submitting..." : "Confirm & Proceed →"}
              </button>
            </div>
          </div>

          {activeShortlist.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
              <p className="text-muted">No screened candidates found. Check the pipeline error above.</p>
            </div>
          ) : (
            activeShortlist.map((candidate) => (
              <ShortlistCard
                key={candidate.candidate_id}
                candidate={candidate}
                score={candidate.score}
                onApprove={(cand, approved) => handleShortlistToggle(cand.candidate_id, approved)}
                onEmailChange={handleShortlistEmailChange}
              />
            ))
          )}

          <div style={{ marginTop: "1.5rem", textAlign: "right" }}>
            <button
              onClick={handleSubmitShortlist}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Submitting..." : "Confirm & Proceed →"}
            </button>
          </div>
        </div>

      ) : stage === "finalist_review" ? (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Approve Interview Plans</h2>
              <p className="text-muted" style={{ marginTop: "0.25rem" }}>
                Review each plan, fill in interviewer emails and schedule times, then approve.
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              <button
                onClick={handleSubmitPlans}
                disabled={submitting}
                className="button button-primary"
                style={{ padding: "0.75rem 1.5rem" }}
              >
                {submitting ? "Confirming & Sending Invites..." : "Confirm Plans & Send Invites →"}
              </button>
            </div>
          </div>

          {activePlans.length === 0 ? (
            <div className="card"><p className="text-muted">No interview plans generated yet.</p></div>
          ) : (
            activePlans.map((plan) => {
              const candidate = (localCandidates ?? candidates).find((c) => c.candidate_id === plan.candidate_id);
              if (!candidate) return null;
              return (
                <InterviewPlanCard
                  key={plan.candidate_id}
                  candidate={candidate}
                  plan={plan}
                  onUpdatePlan={handlePlanUpdate}
                  onApprove={(p, approved) => handlePlanApprovalToggle(p.candidate_id, approved)}
                  onCandidateEmailChange={handlePlanCandidateEmailChange}
                />
              );
            })
          )}

          <div style={{ marginTop: "1.5rem", textAlign: "right" }}>
            <p className="text-small text-muted" style={{ marginBottom: "0.5rem" }}>
              Confirming will save all plans and immediately send Gmail + Calendar invites to candidates and interviewers.
            </p>
            <button
              onClick={handleSubmitPlans}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Confirming & Sending Invites..." : "Confirm Plans & Send Invites →"}
            </button>
          </div>
        </div>

      ) : stage === "awaiting_feedback" ? (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Submit Interview Feedback</h2>
              <p className="text-muted" style={{ marginTop: "0.25rem" }}>
                Enter feedback for each completed interview round, then submit all at once.
              </p>
            </div>
            <button
              onClick={handleSubmitAllFeedback}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Submitting..." : "Submit All Feedback →"}
            </button>
          </div>

          {candidatesWithPlans.length === 0 ? (
            <div className="card"><p className="text-muted">No candidates with interview plans found.</p></div>
          ) : (
            candidatesWithPlans.map((candidate) => {
              const plan = plans.find((p) => p.candidate_id === candidate.candidate_id);
              return (
                <FeedbackForm
                  key={candidate.candidate_id}
                  candidate={candidate}
                  plan={plan}
                  feedback={localFeedback[candidate.candidate_id]}
                  onChange={(fb) => handleFeedbackChange(candidate.candidate_id, fb)}
                />
              );
            })
          )}

          <div style={{ marginTop: "1.5rem", textAlign: "right" }}>
            <button
              onClick={handleSubmitAllFeedback}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Submitting..." : "Submit All Feedback →"}
            </button>
          </div>
        </div>

      ) : stage === "offer_candidates_review" ? (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Select Candidates for Offers</h2>
              <p className="text-muted" style={{ marginTop: "0.25rem" }}>
                Review AI evaluations and select who should receive an offer.
              </p>
            </div>
            <button
              onClick={handleSubmitEvaluations}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Submitting..." : "Confirm Selection →"}
            </button>
          </div>

          {activeEvaluations.length === 0 ? (
            <div className="card"><p className="text-muted">No evaluations available.</p></div>
          ) : (
            activeEvaluations.map((evaluation) => {
              const candidate = candidates.find((c) => c.candidate_id === evaluation.candidate_id);
              if (!candidate) return null;
              return (
                <EvaluationCard
                  key={evaluation.candidate_id}
                  candidate={candidate}
                  evaluation={evaluation}
                  onApprove={(cand, approved) => handleEvaluationToggle(cand.candidate_id, approved)}
                />
              );
            })
          )}

          <div style={{ marginTop: "1.5rem", textAlign: "right" }}>
            <button
              onClick={handleSubmitEvaluations}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Submitting..." : "Confirm Selection →"}
            </button>
          </div>
        </div>

      ) : stage === "offer_review" ? (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Review & Approve Offers</h2>
              <p className="text-muted" style={{ marginTop: "0.25rem" }}>
                Review each offer letter. Modify salary, equity, or start date if needed, then approve to send.
              </p>
            </div>
            <button
              onClick={handleSubmitOffers}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Sending..." : "Send Approved Offers →"}
            </button>
          </div>

          {activeOffers.length === 0 ? (
            <div className="card"><p className="text-muted">No offer drafts available.</p></div>
          ) : (
            activeOffers.map((offer) => {
              const candidate = candidates.find((c) => c.candidate_id === offer.candidate_id);
              if (!candidate) return null;
              return (
                <OfferCard
                  key={offer.candidate_id}
                  candidate={candidate}
                  offer={offer}
                  onUpdate={handleOfferUpdate}
                />
              );
            })
          )}

          <div style={{ marginTop: "1.5rem", textAlign: "right" }}>
            <button
              onClick={handleSubmitOffers}
              disabled={submitting}
              className="button button-primary"
              style={{ padding: "0.75rem 1.5rem" }}
            >
              {submitting ? "Sending..." : "Send Approved Offers →"}
            </button>
          </div>
        </div>

      ) : stage === "completed" ? (
        <PipelineSummary
          candidates={candidates}
          shortlist={shortlist}
          plans={plans}
          evaluations={evaluations}
          offers={offers}
          onBack={() => router.push("/")}
        />

      ) : (
        <div className="card">
          <p className="text-muted">Unknown stage: {stage}</p>
        </div>
      )}

      {/* Job Description Details */}
      {jd.title && (
        <div className="card" style={{ marginTop: "3rem" }}>
          <h3 style={{ marginBottom: "1rem" }}>Job Description</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <p className="text-small text-muted">Title</p>
              <p className="text-small" style={{ fontWeight: 500 }}>{jd.title}</p>
            </div>
            <div>
              <p className="text-small text-muted">Seniority</p>
              <p className="text-small" style={{ fontWeight: 500, textTransform: "capitalize" }}>{jd.seniority}</p>
            </div>
            <div>
              <p className="text-small text-muted">Location</p>
              <p className="text-small" style={{ fontWeight: 500 }}>{jd.location}</p>
            </div>
            <div>
              <p className="text-small text-muted">Remote</p>
              <p className="text-small" style={{ fontWeight: 500 }}>{jd.remote_policy}</p>
            </div>
          </div>
          {jd.required_skills?.length > 0 && (
            <div>
              <p className="text-small text-muted" style={{ marginBottom: "0.5rem" }}>Required Skills</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                {jd.required_skills.map((s) => (
                  <span key={s} style={{ padding: "0.25rem 0.75rem", backgroundColor: "#dbeafe", color: "#1e40af", borderRadius: "999px", fontSize: "0.8rem" }}>
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  );
}

// ─── Pipeline completion summary ─────────────────────────────────────────────

function PipelineSummary({ candidates, shortlist, plans, evaluations, offers, onBack }) {
  const shortlistMap   = Object.fromEntries(shortlist.map(c => [c.candidate_id, c]));
  const planMap        = Object.fromEntries(plans.map(p => [p.candidate_id, p]));
  const evaluationMap  = Object.fromEntries(evaluations.map(e => [e.candidate_id, e]));
  const offerMap       = Object.fromEntries(offers.map(o => [o.candidate_id, o]));

  const offersSent = offers.filter(o => o.email_status === "sent");

  // Classify every candidate into a rejection/progress stage
  const classified = candidates.map(c => {
    const id        = c.candidate_id;
    const sc        = shortlistMap[id];
    const offer     = offerMap[id];
    const eval_     = evaluationMap[id];
    const plan      = planMap[id];

    if (offer?.email_status === "sent")           return { ...c, status: "offer_sent",          label: "Offer Sent",                color: "#16a34a", bg: "#dcfce7" };
    if (offer?.human_approved === true)            return { ...c, status: "offer_approved",       label: "Offer Approved",             color: "#16a34a", bg: "#dcfce7" };
    if (offer)                                     return { ...c, status: "offer_rejected",       label: "Offer Rejected",             color: "#dc2626", bg: "#fee2e2" };
    if (eval_?.human_approved === false)           return { ...c, status: "eval_rejected",        label: "Not Selected for Offer",     color: "#ea580c", bg: "#fff7ed" };
    if (eval_)                                     return { ...c, status: "eval_done",            label: "Evaluated",                  color: "#2563eb", bg: "#eff6ff" };
    if (plan)                                      return { ...c, status: "plan_approved",        label: "Interviewed",                color: "#7c3aed", bg: "#f5f3ff" };
    if (sc?.score?.human_approved === false)       return { ...c, status: "shortlist_rejected",   label: "Rejected at Shortlist",      color: "#dc2626", bg: "#fee2e2" };
    if (sc?.score?.human_approved === true)        return { ...c, status: "plan_rejected",        label: "Rejected at Interview Plan", color: "#dc2626", bg: "#fee2e2" };
    if (sc)                                        return { ...c, status: "not_approved",         label: "Not Shortlisted",            color: "#64748b", bg: "#f8fafc" };
    return                                                { ...c, status: "screened",             label: "Screened Only",              color: "#64748b", bg: "#f8fafc" };
  });

  const Badge = ({ label, color, bg }) => (
    <span style={{ fontSize: "0.75rem", fontWeight: 600, padding: "0.2rem 0.6rem", borderRadius: "999px", backgroundColor: bg, color }}>{label}</span>
  );

  const StatBox = ({ value, label, color = "#1e293b" }) => (
    <div style={{ textAlign: "center", padding: "1.25rem", backgroundColor: "#f8fafc", borderRadius: "8px", flex: 1 }}>
      <div style={{ fontSize: "2rem", fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: "0.8rem", color: "#64748b", marginTop: "0.2rem" }}>{label}</div>
    </div>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ backgroundColor: "#dcfce7", border: "1px solid #86efac", borderRadius: "12px", padding: "1.5rem 2rem", marginBottom: "2rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ color: "#166534", margin: "0 0 0.25rem" }}>Pipeline Complete</h2>
          <p style={{ color: "#16a34a", margin: 0, fontSize: "0.9rem" }}>{candidates.length} candidates processed</p>
        </div>
        <button className="button button-primary" onClick={onBack}>Back to Pipelines</button>
      </div>

      {/* Stats row */}
      <div style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
        <StatBox value={candidates.length}    label="Total Candidates" />
        <StatBox value={shortlist.filter(c => c.score?.human_approved === true).length} label="Shortlisted" color="#2563eb" />
        <StatBox value={plans.length}         label="Interviewed"      color="#7c3aed" />
        <StatBox value={evaluations.length}   label="Evaluated"        color="#ea580c" />
        <StatBox value={offersSent.length}    label="Offers Sent"      color="#16a34a" />
      </div>

      {/* Offers sent - detail */}
      {offersSent.length > 0 && (
        <div className="card" style={{ marginBottom: "1.5rem", borderColor: "#86efac", backgroundColor: "#f0fdf4" }}>
          <h3 style={{ color: "#166534", marginBottom: "1rem" }}>Offers Sent ({offersSent.length})</h3>
          {offersSent.map(o => {
            const c = candidates.find(x => x.candidate_id === o.candidate_id);
            return (
              <div key={o.candidate_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "0.75rem 0", borderBottom: "1px solid #dcfce7" }}>
                <div>
                  <p style={{ fontWeight: 600, margin: "0 0 0.15rem", color: "#166534" }}>{c?.name || o.candidate_id}</p>
                  <p style={{ fontSize: "0.8rem", color: "#16a34a", margin: 0 }}>{c?.email}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <p style={{ fontWeight: 600, margin: "0 0 0.1rem", color: "#166534" }}>
                    ${((o.human_modified_salary || o.base_salary) || 0).toLocaleString()}
                  </p>
                  {o.equity && <p style={{ fontSize: "0.8rem", color: "#16a34a", margin: 0 }}>{o.equity}</p>}
                  {o.start_date && <p style={{ fontSize: "0.8rem", color: "#16a34a", margin: 0 }}>Start: {o.human_modified_start_date || o.start_date}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* All candidates journey */}
      <h3 style={{ marginBottom: "1rem" }}>All Candidates</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {classified.map(c => {
          const sc    = shortlistMap[c.candidate_id];
          const eval_ = evaluationMap[c.candidate_id];
          const offer = offerMap[c.candidate_id];

          return (
            <div key={c.candidate_id} style={{ border: `1px solid ${c.bg === "#f8fafc" ? "#e2e8f0" : c.bg}`, borderRadius: "8px", padding: "0.9rem 1.1rem", backgroundColor: "#fff", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.2rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{c.name}</span>
                  <Badge label={c.label} color={c.color} bg={c.bg} />
                </div>
                <p style={{ fontSize: "0.8rem", color: "#64748b", margin: 0 }}>{c.email}</p>
              </div>
              <div style={{ display: "flex", gap: "1.5rem", flexShrink: 0, fontSize: "0.8rem", color: "#64748b" }}>
                {sc?.score?.overall_score != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontWeight: 700, fontSize: "1.1rem", color: "#1e293b" }}>{sc.score.overall_score}</div>
                    <div>Screen</div>
                  </div>
                )}
                {eval_?.composite_score != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontWeight: 700, fontSize: "1.1rem", color: "#1e293b" }}>{eval_.composite_score}</div>
                    <div>Interview</div>
                  </div>
                )}
                {offer?.base_salary && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontWeight: 700, fontSize: "1rem", color: "#16a34a" }}>${((offer.human_modified_salary || offer.base_salary)).toLocaleString()}</div>
                    <div>Offer</div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

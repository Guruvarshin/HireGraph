from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from models.pipeline import (
    Candidate,
    JobDescription,
    PipelineState,
    PipelineStatus,
    PipelineStage,
)
from memory.database import (
    create_pipeline_run,
    get_pipeline_run,
    list_pipeline_runs,
    update_pipeline_run,
    mark_pipeline_completed,
    delete_pipeline_run,
)
from graph.pipeline import (
    start_pipeline,
    resume_pipeline,
    get_pipeline_state,
)


router = APIRouter()


class ApproveShortlistRequest(BaseModel):
    """Recruiter marks candidates in the shortlist as approved/rejected."""
    candidates: list[dict] = Field(
        ...,
        description="List of candidates with their shortlist score and human_approved field.",
    )
    all_candidates: list[dict] | None = Field(
        None,
        description="Full candidates list with any email corrections applied by the recruiter.",
    )


class ApprovePlansRequest(BaseModel):
    """Recruiter approves generated interview plans, optionally filling in interviewer emails."""
    interview_plans: list[dict] = Field(
        ...,
        description=(
            "List of InterviewPlan dicts. Each round now has interviewer_emails filled in "
            "by the recruiter (real email addresses for each interviewer)."
        ),
    )
    candidates: list[dict] | None = Field(
        None,
        description="Optional updated candidate list (e.g. email filled in at this step).",
    )


class SubmitFeedbackRequest(BaseModel):
    """Recruiter submits interview feedback after rounds are completed."""
    interview_feedback: list[dict] = Field(
        ...,
        description="List of InterviewFeedback dicts with round_feedbacks from each interviewer.",
    )


class ApproveOfferCandidatesRequest(BaseModel):
    """Recruiter selects which evaluated candidates should receive offers."""
    evaluations: list[dict] = Field(
        ...,
        description="List of InterviewEvaluation dicts with human_approved set on selected ones.",
    )


class ApproveOffersRequest(BaseModel):
    """Recruiter approves/modifies final offer drafts before sending."""
    offer_drafts: list[dict] = Field(
        ...,
        description=(
            "List of OfferDraft dicts. Recruiter can set human_approved=True/False "
            "and optionally override salary/equity/start_date."
        ),
    )


class SendInvitesRequest(BaseModel):
    """Request to send interview invites to candidates in the shortlist."""


    pass


@router.get("")
def list_pipelines(
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    runs = list_pipeline_runs(user_id=x_recruiter_id)
    return {
        "runs": [
            {
                "thread_id": r.get("thread_id"),
                "status": r.get("status"),
                "current_stage": r.get("current_stage"),
                "job_title": r.get("jd_title", "Unknown"),
                "shortlist_count": r.get("shortlist_count", 0),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            for r in runs
        ]
    }


@router.get("/{thread_id}")
def get_pipeline(
    thread_id: str,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)

    if not state:


        state = get_pipeline_run(thread_id)

    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline {thread_id} not found")


    if state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this pipeline")

    return state


@router.delete("/{thread_id}")
def delete_pipeline(
    thread_id: str,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):
    # Ownership check: only the owner may delete their pipeline.
    state = get_pipeline_state(thread_id) or get_pipeline_run(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline {thread_id} not found")
    if state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this pipeline")

    delete_pipeline_run(thread_id)   # removes the summary + LangGraph checkpoints
    return {"deleted": True, "thread_id": thread_id}


@router.post("/start")
async def start_new_pipeline(
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
    job_description_text: str = Form(...),
    resume_files: list[UploadFile] = File(...),
):


    from utils.resume_parser import extract_resume_text

    if not resume_files:
        raise HTTPException(status_code=400, detail="At least one resume file is required")


    candidates: list[dict] = []

    for idx, file in enumerate(resume_files):
        try:
            clean_text, name, email = await extract_resume_text(file)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse resume {file.filename}: {exc}",
            )

        candidate = Candidate(
            candidate_id=str(uuid4()),
            name=name or file.filename.rsplit(".", 1)[0],
            email=email or "placeholder@example.com",
            raw_resume_text=clean_text,
            file_name=file.filename,
        )
        candidates.append(candidate.model_dump(mode="json"))


    thread_id = str(uuid4())
    now = datetime.utcnow().isoformat()

    initial_state: PipelineState = {
        "thread_id": thread_id,
        "user_id": x_recruiter_id,
        "status": PipelineStatus.PROCESSING,
        "current_stage": PipelineStage.JD_PARSING,
        "error_message": None,
        "job_description": {
            "raw_text": job_description_text,
            "title": "Parsing...",
            "required_skills": [],
            "nice_to_have_skills": [],
            "years_experience_required": None,
            "seniority": "mid",
            "salary_range": None,
            "location": "Unknown",
            "remote_policy": "Unknown",
            "team_size_context": None,
            "contradictions_found": [],
        },
        "candidates": candidates,
        "shortlist": [],
        "interview_plans": [],
        "interview_feedback": [],
        "evaluations": [],
        "offer_drafts": [],
        "created_at": now,
        "updated_at": now,
    }


    create_pipeline_run(
        thread_id=thread_id,
        user_id=x_recruiter_id,
        jd_title="Parsing...",
    )


    # Fetch recruiter profile to include in offer letters
    try:
        from memory.database import get_recruiter_profile as _grp
        _profile = _grp(email=x_recruiter_id) or {}
        initial_state["recruiter_name"] = _profile.get("name", "")
        initial_state["recruiter_role"] = _profile.get("role", "")
    except Exception:
        pass

    try:
        state_after_screening = start_pipeline(initial_state)
    except Exception as exc:
        import traceback as _tb
        _detail = f"Graph execution failed: {type(exc).__name__}: {exc}\n{_tb.format_exc()}"
        update_pipeline_run(
            thread_id,
            {
                "status": PipelineStatus.FAILED,
                "error_message": _detail[:2000],
            },
        )
        raise HTTPException(status_code=500, detail=f"Pipeline start failed: {type(exc).__name__}: {exc}")


    jd_title = state_after_screening.get("job_description", {}).get("title", "Unknown Role")
    update_pipeline_run(thread_id, {
        **state_after_screening,
        "jd_title": jd_title,
        "shortlist_count": len(state_after_screening.get("shortlist", [])),
    })

    return state_after_screening


@router.post("/{thread_id}/approve-shortlist")
def approve_shortlist(
    thread_id: str,
    request: ApproveShortlistRequest,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if state.get("current_stage") != PipelineStage.SHORTLIST_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline is at {state.get('current_stage')}, not shortlist review",
        )


    state_update: dict = {
        "shortlist": request.candidates,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if request.all_candidates:
        # Persist email corrections back onto the main candidates list
        state_update["candidates"] = request.all_candidates

    try:
        new_state = resume_pipeline(thread_id, state_update)
    except Exception as exc:
        update_pipeline_run(thread_id, {"error_message": f"Resume failed: {exc}"})
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}")

    approved_count = sum(
        1 for c in new_state.get("shortlist", [])
        if (c.get("score") or {}).get("human_approved") is True
    )
    update_pipeline_run(thread_id, {**new_state, "shortlist_count": approved_count})
    return new_state


@router.post("/{thread_id}/approve-plans")
def approve_interview_plans(
    thread_id: str,
    request: ApprovePlansRequest,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if state.get("current_stage") != PipelineStage.FINALIST_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline is at {state.get('current_stage')}, not finalist review",
        )

    state_update: dict = {
        "interview_plans": request.interview_plans,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if request.candidates:
        state_update["candidates"] = request.candidates

    try:
        new_state = resume_pipeline(thread_id, state_update)
    except Exception as exc:
        update_pipeline_run(thread_id, {"error_message": f"Resume failed: {exc}"})
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}")

    update_pipeline_run(thread_id, new_state)
    return new_state


@router.post("/{thread_id}/feedback")
def submit_interview_feedback(
    thread_id: str,
    request: SubmitFeedbackRequest,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if state.get("current_stage") != PipelineStage.AWAITING_FEEDBACK:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline is at {state.get('current_stage')}, not awaiting feedback",
        )

    state_update = {
        "interview_feedback": request.interview_feedback,
        "updated_at": datetime.utcnow().isoformat(),
    }


    try:
        from graph.pipeline import pipeline, get_config
        config = get_config(thread_id)
        pipeline.update_state(config, state_update)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"State update failed: {exc}")


    new_state = {**state, **state_update}
    update_pipeline_run(thread_id, new_state)
    return new_state


@router.post("/{thread_id}/resume-evaluator")
def resume_after_feedback(
    thread_id: str,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if state.get("current_stage") != PipelineStage.AWAITING_FEEDBACK:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline is at {state.get('current_stage')}, not awaiting feedback",
        )

    try:
        new_state = resume_pipeline(thread_id)
    except Exception as exc:
        update_pipeline_run(thread_id, {"error_message": f"Resume failed: {exc}"})
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}")

    update_pipeline_run(thread_id, new_state)
    return new_state


@router.post("/{thread_id}/approve-offer-candidates")
def approve_offer_candidates(
    thread_id: str,
    request: ApproveOfferCandidatesRequest,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if state.get("current_stage") != PipelineStage.OFFER_CANDIDATES_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline is at {state.get('current_stage')}, not offer candidates review",
        )

    state_update = {
        "evaluations": request.evaluations,
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        new_state = resume_pipeline(thread_id, state_update)
    except Exception as exc:
        update_pipeline_run(thread_id, {"error_message": f"Resume failed: {exc}"})
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}")

    update_pipeline_run(thread_id, new_state)
    return new_state


@router.post("/{thread_id}/approve-offers")
def approve_final_offers(
    thread_id: str,
    request: ApproveOffersRequest,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if state.get("current_stage") != PipelineStage.OFFER_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline is at {state.get('current_stage')}, not offer review",
        )

    state_update = {
        "offer_drafts": request.offer_drafts,
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        new_state = resume_pipeline(thread_id, state_update)
    except Exception as exc:
        update_pipeline_run(thread_id, {"error_message": f"Resume failed: {exc}"})
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}")


    if new_state.get("current_stage") == PipelineStage.COMPLETED:
        mark_pipeline_completed(thread_id)

    update_pipeline_run(thread_id, new_state)
    return new_state


@router.post("/{thread_id}/send-invites")
async def send_interview_invites(
    thread_id: str,
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):


    from utils.email_client import send_interview_invite

    state = get_pipeline_state(thread_id)
    if not state or state.get("user_id") != x_recruiter_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    current_stage = state.get("current_stage")

    if current_stage not in [
        PipelineStage.FINALIST_REVIEW,
        PipelineStage.AWAITING_FEEDBACK,
        PipelineStage.INTERVIEW_EVALUATION,
        PipelineStage.OFFER_CANDIDATES_REVIEW,
        PipelineStage.OFFER_DRAFTING,
        PipelineStage.OFFER_REVIEW,
        PipelineStage.SENDING_OFFERS,
        PipelineStage.COMPLETED,
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invites can only be sent after interview plans are approved. "
                f"Pipeline is at {current_stage}."
            ),
        )

    candidates: list[dict] = state.get("candidates", [])
    plans: list[dict] = state.get("interview_plans", [])
    jd: dict = state.get("job_description", {})

    candidate_map = {c.get("candidate_id"): c for c in candidates}

    invited: list[str] = []
    failed: list[dict] = []

    for plan in plans:
        candidate_id = plan.get("candidate_id")
        candidate = candidate_map.get(candidate_id, {})
        candidate_email = candidate.get("email", "")
        candidate_name = candidate.get("name", "Unknown")

        if not candidate_email:
            failed.append({
                "candidate_id": candidate_id,
                "reason": "No email address on file",
            })
            continue

        try:
            # The invite email embeds one .ics calendar attachment per
            # scheduled round, so recipients can add events to any calendar.
            send_interview_invite(
                user_id=x_recruiter_id,
                to_email=candidate_email,
                candidate_name=candidate_name,
                job_title=jd.get("title", "the role"),
                rounds=plan.get("rounds", []),
            )
            invited.append(candidate_id)

        except Exception as exc:
            failed.append({
                "candidate_id": candidate_id,
                "reason": f"Email send failed: {exc}",
            })

    return {
        "invited": invited,
        "failed": failed,
        "message": (
            f"Sent {len(invited)} invite(s). "
            + (f"{len(failed)} error(s)." if failed else "All succeeded.")
        ),
    }

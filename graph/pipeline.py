from __future__ import annotations

from datetime import datetime

from langgraph.graph import StateGraph, END

from models.pipeline import (
    PipelineState,
    PipelineStage,
    PipelineStatus,
    EmailStatus,
)
from agents.jd_parser import run_jd_parser
from agents.resume_screener import run_resume_screener
from agents.interview_planner import run_interview_planner
from agents.interview_evaluator import run_interview_evaluator
from agents.offer_drafter import run_offer_drafter
from memory.checkpointer import checkpointer


def _shortlist_review(state: PipelineState) -> dict:
    """Recruiter approved/modified the shortlist. Advance to interview planning."""
    return {"current_stage": PipelineStage.INTERVIEW_PLANNING}


def _finalist_review(state: PipelineState) -> dict:
    """Recruiter approved interview plans. Advance to awaiting real interview feedback."""
    return {"current_stage": PipelineStage.AWAITING_FEEDBACK}


def _awaiting_feedback(state: PipelineState) -> dict:
    """Recruiter submitted interview feedback. Advance to evaluation."""
    return {"current_stage": PipelineStage.INTERVIEW_EVALUATION}


def _offer_candidates_review(state: PipelineState) -> dict:
    """Recruiter selected who gets offers. Advance to offer drafting."""
    return {"current_stage": PipelineStage.OFFER_DRAFTING}


def _offer_review(state: PipelineState) -> dict:
    """Recruiter approved/modified offer drafts. Advance to sending."""
    return {"current_stage": PipelineStage.SENDING_OFFERS}


def _send_offers(state: PipelineState) -> dict:


    from utils.email_client import send_offer_email

    user_id: str = state.get("user_id", "")
    offer_drafts: list[dict] = state.get("offer_drafts", [])
    candidates: list[dict] = state.get("candidates", [])


    candidate_map: dict[str, dict] = {
        c.get("candidate_id"): c for c in candidates
    }

    updated_drafts: list[dict] = []
    errors: list[str] = []

    for draft in offer_drafts:

        if draft.get("human_approved") is not True:
            updated_drafts.append(draft)
            continue


        if draft.get("email_status") == EmailStatus.SENT:
            updated_drafts.append(draft)
            continue

        candidate_id: str = draft.get("candidate_id", "")
        candidate: dict = candidate_map.get(candidate_id, {})
        candidate_email: str = candidate.get("email", "")
        candidate_name: str = candidate.get("name", candidate_id)

        if not candidate_email:
            errors.append(f"No email address for candidate {candidate_id} — skipped.")
            updated_drafts.append({**draft, "email_status": EmailStatus.FAILED})
            continue

        try:
            send_offer_email(
                user_id=user_id,
                to_email=candidate_email,
                candidate_name=candidate_name,
                offer_letter_text=draft.get("offer_letter_text", ""),
            )
            updated_drafts.append({
                **draft,
                "email_status": EmailStatus.SENT,
                "sent_at": datetime.utcnow().isoformat(),
            })
        except Exception as exc:
            errors.append(f"Failed to send to {candidate_email}: {exc}")
            updated_drafts.append({**draft, "email_status": EmailStatus.FAILED})

    error_message = None
    if errors:
        error_message = "Send Offers errors: " + " | ".join(errors)

    return {
        "offer_drafts": updated_drafts,
        "current_stage": PipelineStage.COMPLETED,
        "status": PipelineStatus.COMPLETED,
        "error_message": error_message,
    }


def _build_pipeline() -> object:


    graph = StateGraph(PipelineState)


    graph.add_node("jd_parser",              run_jd_parser)
    graph.add_node("resume_screener",         run_resume_screener)
    graph.add_node("shortlist_review",        _shortlist_review)
    graph.add_node("interview_planner",       run_interview_planner)
    graph.add_node("finalist_review",         _finalist_review)
    graph.add_node("awaiting_feedback",       _awaiting_feedback)
    graph.add_node("interview_evaluator",     run_interview_evaluator)
    graph.add_node("offer_candidates_review", _offer_candidates_review)
    graph.add_node("offer_drafter",           run_offer_drafter)
    graph.add_node("offer_review",            _offer_review)
    graph.add_node("send_offers",             _send_offers)


    graph.set_entry_point("jd_parser")


    graph.add_edge("jd_parser",               "resume_screener")
    graph.add_edge("resume_screener",          "shortlist_review")
    graph.add_edge("shortlist_review",         "interview_planner")
    graph.add_edge("interview_planner",        "finalist_review")
    graph.add_edge("finalist_review",          "awaiting_feedback")
    graph.add_edge("awaiting_feedback",        "interview_evaluator")
    graph.add_edge("interview_evaluator",      "offer_candidates_review")
    graph.add_edge("offer_candidates_review",  "offer_drafter")
    graph.add_edge("offer_drafter",            "offer_review")
    graph.add_edge("offer_review",             "send_offers")
    graph.add_edge("send_offers",              END)


    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[
            "shortlist_review",
            "finalist_review",
            "awaiting_feedback",
            "offer_candidates_review",
            "offer_review",
        ],
    )


pipeline = _build_pipeline()


def get_config(thread_id: str) -> dict:


    # `configurable.thread_id` keys the LangGraph checkpoint.
    # `metadata` + `tags` are attached to LangSmith traces so a run can be
    # filtered by thread_id (e.g. to debug one specific hiring pipeline).
    return {
        "configurable": {"thread_id": thread_id},
        "metadata":     {"thread_id": thread_id},
        "tags":         ["hiregraph", "pipeline"],
    }


def start_pipeline(initial_state: PipelineState) -> dict:


    config = get_config(initial_state["thread_id"])
    return pipeline.invoke(initial_state, config=config)


def resume_pipeline(thread_id: str, state_update: dict | None = None) -> dict:


    config = get_config(thread_id)

    if state_update:
        pipeline.update_state(config, state_update)

    return pipeline.invoke(None, config=config)


def get_pipeline_state(thread_id: str) -> dict | None:


    config = get_config(thread_id)
    snapshot = pipeline.get_state(config)
    if snapshot is None:
        return None
    return dict(snapshot.values)

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models.pipeline import (
    EmailStatus,
    OfferDraft,
    JobDescription,
    PipelineState,
    PipelineStage,
)
from memory.agentic_rag import rag
from prompts.agents import OFFER_DRAFTER_PROMPT
from utils.tracing import traceable


_llm = ChatOpenAI(
    model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
    temperature=0,
)


def _extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text.strip()


def _build_candidate_profile(
    candidate: dict,
    evaluation: dict,
    jd: JobDescription,
) -> str:


    ev = evaluation or {}
    salary_range = ""
    if jd.salary_range:
        salary_range = (
            f"\nJD Salary Range: {jd.salary_range.currency} "
            f"{jd.salary_range.min:,} – {jd.salary_range.max:,}"
        )

    return (
        f"Candidate Name: {candidate.get('name', 'Unknown')}\n"
        f"Role: {jd.title} ({jd.seniority})\n"
        f"Location: {jd.location} | Remote Policy: {jd.remote_policy}"
        f"{salary_range}\n"
        f"\nInterview Evaluation:"
        f"\n  Composite Score: {ev.get('composite_score', 'N/A')}/100"
        f"\n  Recommendation: {ev.get('final_recommendation', 'N/A')}"
        f"\n  Confidence: {ev.get('confidence', 'N/A')}"
        f"\n  Reasoning Summary: {ev.get('reasoning', 'N/A')}"
    )


@traceable(name="Draft offer", run_type="chain")
def _draft_offer(
    candidate: dict,
    evaluation: dict,
    jd: JobDescription,
    market_context: str,
    recruiter_name: str = "The Hiring Team",
    recruiter_role: str = "",
) -> OfferDraft:


    candidate_id: str = candidate.get("candidate_id", "unknown")

    profile = _build_candidate_profile(candidate, evaluation, jd)

    signing_info = recruiter_name
    if recruiter_role:
        signing_info += f", {recruiter_role}"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    human_content = (
        f"Today's date: {today}\n"
        f"{profile}"
        f"\n\nMARKET COMPENSATION DATA:\n{market_context}"
        f"\n\nSign the offer letter as: {signing_info}"
    )

    messages = [
        SystemMessage(content=OFFER_DRAFTER_PROMPT),
        HumanMessage(content=human_content),
    ]

    try:
        response = _llm.invoke(messages)
        raw_content: str = response.content
    except Exception as exc:
        raise RuntimeError(
            f"LLM call failed for offer drafting of candidate {candidate_id}: {exc}"
        ) from exc

    try:
        clean_json = _extract_json(raw_content)
        parsed: dict = json.loads(clean_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Non-JSON response for candidate {candidate_id}: {exc}. "
            f"Raw: {raw_content[:300]}"
        ) from exc

    try:
        offer = OfferDraft(
            candidate_id=candidate_id,
            base_salary=int(parsed.get("base_salary", 0)),
            equity=parsed.get("equity") or None,
            start_date=parsed.get("start_date") or None,
            offer_letter_text=parsed.get("offer_letter_text", ""),
            market_data_used=parsed.get("market_data_used", ""),
            salary_reasoning=parsed.get("salary_reasoning", ""),
            email_status=EmailStatus.NOT_SENT,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Pydantic validation failed for OfferDraft of {candidate_id}: {exc}"
        ) from exc

    return offer


@traceable(name="Agent 5: Offer Drafter", run_type="chain")
def run_offer_drafter(state: PipelineState) -> dict:


    evaluations: list[dict] = state.get("evaluations", [])
    candidates: list[dict] = state.get("candidates", [])
    jd_dict: dict = state.get("job_description", {})
    recruiter_name: str = state.get("recruiter_name", "The Hiring Team")
    recruiter_role: str = state.get("recruiter_role", "")

    if not evaluations:
        return {
            "error_message": "Offer Drafter: no evaluations found in state.",
            "current_stage": PipelineStage.OFFER_DRAFTING,
        }

    if not jd_dict:
        return {
            "error_message": "Offer Drafter: no job description found in state.",
            "current_stage": PipelineStage.OFFER_DRAFTING,
        }


    try:
        jd = JobDescription(**jd_dict)
    except Exception as exc:
        return {
            "error_message": f"Offer Drafter: could not reconstruct JobDescription: {exc}",
            "current_stage": PipelineStage.OFFER_DRAFTING,
        }


    approved_evals = [
        ev for ev in evaluations
        if ev.get("human_approved") is True
    ]

    if not approved_evals:
        return {
            "error_message": (
                "Offer Drafter: no human-approved candidates found. "
                "Recruiter must approve at least one candidate at the offer candidates review."
            ),
            "current_stage": PipelineStage.OFFER_DRAFTING,
        }


    candidate_map: dict[str, dict] = {
        c.get("candidate_id"): c for c in candidates
    }


    market_query = (
        f"{jd.seniority} {jd.title} salary compensation "
        f"{jd.location} {jd.remote_policy}"
    )
    user_id: str = state.get("user_id", "")
    # Salary is public market data, so web fallback (default on) is appropriate here.
    market_result = rag.query(query=market_query, namespace="company_rubrics", user_id=user_id)

    if market_result.has_context():
        market_context = market_result.context
    else:


        market_context = (
            "No market compensation data is currently available in the database. "
            "Use the job description salary range midpoint as a baseline and note "
            "that market validation is needed before sending this offer."
        )


    offer_drafts: list[dict] = []
    errors: list[str] = []

    for evaluation in approved_evals:
        candidate_id = evaluation.get("candidate_id")
        candidate = candidate_map.get(candidate_id, {})

        try:
            offer: OfferDraft = _draft_offer(
                candidate, evaluation, jd, market_context,
                recruiter_name=recruiter_name, recruiter_role=recruiter_role,
            )
            offer_drafts.append(offer.model_dump(mode="json"))
        except RuntimeError as exc:
            errors.append(str(exc))

    if not offer_drafts:
        return {
            "error_message": (
                "Offer Drafter: all candidates failed offer drafting. Errors: "
                + " | ".join(errors)
            ),
            "current_stage": PipelineStage.OFFER_DRAFTING,
        }

    error_message = None
    if errors:
        error_message = (
            f"Offer Drafter completed with {len(errors)} error(s): "
            + " | ".join(errors)
        )

    return {
        "offer_drafts": offer_drafts,
        "current_stage": PipelineStage.OFFER_REVIEW,
        "error_message": error_message,
    }

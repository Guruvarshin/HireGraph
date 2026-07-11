from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models.pipeline import (
    InterviewPlan,
    InterviewRound,
    JobDescription,
    PipelineState,
    PipelineStage,
    PlannedInterview,
)
from memory.agentic_rag import rag
from prompts.agents import INTERVIEW_PLANNER_PROMPT
from utils.tracing import traceable


_llm = ChatOpenAI(
    model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
    temperature=0,
)
_structured_llm = _llm.with_structured_output(PlannedInterview)


@traceable(name="Plan candidate interview", run_type="chain")
def _plan_for_candidate(
    candidate: dict,
    jd: JobDescription,
    rubric_context: str,
) -> InterviewPlan:


    candidate_id: str = candidate.get("candidate_id", "unknown")
    resume_text: str = candidate.get("raw_resume_text", "")
    score: dict = candidate.get("score") or {}


    score_summary = ""
    if score:
        dim = score.get("dimension_scores", {})
        score_summary = (
            f"\n\nSCREENING SCORE SUMMARY:"
            f"\n  Overall: {score.get('overall_score', 'N/A')}/100"
            f"\n  Skills Match: {dim.get('skills_match', 'N/A')}/100"
            f"\n  Experience Relevance: {dim.get('experience_relevance', 'N/A')}/100"
            f"\n  Seniority Signal: {dim.get('seniority_signal', 'N/A')}/100"
            f"\n  Resume Quality: {dim.get('resume_quality', 'N/A')}/100"
            f"\n  Screener Reasoning: {score.get('reasoning', 'N/A')}"
        )

    jd_summary = (
        f"Job Title: {jd.title}\n"
        f"Seniority: {jd.seniority.value}\n"
        f"Required Skills: {', '.join(jd.required_skills)}\n"
        f"Nice-to-have Skills: {', '.join(jd.nice_to_have_skills)}\n"
        f"Years of Experience Required: {jd.years_experience_required}\n"
        f"Location: {jd.location} | Remote Policy: {jd.remote_policy}"
    )

    human_content = (
        f"JOB DESCRIPTION:\n{jd_summary}"
        f"{score_summary}"
        f"{rubric_context}"
        f"\n\nCANDIDATE RESUME:\n{resume_text}"
    )

    messages = [
        SystemMessage(content=INTERVIEW_PLANNER_PROMPT),
        HumanMessage(content=human_content),
    ]

    try:
        parsed: PlannedInterview = _structured_llm.invoke(messages)
    except Exception as exc:
        raise RuntimeError(
            f"LLM call failed for interview planning of candidate {candidate_id}: {exc}"
        ) from exc

    if not parsed.rounds:
        raise RuntimeError(
            f"Interview planner produced no rounds for candidate {candidate_id}."
        )

    rounds = [InterviewRound(**r.model_dump()) for r in parsed.rounds]
    return InterviewPlan(candidate_id=candidate_id, rounds=rounds)


@traceable(name="Agent 3: Interview Planner", run_type="chain")
def run_interview_planner(state: PipelineState) -> dict:


    shortlist: list[dict] = state.get("shortlist", [])
    jd_dict: dict = state.get("job_description", {})

    if not jd_dict:
        return {
            "error_message": "Interview Planner: no job description found in state.",
            "current_stage": PipelineStage.INTERVIEW_PLANNING,
        }


    approved = [
        c for c in shortlist
        if c.get("score", {}) and c.get("score", {}).get("human_approved") is True
    ]

    if not approved:
        return {
            "error_message": (
                "Interview Planner: no human-approved candidates found. "
                "Recruiter must approve at least one candidate in the shortlist review."
            ),
            "current_stage": PipelineStage.INTERVIEW_PLANNING,
        }


    try:
        jd = JobDescription(**jd_dict)
    except Exception as exc:
        return {
            "error_message": f"Interview Planner: could not reconstruct JobDescription: {exc}",
            "current_stage": PipelineStage.INTERVIEW_PLANNING,
        }


    user_id: str = state.get("user_id", "")
    rubric_result = rag.query(
        query=f"interview process rounds format for {jd.seniority.value} {jd.title}",
        namespace="company_rubrics",
        user_id=user_id,
        allow_web_fallback=False,  # rubric is proprietary; generic web results would mislead
    )
    rubric_context = ""
    if rubric_result.has_context():
        rubric_context = (
            "\n\nCOMPANY INTERVIEW RUBRIC (use this to align rounds with company process):\n"
            + rubric_result.context
        )


    interview_plans: list[dict] = []
    errors: list[str] = []

    for candidate in approved:
        try:
            plan: InterviewPlan = _plan_for_candidate(candidate, jd, rubric_context)
            interview_plans.append(plan.model_dump(mode="json"))
        except RuntimeError as exc:
            errors.append(str(exc))

    if not interview_plans:
        return {
            "error_message": (
                f"Interview Planner: all candidates failed planning. Errors: "
                + " | ".join(errors)
            ),
            "current_stage": PipelineStage.INTERVIEW_PLANNING,
        }

    error_message = None
    if errors:
        error_message = (
            f"Interview Planner completed with {len(errors)} error(s): "
            + " | ".join(errors)
        )

    return {
        "interview_plans": interview_plans,
        "current_stage": PipelineStage.FINALIST_REVIEW,
        "error_message": error_message,
    }

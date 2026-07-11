from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models.pipeline import (
    EvaluatedInterview,
    InterviewEvaluation,
    PipelineState,
    PipelineStage,
)
from prompts.agents import INTERVIEW_EVALUATOR_PROMPT
from utils.tracing import traceable


_llm = ChatOpenAI(
    model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
    temperature=0,
)
_structured_llm = _llm.with_structured_output(EvaluatedInterview)


def _format_feedback(feedback: dict) -> str:


    lines = [f"Candidate ID: {feedback.get('candidate_id', 'unknown')}"]
    for rf in feedback.get("round_feedbacks", []):
        lines.append(
            f"\nRound {rf.get('round_number')} - Interviewer: {rf.get('interviewer_name')}"
            f"\n  Recommendation: {rf.get('recommendation')}"
            f"\n  Technical Score (1-5): {rf.get('technical_score')}"
            f"\n  Communication Score (1-5): {rf.get('communication_score')}"
            f"\n  Culture Score (1-5): {rf.get('culture_score')}"
            f"\n  Notes: {rf.get('notes', '')}"
        )
    return "\n".join(lines)


@traceable(name="Evaluate candidate", run_type="chain")
def _evaluate_candidate(
    feedback: dict,
    candidate: dict | None,
    jd_title: str,
) -> InterviewEvaluation:


    candidate_id: str = feedback.get("candidate_id", "unknown")
    candidate_name: str = (candidate or {}).get("name", "Unknown Candidate")

    feedback_block = _format_feedback(feedback)


    human_content = (
        f"Role: {jd_title}\n"
        f"Candidate: {candidate_name}\n\n"
        f"INTERVIEW FEEDBACK:\n{feedback_block}"
    )

    messages = [
        SystemMessage(content=INTERVIEW_EVALUATOR_PROMPT),
        HumanMessage(content=human_content),
    ]

    try:
        parsed: EvaluatedInterview = _structured_llm.invoke(messages)
    except Exception as exc:
        raise RuntimeError(
            f"LLM call failed for evaluating candidate {candidate_id}: {exc}"
        ) from exc

    return InterviewEvaluation(candidate_id=candidate_id, **parsed.model_dump())


@traceable(name="Agent 4: Interview Evaluator", run_type="chain")
def run_interview_evaluator(state: PipelineState) -> dict:


    feedback_list: list[dict] = state.get("interview_feedback", [])
    candidates: list[dict] = state.get("candidates", [])
    jd_dict: dict = state.get("job_description", {})

    if not feedback_list:
        return {
            "error_message": (
                "Interview Evaluator: no interview feedback found. "
                "Recruiter must submit feedback via the /feedback endpoint before this stage."
            ),
            "current_stage": PipelineStage.AWAITING_FEEDBACK,
        }


    candidate_map: dict[str, dict] = {
        c.get("candidate_id"): c for c in candidates
    }

    jd_title: str = jd_dict.get("title", "the role")


    evaluations: list[dict] = []
    errors: list[str] = []

    for feedback in feedback_list:
        candidate_id = feedback.get("candidate_id")
        candidate = candidate_map.get(candidate_id)

        try:
            evaluation: InterviewEvaluation = _evaluate_candidate(
                feedback, candidate, jd_title
            )
            evaluations.append(evaluation.model_dump(mode="json"))
        except RuntimeError as exc:
            errors.append(str(exc))

    if not evaluations:
        return {
            "error_message": (
                "Interview Evaluator: all candidates failed evaluation. Errors: "
                + " | ".join(errors)
            ),
            "current_stage": PipelineStage.INTERVIEW_EVALUATION,
        }

    error_message = None
    if errors:
        error_message = (
            f"Interview Evaluator completed with {len(errors)} error(s): "
            + " | ".join(errors)
        )

    return {
        "evaluations": evaluations,
        "current_stage": PipelineStage.OFFER_CANDIDATES_REVIEW,
        "error_message": error_message,
    }

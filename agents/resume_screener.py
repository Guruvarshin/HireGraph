from __future__ import annotations

import json
import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models.pipeline import (
    CandidateScore,
    DimensionScores,
    JobDescription,
    PipelineState,
    PipelineStage,
)
from memory.agentic_rag import rag
from prompts.agents import RESUME_SCREENER_PROMPT
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


def _normalise_bias_flags(raw) -> list[str]:
    """Accept either a list of strings or a dict of {flag: bool} from the LLM."""
    if isinstance(raw, list):
        return [str(f) for f in raw]
    if isinstance(raw, dict):
        return [key for key, val in raw.items() if val]
    return []


@traceable(name="Score candidate", run_type="chain")
def _score_candidate(
    candidate: dict,
    jd: JobDescription,
    rubric_context: str,
) -> CandidateScore | None:


    resume_text: str = candidate.get("raw_resume_text", "")
    candidate_id: str = candidate.get("candidate_id", "unknown")

    if not resume_text.strip():

        return CandidateScore(
            candidate_id=candidate_id,
            overall_score=0,
            dimension_scores=DimensionScores(
                skills_match=0,
                experience_relevance=0,
                seniority_signal=0,
                resume_quality=0,
            ),
            reasoning="Resume text was empty - could not evaluate.",
            bias_flags=[],
            recommended_for_shortlist=False,
        )


    jd_summary = (
        f"Job Title: {jd.title}\n"
        f"Required Skills: {', '.join(jd.required_skills)}\n"
        f"Nice-to-have Skills: {', '.join(jd.nice_to_have_skills)}\n"
        f"Years of Experience Required: {jd.years_experience_required}\n"
        f"Seniority: {jd.seniority.value}\n"
        f"Location: {jd.location} | Remote Policy: {jd.remote_policy}"
    )

    human_content = (
        f"JOB DESCRIPTION SUMMARY:\n{jd_summary}"
        f"{rubric_context}"
        f"\n\nCANDIDATE RESUME:\n{resume_text}"
    )

    messages = [
        SystemMessage(content=RESUME_SCREENER_PROMPT),
        HumanMessage(content=human_content),
    ]

    try:
        response = _llm.invoke(messages)
        raw_content: str = response.content
    except Exception as exc:

        raise RuntimeError(f"LLM call failed for candidate {candidate_id}: {exc}") from exc

    try:
        clean_json = _extract_json(raw_content)
        parsed: dict = json.loads(clean_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Non-JSON response for candidate {candidate_id}: {exc}. "
            f"Raw: {raw_content[:300]}"
        ) from exc


    try:
        dim = parsed.get("dimension_scores", {})
        score = CandidateScore(
            candidate_id=candidate_id,
            overall_score=parsed.get("overall_score", 0),
            dimension_scores=DimensionScores(
                skills_match=dim.get("skills_match", 0),
                experience_relevance=dim.get("experience_relevance", 0),
                seniority_signal=dim.get("seniority_signal", 0),
                resume_quality=dim.get("resume_quality", 0),
            ),
            reasoning=parsed.get("reasoning", ""),
            bias_flags=_normalise_bias_flags(parsed.get("bias_flags", [])),
            recommended_for_shortlist=parsed.get("recommended_for_shortlist", False),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Pydantic validation failed for candidate {candidate_id}: {exc}"
        ) from exc

    return score


@traceable(name="Agent 2: Resume Screener", run_type="chain")
def run_resume_screener(state: PipelineState) -> dict:


    jd_dict: dict = state.get("job_description", {})
    candidates: list[dict] = state.get("candidates", [])

    if not jd_dict:
        return {
            "error_message": "Resume Screener: no job description found in state.",
            "current_stage": PipelineStage.RESUME_SCREENING,
        }

    # Guard: if JD parsing failed the title stays "Parsing..." - don't screen against a bad JD
    if jd_dict.get("title", "Parsing...") == "Parsing...":
        return {
            "error_message": (
                "Resume Screener: JD parsing did not complete successfully. "
                "Check the JD parser error above."
            ),
            "current_stage": PipelineStage.RESUME_SCREENING,
        }

    if not candidates:
        return {
            "error_message": "Resume Screener: no candidates found in state.",
            "current_stage": PipelineStage.RESUME_SCREENING,
        }

    try:
        jd = JobDescription(**jd_dict)
    except Exception as exc:
        return {
            "error_message": f"Resume Screener: could not reconstruct JobDescription: {exc}",
            "current_stage": PipelineStage.RESUME_SCREENING,
        }


    user_id: str = state.get("user_id", "")
    rubric_result = rag.query(
        query=f"scoring criteria for {jd.seniority.value} {jd.title}",
        namespace="company_rubrics",
        user_id=user_id,
        allow_web_fallback=False,  # rubric is proprietary; generic web results would mislead
    )
    rubric_context = ""
    if rubric_result.has_context():
        rubric_context = (
            "\n\nCOMPANY RUBRIC CONTEXT (use this to calibrate scores):\n"
            + rubric_result.context
        )


    updated_candidates: list[dict] = []
    shortlist: list[dict] = []
    errors: list[str] = []

    for candidate in candidates:
        try:
            score: CandidateScore = _score_candidate(candidate, jd, rubric_context)


            candidate_with_score = {
                **candidate,
                "score": score.model_dump(mode="json"),
            }
            updated_candidates.append(candidate_with_score)


            if score.recommended_for_shortlist:
                shortlist.append(candidate_with_score)

        except RuntimeError as exc:


            errors.append(str(exc))
            updated_candidates.append({
                **candidate,
                "score": None,
                "score_error": str(exc),
            })


    error_message = None
    if errors:
        error_message = f"Screener completed with {len(errors)} error(s): " + " | ".join(errors)

    return {
        "candidates": updated_candidates,
        "shortlist": shortlist,
        "current_stage": PipelineStage.SHORTLIST_REVIEW,
        "error_message": error_message,
    }

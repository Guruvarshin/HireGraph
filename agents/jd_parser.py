from __future__ import annotations

import json
import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models.pipeline import JobDescription, PipelineState, PipelineStage, Seniority
from memory.agentic_rag import rag
from prompts.agents import JD_PARSER_PROMPT


_llm = ChatOpenAI(
    model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
    temperature=0,
)

_VALID_SENIORITY = {s.value for s in Seniority}
_SENIORITY_ALIASES = {
    "lead": "senior", "principal engineer": "principal", "staff engineer": "staff",
    "entry": "junior", "entry-level": "junior", "entry level": "junior",
    "associate": "junior", "l3": "junior", "l4": "mid", "l5": "senior",
    "l6": "staff", "l7": "principal", "manager": "senior", "director": "director",
    "vp": "director", "intern": "intern",
}


def _extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    # Strip any leading/trailing non-JSON text
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text


def _coerce_years(raw) -> int | None:
    """Accept int, float, or strings like '5', '5+', '3-5', '3 to 5'."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    s = str(raw).strip()
    # Take first number found
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _coerce_seniority(raw) -> str:
    if not raw:
        return "mid"
    val = str(raw).lower().strip()
    if val in _VALID_SENIORITY:
        return val
    for alias, mapped in _SENIORITY_ALIASES.items():
        if alias in val:
            return mapped
    return "mid"


def _sanitise_parsed(parsed: dict, raw_jd: str) -> dict:
    """Coerce LLM output into shapes the Pydantic model expects."""
    return {
        "raw_text":                raw_jd,
        "title":                   str(parsed.get("title") or "Unknown Role").strip(),
        "required_skills":         [str(s) for s in (parsed.get("required_skills") or [])],
        "nice_to_have_skills":     [str(s) for s in (parsed.get("nice_to_have_skills") or [])],
        "years_experience_required": _coerce_years(parsed.get("years_experience_required")),
        "seniority":               _coerce_seniority(parsed.get("seniority")),
        "salary_range":            parsed.get("salary_range") or None,
        "location":                str(parsed.get("location") or "Unknown").strip(),
        "remote_policy":           str(parsed.get("remote_policy") or "Unknown").strip(),
        "team_size_context":       parsed.get("team_size_context") or None,
        "contradictions_found":    [str(c) for c in (parsed.get("contradictions_found") or [])],
    }


def run_jd_parser(state: PipelineState) -> dict:
    raw_jd: str = state.get("job_description", {}).get("raw_text", "")

    if not raw_jd.strip():
        return {
            "error_message": "JD Parser: job description text is empty.",
            "current_stage": PipelineStage.JD_PARSING,
        }

    user_id: str = state.get("user_id", "")
    # Optional RAG context
    rubric_result = rag.query(
        "hiring standards seniority expectations",
        namespace="company_rubrics",
        user_id=user_id,
        allow_web_fallback=False,  # rubric is proprietary; generic web results would mislead
    )
    rubric_context = ""
    if rubric_result.has_context():
        rubric_context = "\n\nCOMPANY RUBRIC CONTEXT:\n" + rubric_result.context

    messages = [
        SystemMessage(content=JD_PARSER_PROMPT),
        HumanMessage(content=f"JOB DESCRIPTION:\n{raw_jd}{rubric_context}"),
    ]

    try:
        response = _llm.invoke(messages)
        raw_content: str = response.content
    except Exception as exc:
        return {
            "error_message": f"JD Parser: LLM call failed - {exc}",
            "current_stage": PipelineStage.JD_PARSING,
        }

    try:
        clean_json = _extract_json(raw_content)
        parsed: dict = json.loads(clean_json)
    except json.JSONDecodeError as exc:
        return {
            "error_message": f"JD Parser: LLM returned non-JSON - {exc}. Raw: {raw_content[:300]}",
            "current_stage": PipelineStage.JD_PARSING,
        }

    sanitised = _sanitise_parsed(parsed, raw_jd)

    try:
        job_description = JobDescription(**sanitised)
    except Exception as exc:
        return {
            "error_message": f"JD Parser: validation failed after sanitisation - {exc}",
            "current_stage": PipelineStage.JD_PARSING,
        }

    return {
        "job_description": job_description.model_dump(mode="json"),
        "current_stage": PipelineStage.RESUME_SCREENING,
        "error_message": None,
    }

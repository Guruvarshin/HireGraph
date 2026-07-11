from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models.pipeline import JobDescription, ParsedJD, PipelineState, PipelineStage
from memory.agentic_rag import rag
from prompts.agents import JD_PARSER_PROMPT
from utils.tracing import traceable


_llm = ChatOpenAI(
    model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
    temperature=0,
)
# Constrain the model to emit exactly the ParsedJD schema (valid seniority enum,
# typed fields) - no free-form JSON to extract or coerce afterwards.
_structured_llm = _llm.with_structured_output(ParsedJD)


@traceable(name="Agent 1: JD Parser", run_type="chain")
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
        parsed: ParsedJD = _structured_llm.invoke(messages)
    except Exception as exc:
        return {
            "error_message": f"JD Parser: LLM call failed - {exc}",
            "current_stage": PipelineStage.JD_PARSING,
        }

    try:
        job_description = JobDescription(raw_text=raw_jd, **parsed.model_dump())
    except Exception as exc:
        return {
            "error_message": f"JD Parser: validation failed - {exc}",
            "current_stage": PipelineStage.JD_PARSING,
        }

    return {
        "job_description": job_description.model_dump(mode="json"),
        "current_stage": PipelineStage.RESUME_SCREENING,
        "error_message": None,
    }

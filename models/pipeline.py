from __future__ import annotations

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
from enum import Enum
from typing import Optional, TypedDict

from pydantic import BaseModel, EmailStr, Field


class PipelineStatus(str, Enum):
    PENDING                    = "pending"
    PROCESSING                 = "processing"
    AWAITING_HUMAN             = "awaiting_human"
    AWAITING_INTERVIEW_FEEDBACK = "awaiting_interview_feedback"
    FAILED                     = "failed"
    COMPLETED                  = "completed"


class PipelineStage(str, Enum):
    JD_PARSING              = "jd_parsing"
    RESUME_SCREENING        = "resume_screening"
    SHORTLIST_REVIEW        = "shortlist_review"
    INTERVIEW_PLANNING      = "interview_planning"
    FINALIST_REVIEW         = "finalist_review"
    AWAITING_FEEDBACK       = "awaiting_feedback"
    INTERVIEW_EVALUATION    = "interview_evaluation"
    OFFER_CANDIDATES_REVIEW = "offer_candidates_review"
    OFFER_DRAFTING          = "offer_drafting"
    OFFER_REVIEW            = "offer_review"
    SENDING_OFFERS          = "sending_offers"
    COMPLETED               = "completed"


class Seniority(str, Enum):
    INTERN    = "intern"
    JUNIOR    = "junior"
    MID       = "mid"
    SENIOR    = "senior"
    STAFF     = "staff"
    PRINCIPAL = "principal"
    DIRECTOR  = "director"


class InterviewType(str, Enum):
    TECHNICAL      = "technical"
    BEHAVIORAL     = "behavioral"
    SYSTEM_DESIGN  = "system_design"
    PORTFOLIO      = "portfolio"
    HIRING_MANAGER = "hiring_manager"
    CULTURE        = "culture"


class HireRecommendation(str, Enum):
    STRONG_HIRE = "strong_hire"
    HIRE        = "hire"
    MAYBE       = "maybe"
    NO_HIRE     = "no_hire"


class EmailStatus(str, Enum):
    NOT_SENT = "not_sent"
    PENDING  = "pending"
    SENT     = "sent"
    FAILED   = "failed"


class SalaryRange(BaseModel):
    min: int
    max: int
    currency: str = "USD"


class JobDescription(BaseModel):
    raw_text: str
    title: str
    required_skills: list[str]
    nice_to_have_skills: list[str]
    years_experience_required: Optional[int] = None
    seniority: Seniority
    salary_range: Optional[SalaryRange] = None
    location: str
    remote_policy: str
    team_size_context: Optional[str] = None
    contradictions_found: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    candidate_id: str
    name: str
    email: EmailStr
    raw_resume_text: str
    file_name: str
    uploaded_at: datetime = Field(default_factory=_utcnow)
    parse_failed: bool = False
    parse_error: Optional[str] = None


class DimensionScores(BaseModel):
    skills_match: int = Field(ge=0, le=100)
    experience_relevance: int = Field(ge=0, le=100)
    seniority_signal: int = Field(ge=0, le=100)
    resume_quality: int = Field(ge=0, le=100)


class CandidateScore(BaseModel):
    candidate_id: str
    overall_score: int = Field(ge=0, le=100)
    dimension_scores: DimensionScores
    reasoning: str
    bias_flags: list[str] = Field(default_factory=list)
    recommended_for_shortlist: bool
    human_approved: Optional[bool] = None
    human_modified: bool = False


class InterviewRound(BaseModel):
    round_number: int
    type: InterviewType
    duration_minutes: int = 60
    interviewers: list[str]
    interviewer_emails: list[str] = Field(default_factory=list)
    questions: list[str]
    calendar_event_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    email_sent: bool = False


class InterviewPlan(BaseModel):
    candidate_id: str
    rounds: list[InterviewRound]
    human_approved: Optional[bool] = None
    emails_sent: bool = False


class RoundFeedback(BaseModel):
    round_number: int
    interviewer_name: str
    recommendation: HireRecommendation
    technical_score: int = Field(ge=1, le=5)
    communication_score: int = Field(ge=1, le=5)
    culture_score: int = Field(ge=1, le=5)
    notes: str


class InterviewFeedback(BaseModel):
    candidate_id: str
    round_feedbacks: list[RoundFeedback]
    submitted_at: datetime = Field(default_factory=_utcnow)


class InterviewEvaluation(BaseModel):
    candidate_id: str
    final_recommendation: HireRecommendation
    confidence: float = Field(ge=0.0, le=1.0)
    composite_score: int = Field(ge=0, le=100)
    reasoning: str
    dissenting_notes: Optional[str] = None
    recommended_for_offer: bool
    human_approved: Optional[bool] = None


class OfferDraft(BaseModel):
    candidate_id: str
    base_salary: int
    equity: Optional[str] = None
    start_date: Optional[str] = None
    offer_letter_text: str
    market_data_used: str
    salary_reasoning: str
    human_approved: Optional[bool] = None
    human_modified_salary: Optional[int] = None
    human_modified_equity: Optional[str] = None
    human_modified_start_date: Optional[str] = None
    email_status: EmailStatus = EmailStatus.NOT_SENT
    sent_at: Optional[datetime] = None

    def final_salary(self) -> int:
        return self.human_modified_salary or self.base_salary

    def final_equity(self) -> Optional[str]:
        return self.human_modified_equity or self.equity

    def final_start_date(self) -> Optional[str]:
        return self.human_modified_start_date or self.start_date


# ---------------------------------------------------------------------------
# LLM output schemas
#
# These mirror the domain models above but contain ONLY the fields an agent's
# LLM should generate. App-managed fields (candidate_id, email_status,
# human_approved, calendar ids, ...) are injected by the agent after the call.
# They are passed to `ChatOpenAI.with_structured_output(...)` so the model is
# constrained to emit exactly this shape - no post-hoc JSON parsing needed.
# ---------------------------------------------------------------------------


class ParsedJD(BaseModel):
    title: str
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    years_experience_required: Optional[int] = None
    seniority: Seniority
    salary_range: Optional[SalaryRange] = None
    location: str
    remote_policy: str
    team_size_context: Optional[str] = None
    contradictions_found: list[str] = Field(default_factory=list)


class ScoredResume(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    dimension_scores: DimensionScores
    reasoning: str
    bias_flags: list[str] = Field(default_factory=list)
    recommended_for_shortlist: bool


class PlannedRound(BaseModel):
    round_number: int
    type: InterviewType
    duration_minutes: int = 60
    interviewers: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class PlannedInterview(BaseModel):
    rounds: list[PlannedRound] = Field(default_factory=list)


class EvaluatedInterview(BaseModel):
    final_recommendation: HireRecommendation
    confidence: float = Field(ge=0.0, le=1.0)
    composite_score: int = Field(ge=0, le=100)
    reasoning: str
    dissenting_notes: Optional[str] = None
    recommended_for_offer: bool


class DraftedOffer(BaseModel):
    base_salary: int
    equity: Optional[str] = None
    start_date: Optional[str] = None
    offer_letter_text: str
    market_data_used: str
    salary_reasoning: str


class PipelineState(TypedDict, total=False):
    thread_id:          str
    user_id:            str
    recruiter_name:     str
    recruiter_role:     str
    status:             str
    current_stage:      str
    error_message:      Optional[str]

    job_description:    Optional[dict]
    candidates:         list[dict]
    shortlist:          list[dict]
    interview_plans:    list[dict]
    interview_feedback: list[dict]
    evaluations:        list[dict]
    offer_drafts:       list[dict]

    created_at:         str
    updated_at:         str

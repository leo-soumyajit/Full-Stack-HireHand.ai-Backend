"""
EOS-IA Psychometric Intelligence System — Pydantic Models
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Position-level: Psychometric Profile ──────────────────────────────────

class PsychometricQuestion(BaseModel):
    trait: str                   # e.g. "Decisiveness under ambiguity"
    question: str                # the interview question text
    why_important: str           # why this trait matters for the role
    scoring_guide: str           # "1 = freezes under pressure, 10 = confident decisive action"


class PsychometricProfile(BaseModel):
    position_id: str
    user_id: str
    role_title: str
    level: str
    business_unit: str
    company_context: str         # extracted company/culture context
    business_model: str          # FMCG / Tech / Infra / etc.
    role_type: str               # execution | strategy | governance | people
    key_stressors: List[str]
    required_traits: List[PsychometricQuestion]
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PsychometricProfileResponse(BaseModel):
    id: str
    position_id: str
    role_title: str
    level: str
    business_unit: str
    company_context: str
    business_model: str
    role_type: str
    key_stressors: List[str]
    required_traits: List[PsychometricQuestion]
    generated_at: str


# ── Candidate-level: Interviewer Scores ───────────────────────────────────

class TraitScore(BaseModel):
    trait: str                   # must match a required_trait.trait from the position profile
    score: float = Field(ge=1, le=10)
    notes: Optional[str] = None  # interviewer notes


class CandidateScoreSubmit(BaseModel):
    scores: List[TraitScore]


class CandidateScoreResponse(BaseModel):
    id: str
    candidate_id: str
    position_id: str
    scores: List[TraitScore]
    submitted_at: str


# ── Candidate-level: AI-Generated Fitment Report ──────────────────────────

class TraitInterpretation(BaseModel):
    trait: str
    score: float
    interpretation: str          # "Strong decisiveness — acts confidently under pressure"


class PatternCluster(BaseModel):
    name: str                    # e.g. "Strategic Executor"
    description: str             # 2-3 sentence behavioral summary
    sentiment: str               # positive | neutral | negative


class PsychometricRisk(BaseModel):
    level: str                   # LOW | MEDIUM | HIGH
    statement: str               # short risk headline
    role_specific_risk: str      # detailed risk tied to this specific role


class FitmentVerdict(BaseModel):
    decision: str                # GO | CONDITIONAL GO | NO-GO
    rationale: str               # why this verdict
    coaching_note: str           # what to watch / develop


class FitmentReport(BaseModel):
    candidate_id: str
    position_id: str
    user_id: str
    trait_matrix: List[TraitInterpretation]
    pattern_cluster: PatternCluster
    risk: PsychometricRisk
    verdict: FitmentVerdict
    composite_psych_score: float  # 0–100
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class FitmentReportResponse(BaseModel):
    id: str
    candidate_id: str
    position_id: str
    trait_matrix: List[TraitInterpretation]
    pattern_cluster: PatternCluster
    risk: PsychometricRisk
    verdict: FitmentVerdict
    composite_psych_score: float
    generated_at: str


# ── Full Automated Assessment Flow Models ─────────────────────────────────

class AssessmentQuestionOption(BaseModel):
    id: str
    text: str

class AssessmentQuestion(BaseModel):
    id: str
    trait_assessed: str
    scenario: str
    options: List[AssessmentQuestionOption]

class AssessmentTest(BaseModel):
    position_id: str
    role_title: str
    time_limit_minutes: int
    questions: List[AssessmentQuestion]
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class AssessmentLink(BaseModel):
    token: str
    candidate_id: str
    position_id: str
    user_id: str
    expires_at: str
    is_completed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class QuestionResponse(BaseModel):
    question_id: str
    selected_option_id: str
    time_spent_ms: int

class AssessmentSubmission(BaseModel):
    candidate_id: str
    position_id: str
    responses: List[QuestionResponse]
    total_time_spent_ms: int
    submitted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


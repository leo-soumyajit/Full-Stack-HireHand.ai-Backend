"""
Resume Screening Models — EOS-IA AI Resume Intelligence
"""
from pydantic import BaseModel
from typing import Optional

class ResumeAnalysis(BaseModel):
    candidate_name: str
    candidate_email: Optional[str] = None
    candidate_current_role: Optional[str] = None
    resume_score: float                  # 0-10
    jd_match_percent: int               # 0-100
    strengths: list[str]
    gaps: list[str]
    experience_summary: str
    verdict: str                        # STRONG FIT | POTENTIAL FIT | WEAK FIT | NOT SUITABLE
    verdict_rationale: str
    recommended_stage: str              # Screened | Interview L1 | Rejected

class ResumeScreenResponse(BaseModel):
    analysis: ResumeAnalysis
    candidate_id: Optional[str] = None  # set if auto-created
    position_id: str
    raw_text_length: int

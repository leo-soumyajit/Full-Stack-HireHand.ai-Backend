from pydantic import BaseModel, EmailStr
from typing import Optional


class CandidateScores(BaseModel):
    resume: float = 0.0
    psych: float = 0.0
    composite: int = 0


class CandidateCreate(BaseModel):
    name: str
    role: str
    email: EmailStr
    stage: str = "Sourced"


class CandidateUpdate(BaseModel):
    stage: Optional[str] = None
    verdict: Optional[str] = None  # "Go" | "Conditional" | "No-Go"
    scores: Optional[CandidateScores] = None


class CandidateResponse(BaseModel):
    id: str
    position_id: str
    name: str
    role: str
    email: str
    stage: str
    scores: CandidateScores
    verdict: str = "Pending"
    added_date: str

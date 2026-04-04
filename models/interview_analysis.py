"""Pydantic models for AI Interview Intelligence System."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class EndInterviewRequest(BaseModel):
    """Sent by frontend when interviewer ends the call."""
    schedule_id: str
    transcript: str = Field(..., min_length=10, description="Full interview transcript")
    duration_seconds: int = Field(..., ge=0, description="Total interview duration in seconds")


class InterviewAnalysisResponse(BaseModel):
    """Full analysis response returned to frontend."""
    id: str
    schedule_id: str
    position_id: str
    candidate_id: str
    candidate_name: str
    position_title: str
    status: str  # "processing" | "completed" | "failed"
    duration_seconds: int
    transcript: str
    created_at: str

    # Populated after AI analysis completes
    interviewer_report: Optional[dict] = None
    candidate_report: Optional[dict] = None
    interviewer_quality: Optional[dict] = None
    error: Optional[str] = None


class InterviewAnalysisListItem(BaseModel):
    """Compact item for listing analyses."""
    id: str
    schedule_id: str
    candidate_name: str
    position_title: str
    status: str
    duration_seconds: int
    created_at: str
    overall_score: Optional[float] = None
    verdict: Optional[str] = None

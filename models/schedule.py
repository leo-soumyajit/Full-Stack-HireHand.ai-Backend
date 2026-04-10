from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime


class ScheduleCreate(BaseModel):
    candidate_id: str
    position_id: str
    scheduled_at: str  # ISO 8601 string


class ScheduleUpdate(BaseModel):
    status: Optional[str] = None
    scheduled_at: Optional[str] = None


class ScheduleResponse(BaseModel):
    id: str
    candidate_id: str
    position_id: str
    user_id: str
    candidate_name: str
    candidate_email: str
    candidate_role: str
    position_title: str
    scheduled_at: str
    meeting_link: str
    room_id: Optional[str] = None
    interview_round: int = 1  # L1=1, L2=2, L3=3, ...
    status: str  # "Scheduled", "Completed", "Cancelled"
    created_at: str

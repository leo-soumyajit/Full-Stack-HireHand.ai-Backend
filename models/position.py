from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class L1Question(BaseModel):
    id: str
    text: str
    category: str
    difficulty: str
    level: Optional[str] = None  # "L1" | "L2" | "L3" | "L4" | "L5"

class PositionL1QuestionsUpdate(BaseModel):
    questions: List[L1Question]


class CustomSectionConfig(BaseModel):
    name: str
    weight_percentage: int

class PositionScreeningRules(BaseModel):
    enabled: bool = False
    sections: List[CustomSectionConfig] = []
    auto_select_threshold: int = 80
    auto_reject_threshold: int = 50


class PositionJD(BaseModel):
    purpose: str = ""
    education: List[str] = []
    experience: List[str] = []
    responsibilities: List[str] = []
    skills: List[str] = []
    non_negotiables: List[str] = []


class JDVersion(BaseModel):
    version: int
    jd: PositionJD
    createdAt: str


class PositionCreate(BaseModel):
    title: str
    business_unit: str
    location: str = "Remote"
    level: str = "Mid"  # Junior | Mid | Senior | Executive
    years_of_experience: Optional[str] = None


class PositionUpdate(BaseModel):
    title: Optional[str] = None
    business_unit: Optional[str] = None
    location: Optional[str] = None
    level: Optional[str] = None
    years_of_experience: Optional[str] = None


class PositionStatusUpdate(BaseModel):
    status: str  # "Active" | "Closed"


class PositionJDUpdate(BaseModel):
    jd: PositionJD
    version: int


class PositionResponse(BaseModel):
    id: str
    req_id: str
    title: str
    business_unit: str
    location: str
    level: str
    years_of_experience: Optional[str] = None
    status: str
    jd: Optional[PositionJD] = None
    jd_versions: List[JDVersion] = []
    l1_questions: List[L1Question] = []
    screening_rules: Optional[PositionScreeningRules] = None
    candidates_count: int = 0
    shortlisted_count: int = 0
    risk_flag: Optional[str] = None
    risk_level: Optional[str] = None
    created_at: str
    updated_at: str

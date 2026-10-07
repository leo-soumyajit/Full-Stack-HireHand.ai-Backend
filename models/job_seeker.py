"""
Job Seeker Portal models — fully isolated from the HR `users` system.
Powers: seeker auth, Naukri-style profile, applications, public job board,
and AI job recommendations.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


# ── Auth ────────────────────────────────────────────────────────────
class SeekerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=6)


class SeekerLogin(BaseModel):
    email: EmailStr
    password: str


class SeekerVerifyOTP(BaseModel):
    email: EmailStr
    otp: str


class SeekerResendOTP(BaseModel):
    email: EmailStr


class SeekerForgotPassword(BaseModel):
    email: EmailStr


class SeekerResetPassword(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class SeekerChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


# ── Profile sub-objects ─────────────────────────────────────────────
class WorkExperience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[str] = None


class SeekerPreferences(BaseModel):
    desired_roles: List[str] = []
    preferred_locations: List[str] = []
    job_type: Optional[str] = None  # Full-time | Part-time | Internship | Remote | Contract
    expected_salary: Optional[str] = None


class SeekerSocialLinks(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None


class SeekerProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    avatar_url: Optional[str] = None
    current_role: Optional[str] = None
    total_experience_years: Optional[float] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    education: Optional[List[Education]] = None
    work_experience: Optional[List[WorkExperience]] = None
    preferences: Optional[SeekerPreferences] = None
    social_links: Optional[SeekerSocialLinks] = None


class SeekerResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    is_verified: bool = False
    phone: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    avatar_url: Optional[str] = None
    current_role: Optional[str] = None
    total_experience_years: Optional[float] = None
    summary: Optional[str] = None
    skills: List[str] = []
    education: List[dict] = []
    work_experience: List[dict] = []
    preferences: Optional[dict] = None
    social_links: Optional[dict] = None
    resume_url: Optional[str] = None
    has_resume: bool = False
    profile_complete: bool = False


class SeekerToken(BaseModel):
    access_token: str
    token_type: str
    seeker: SeekerResponse


# ── Applications ────────────────────────────────────────────────────
class ApplicationCreate(BaseModel):
    position_id: str
    cover_note: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: str
    position_id: str
    job_title: str
    company_name: Optional[str] = None
    company_logo: Optional[str] = None
    location: Optional[str] = None
    status: str
    match_percent: Optional[int] = None
    applied_at: str


# ── Public job board ────────────────────────────────────────────────
class JobPublicResponse(BaseModel):
    id: str
    title: str
    company_name: Optional[str] = None
    company_logo: Optional[str] = None
    location: str = "Remote"
    level: str = "Mid"
    business_unit: Optional[str] = None
    years_of_experience: Optional[str] = None
    purpose: str = ""
    responsibilities: List[str] = []
    skills: List[str] = []
    education: List[str] = []
    experience: List[str] = []
    published_at: Optional[str] = None
    applicant_count: int = 0


# ── Recommendations ─────────────────────────────────────────────────
class RecommendationItem(BaseModel):
    job: JobPublicResponse
    match_percent: int
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    reason: Optional[str] = None
    already_applied: bool = False

"""
Auth dependency for the Job Seeker portal — isolated from HR `get_current_user`.
Seeker JWTs carry `typ: "seeker"`; this dependency validates that and loads the
seeker from the `job_seekers` collection, so HR tokens can never authenticate
seeker routes and vice-versa.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.security import decode_access_token
from database import job_seekers_collection

seeker_security = HTTPBearer()


async def get_current_seeker(
    credentials: HTTPAuthorizationCredentials = Depends(seeker_security),
) -> dict:
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("typ") != "seeker":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a job seeker token",
        )

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    seeker = await job_seekers_collection.find_one({"email": email}, {"hashed_password": 0})
    if seeker is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Seeker not found")

    seeker["id"] = str(seeker.pop("_id"))
    return seeker


def serialize_seeker(doc: dict) -> dict:
    """Build a SeekerResponse-shaped dict from a job_seekers document."""
    skills = doc.get("skills") or []
    has_resume = bool(doc.get("resume_url") or doc.get("resume_text"))
    return {
        "id": str(doc.get("_id") or doc.get("id", "")),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "is_verified": doc.get("is_verified", False),
        "phone": doc.get("phone"),
        "headline": doc.get("headline"),
        "location": doc.get("location"),
        "avatar_url": doc.get("avatar_url"),
        "current_role": doc.get("current_role"),
        "total_experience_years": doc.get("total_experience_years"),
        "summary": doc.get("summary"),
        "skills": skills,
        "education": doc.get("education") or [],
        "work_experience": doc.get("work_experience") or [],
        "preferences": doc.get("preferences"),
        "social_links": doc.get("social_links"),
        "resume_url": doc.get("resume_url"),
        "has_resume": has_resume,
        "profile_complete": bool(skills and has_resume),
    }

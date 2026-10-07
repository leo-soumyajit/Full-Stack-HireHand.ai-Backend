"""
Job Seeker profile — Naukri-style profile management + resume intelligence.
Mounted at /api/seeker.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import io
import base64
import os
from datetime import datetime, timezone

import cloudinary
import cloudinary.uploader

from core.seeker_deps import get_current_seeker, serialize_seeker
from core.seeker_ai import extract_profile_from_resume
from core.embeddings import embed_text, profile_to_text
from database import job_seekers_collection
from models.job_seeker import SeekerProfileUpdate, SeekerResponse

router = APIRouter()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "di5i72sy9"),
    api_key=os.getenv("CLOUDINARY_API_KEY", "572758113724938"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", "LBnZ_kEVCCCRJ5B63jN2hcZ226k"),
    secure=True,
)


class ResumeUploadRequest(BaseModel):
    file_base64: str
    filename: str = "resume.pdf"


class AvatarUploadRequest(BaseModel):
    file_base64: str  # data URL or raw base64


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read PDF: {str(e)}")


async def _recompute_embedding(email: str) -> None:
    """Refresh the seeker's profile embedding after profile/resume changes."""
    doc = await job_seekers_collection.find_one({"email": email})
    if not doc:
        return
    vec = await embed_text(profile_to_text(doc))
    if vec:
        await job_seekers_collection.update_one(
            {"email": email}, {"$set": {"profile_embedding": vec}}
        )


@router.get("/profile", response_model=SeekerResponse)
async def get_profile(seeker: dict = Depends(get_current_seeker)):
    return serialize_seeker(seeker)


@router.put("/profile", response_model=SeekerResponse)
async def update_profile(body: SeekerProfileUpdate, seeker: dict = Depends(get_current_seeker)):
    update = body.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Normalize nested pydantic models to plain dicts
    for k in ("education", "work_experience"):
        if k in update and update[k] is not None:
            update[k] = [e.model_dump() if hasattr(e, "model_dump") else e for e in update[k]]
    for k in ("preferences", "social_links"):
        if k in update and update[k] is not None and hasattr(update[k], "model_dump"):
            update[k] = update[k].model_dump()

    await job_seekers_collection.update_one({"email": seeker["email"]}, {"$set": update})
    await _recompute_embedding(seeker["email"])
    updated = await job_seekers_collection.find_one({"email": seeker["email"]})
    return serialize_seeker(updated)


@router.post("/profile/resume")
async def upload_resume(payload: ResumeUploadRequest, seeker: dict = Depends(get_current_seeker)):
    """Upload resume PDF → parse text → AI extracts structured profile → store + embed."""
    if not payload.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")
    raw = payload.file_base64.split(",", 1)[-1]  # tolerate data URL prefix
    try:
        file_bytes = base64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file data.")
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Resume must be under 10 MB.")

    resume_text = _extract_pdf_text(file_bytes)
    if len(resume_text) < 50:
        raise HTTPException(status_code=422, detail="Could not extract text — is this a scanned image?")

    # AI structured extraction (best-effort; never hard-fail the upload)
    extracted = {}
    try:
        extracted = await extract_profile_from_resume(resume_text) or {}
    except Exception as e:
        print(f"⚠️ [seeker_profile] resume parse failed: {e}")

    # Store the PDF on Cloudinary (raw)
    resume_url = None
    try:
        up = cloudinary.uploader.upload(
            file_bytes, resource_type="raw", folder="hirehand/resumes",
            public_id=f"seeker_{seeker['id']}", overwrite=True,
        )
        resume_url = up.get("secure_url")
    except Exception as e:
        print(f"⚠️ [seeker_profile] cloudinary resume upload failed: {e}")

    set_doc = {
        "resume_text": resume_text,
        "structured_profile": extracted,
        "resume_uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if resume_url:
        set_doc["resume_url"] = resume_url

    # Fill profile fields from the resume (don't clobber a name the user set)
    field_map = ["headline", "location", "current_role", "total_experience_years",
                 "summary", "skills", "education", "work_experience", "social_links", "phone"]
    for f in field_map:
        val = extracted.get(f)
        if val not in (None, "", [], {}):
            set_doc[f] = val
    if not seeker.get("name") and extracted.get("name"):
        set_doc["name"] = extracted["name"]

    await job_seekers_collection.update_one({"email": seeker["email"]}, {"$set": set_doc})
    await _recompute_embedding(seeker["email"])

    updated = await job_seekers_collection.find_one({"email": seeker["email"]})
    return {"profile": serialize_seeker(updated), "parsed": bool(extracted)}


@router.post("/profile/avatar")
async def upload_avatar(payload: AvatarUploadRequest, seeker: dict = Depends(get_current_seeker)):
    raw = payload.file_base64.split(",", 1)[-1]
    try:
        img = base64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image data.")
    try:
        up = cloudinary.uploader.upload(img, folder="hirehand/seeker_avatars",
                                        public_id=f"avatar_{seeker['id']}", overwrite=True)
        url = up.get("secure_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")
    await job_seekers_collection.update_one({"email": seeker["email"]}, {"$set": {"avatar_url": url}})
    return {"url": url}

"""
Job Seeker applications. Mounted at /api/seeker.

Applying bridges the seeker INTO the existing HR pipeline: it runs the same
AI resume screening and creates a normal `candidates` document on the HR side,
so recruiters see portal applicants exactly like manually-screened ones.
The HR side needs zero changes.
"""
from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from datetime import datetime, timezone
from typing import List
import os
import httpx

from core.seeker_deps import get_current_seeker
from core.openrouter import analyze_resume
from database import (
    positions_collection, candidates_collection,
    applications_collection, user_collection,
)
from models.job_seeker import ApplicationCreate, ApplicationResponse

router = APIRouter()

_VERDICT_MAP = {
    "STRONG FIT": "Go", "POTENTIAL FIT": "Conditional",
    "WEAK FIT": "Conditional", "NOT SUITABLE": "No-Go",
}


def _seeker_status(candidate: dict, fallback: str = "Under review") -> str:
    """Derive a candidate-facing status from the HR candidate record."""
    if not candidate:
        return fallback
    stage = (candidate.get("stage") or "").lower()
    verdict = (candidate.get("verdict") or "").lower()
    if "reject" in stage or verdict == "no-go":
        return "Not selected"
    if "offer" in stage or "select" in stage or "hired" in stage:
        return "Selected"
    if "interview" in stage:
        return "Interview"
    if "shortlist" in stage or verdict == "go":
        return "Shortlisted"
    if stage in ("screened", "sourced"):
        return "Under review"
    return fallback


async def _save_resume_to_disk(resume_url: str, candidate_id: str) -> None:
    """Mirror the Cloudinary resume to local disk so HR 'Original Resume' works."""
    if not resume_url:
        return
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(resume_url)
            if r.status_code == 200:
                os.makedirs("uploads/resumes", exist_ok=True)
                with open(f"uploads/resumes/{candidate_id}.pdf", "wb") as f:
                    f.write(r.content)
    except Exception as e:
        print(f"⚠️ [applications] could not mirror resume to disk: {e}")


@router.post("/applications", response_model=ApplicationResponse)
async def apply_to_job(body: ApplicationCreate, seeker: dict = Depends(get_current_seeker)):
    if not seeker.get("resume_text"):
        raise HTTPException(status_code=400, detail="Please upload your resume before applying.")

    try:
        oid = ObjectId(body.position_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    pos = await positions_collection.find_one({"_id": oid, "is_published": True, "status": "Active"})
    if not pos:
        raise HTTPException(status_code=404, detail="Job not found or no longer accepting applications")

    # Duplicate guard (also enforced by a unique index)
    if await applications_collection.find_one({"seeker_id": seeker["id"], "position_id": body.position_id}):
        raise HTTPException(status_code=409, detail="You have already applied to this job.")

    jd = pos.get("jd") or {}
    owner_id = pos.get("user_id", "")

    # ── Run the existing AI screening against this JD ──
    analysis = {}
    try:
        analysis = await analyze_resume(
            resume_text=seeker["resume_text"],
            jd_purpose=jd.get("purpose", ""),
            jd_responsibilities=jd.get("responsibilities", []),
            jd_experience=jd.get("experience", []),
            role_title=pos.get("title", ""),
            level=pos.get("level", "Mid"),
            business_unit=pos.get("business_unit", "General"),
            custom_rules=pos.get("screening_rules"),
            non_negotiables=jd.get("non_negotiables", []),
        )
    except Exception as e:
        print(f"⚠️ [applications] screening failed, applying without score: {e}")

    resume_score = round(max(0.0, min(10.0, float(analysis.get("resume_score", 5.0)))), 1)
    jd_match = int(max(0, min(100, analysis.get("jd_match_percent", 50))))
    composite = int(jd_match * 0.7 + resume_score * 3)
    verdict = _VERDICT_MAP.get(analysis.get("verdict", ""), "Conditional")

    # ── Create the HR-side candidate (same shape as resume_screen) ──
    candidate_doc = {
        "position_id": body.position_id,
        "user_id": owner_id,
        "name": seeker.get("name", analysis.get("candidate_name", "Applicant")),
        "role": seeker.get("current_role") or "Not specified",
        "email": seeker.get("email", ""),
        "stage": "Rejected" if analysis.get("recommended_stage") == "Rejected" else "Screened",
        "scores": {"resume": resume_score, "psych": 0.0, "composite": composite},
        "verdict": verdict,
        "resume_analysis": analysis,
        "added_via": "portal_application",
        "source": "portal",
        "seeker_id": seeker["id"],
        "resume_url": seeker.get("resume_url"),
        "created_at": datetime.utcnow().isoformat(),
    }
    cand_res = await candidates_collection.insert_one(candidate_doc)
    candidate_id = str(cand_res.inserted_id)
    await positions_collection.update_one({"_id": oid}, {"$inc": {"candidates_count": 1}})
    await _save_resume_to_disk(seeker.get("resume_url"), candidate_id)

    # ── Record the application (seeker-facing) ──
    now = datetime.now(timezone.utc).isoformat()
    app_doc = {
        "seeker_id": seeker["id"],
        "position_id": body.position_id,
        "candidate_id": candidate_id,
        "cover_note": body.cover_note,
        "status": "applied",
        "match_percent": jd_match,
        "created_at": now,
    }
    app_res = await applications_collection.insert_one(app_doc)

    company = await user_collection.find_one(
        {"_id": ObjectId(owner_id)} if owner_id else {"_id": None},
        {"company_name": 1, "company_logo": 1},
    ) if owner_id else None

    return ApplicationResponse(
        id=str(app_res.inserted_id),
        position_id=body.position_id,
        job_title=pos.get("title", ""),
        company_name=(company or {}).get("company_name"),
        company_logo=(company or {}).get("company_logo"),
        location=pos.get("location"),
        status="Under review",
        match_percent=jd_match,
        applied_at=now,
    )


@router.get("/applications", response_model=List[ApplicationResponse])
async def my_applications(seeker: dict = Depends(get_current_seeker)):
    cursor = applications_collection.find({"seeker_id": seeker["id"]}).sort("created_at", -1)
    apps = [a async for a in cursor]

    # Batch-load positions, companies, candidates for status
    pos_ids = []
    for a in apps:
        try:
            pos_ids.append(ObjectId(a["position_id"]))
        except Exception:
            pass
    positions = {}
    async for p in positions_collection.find({"_id": {"$in": pos_ids}}):
        positions[str(p["_id"])] = p
    owner_ids = [p.get("user_id") for p in positions.values() if p.get("user_id")]
    companies = {}
    oids = [ObjectId(x) for x in set(owner_ids) if x]
    if oids:
        async for u in user_collection.find({"_id": {"$in": oids}}, {"company_name": 1, "company_logo": 1}):
            companies[str(u["_id"])] = u
    cand_ids = [ObjectId(a["candidate_id"]) for a in apps if a.get("candidate_id")]
    candidates = {}
    if cand_ids:
        async for c in candidates_collection.find({"_id": {"$in": cand_ids}}):
            candidates[str(c["_id"])] = c

    out: List[ApplicationResponse] = []
    for a in apps:
        pos = positions.get(a["position_id"], {})
        owner = pos.get("user_id", "")
        comp = companies.get(owner, {})
        cand = candidates.get(a.get("candidate_id", ""), {})
        out.append(ApplicationResponse(
            id=str(a["_id"]),
            position_id=a["position_id"],
            job_title=pos.get("title", "Job"),
            company_name=comp.get("company_name"),
            company_logo=comp.get("company_logo"),
            location=pos.get("location"),
            status=_seeker_status(cand),
            match_percent=a.get("match_percent"),
            applied_at=a.get("created_at", ""),
        ))
    return out

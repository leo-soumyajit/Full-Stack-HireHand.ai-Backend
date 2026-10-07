"""
Public Job Board — no authentication required.
Mounted at /api/jobs. Serves ONLY positions that HR has published
(is_published=True) and that are still Active. Internal fields (screening
rules, candidate data, user_id) are never exposed.
"""
from fastapi import APIRouter, HTTPException, Query
from bson import ObjectId
from typing import Optional, List
import re

from database import positions_collection, user_collection, applications_collection
from models.job_seeker import JobPublicResponse

router = APIRouter()


async def _company_map(user_ids: List[str]) -> dict:
    """Map owner org user_id -> {company_name, company_logo}."""
    oids = []
    for uid in set(user_ids):
        try:
            oids.append(ObjectId(uid))
        except Exception:
            pass
    out = {}
    if not oids:
        return out
    async for u in user_collection.find(
        {"_id": {"$in": oids}}, {"company_name": 1, "company_logo": 1}
    ):
        out[str(u["_id"])] = {
            "company_name": u.get("company_name"),
            "company_logo": u.get("company_logo"),
        }
    return out


async def _applicant_counts(position_ids: List[str]) -> dict:
    counts = {}
    if not position_ids:
        return counts
    cursor = applications_collection.aggregate([
        {"$match": {"position_id": {"$in": position_ids}}},
        {"$group": {"_id": "$position_id", "n": {"$sum": 1}}},
    ])
    async for row in cursor:
        counts[row["_id"]] = row["n"]
    return counts


def _to_public(pos: dict, company: dict, applicants: int) -> JobPublicResponse:
    jd = pos.get("jd") or {}
    return JobPublicResponse(
        id=str(pos["_id"]),
        title=pos.get("title", ""),
        company_name=(company or {}).get("company_name"),
        company_logo=(company or {}).get("company_logo"),
        location=pos.get("location", "Remote"),
        level=pos.get("level", "Mid"),
        business_unit=pos.get("business_unit"),
        years_of_experience=pos.get("years_of_experience"),
        purpose=jd.get("purpose", ""),
        responsibilities=jd.get("responsibilities", []),
        skills=jd.get("skills", []),
        education=jd.get("education", []),
        experience=jd.get("experience", []),
        published_at=pos.get("published_at"),
        applicant_count=applicants,
    )


@router.get("", response_model=List[JobPublicResponse])
@router.get("/", response_model=List[JobPublicResponse])
async def list_public_jobs(
    q: Optional[str] = Query(None, description="search in title"),
    location: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = Query(50, le=100),
    skip: int = 0,
):
    query: dict = {"is_published": True, "status": "Active"}
    if q:
        query["title"] = {"$regex": re.escape(q), "$options": "i"}
    if location:
        query["location"] = {"$regex": re.escape(location), "$options": "i"}
    if level:
        query["level"] = level

    cursor = positions_collection.find(query).sort("published_at", -1).skip(skip).limit(limit)
    positions = [p async for p in cursor]
    company = await _company_map([p.get("user_id", "") for p in positions])
    counts = await _applicant_counts([str(p["_id"]) for p in positions])
    return [_to_public(p, company.get(p.get("user_id", "")), counts.get(str(p["_id"]), 0)) for p in positions]


@router.get("/{job_id}", response_model=JobPublicResponse)
async def get_public_job(job_id: str):
    try:
        oid = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID")
    pos = await positions_collection.find_one({"_id": oid, "is_published": True})
    if not pos:
        raise HTTPException(status_code=404, detail="Job not found or not published")
    company = await _company_map([pos.get("user_id", "")])
    counts = await _applicant_counts([job_id])
    return _to_public(pos, company.get(pos.get("user_id", "")), counts.get(job_id, 0))

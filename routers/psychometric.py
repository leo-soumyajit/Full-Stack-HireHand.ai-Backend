"""
EOS-IA Psychometric Intelligence System — API Router
All routes are user-scoped via JWT.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from datetime import datetime

from core.deps import get_current_user
from core.openrouter import generate_psychometric_profile, generate_fitment_report
from database import (
    positions_collection,
    candidates_collection,
    psychometric_profiles_collection,
    psychometric_reports_collection,
    psychometric_scores_collection,
)
from models.psychometric import (
    PsychometricProfileResponse,
    CandidateScoreSubmit,
    CandidateScoreResponse,
    FitmentReportResponse,
)

router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


def _get_user_id(user: dict) -> str:
    """
    deps.py pops _id and stores it as 'id'.
    Use this helper everywhere instead of user['_id'].
    """
    return user.get("id") or str(user.get("_id", ""))


# ── POSITION ENDPOINTS ─────────────────────────────────────────────────────

@router.post(
    "/positions/{position_id}/psychometric-profile",
    response_model=PsychometricProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_profile(
    position_id: str,
    user=Depends(get_current_user),
):
    """
    Generate a role-calibrated psychometric profile from the position's JD.
    Requires the position to have a saved JD.
    """
    user_id = _get_user_id(user)

    # Fetch position — try user_id match, fallback without for flexibility
    pos = await positions_collection.find_one(
        {"_id": ObjectId(position_id), "user_id": user_id}
    )
    if not pos:
        # Try without user_id in case of legacy data
        pos = await positions_collection.find_one({"_id": ObjectId(position_id)})
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    if not pos.get("jd"):
        raise HTTPException(
            status_code=400,
            detail="Position must have a saved JD before generating a psychometric profile.",
        )

    jd = pos["jd"]

    # Call LLM
    try:
        profile_data = await generate_psychometric_profile(
            jd_purpose=jd.get("purpose", ""),
            jd_responsibilities=jd.get("responsibilities", []),
            jd_experience=jd.get("experience", []),
            role_title=pos["title"],
            level=pos.get("level", "Mid"),
            business_unit=pos.get("business_unit", "General"),
            location=pos.get("location", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {str(e)}")

    doc = {
        "position_id": position_id,
        "user_id": user_id,
        "role_title": pos["title"],
        "level": pos.get("level", "Mid"),
        "business_unit": pos.get("business_unit", "General"),
        **profile_data,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Upsert: one profile per position
    await psychometric_profiles_collection.update_one(
        {"position_id": position_id, "user_id": user_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await psychometric_profiles_collection.find_one(
        {"position_id": position_id, "user_id": user_id}
    )
    return _serialize(saved)


@router.get(
    "/positions/{position_id}/psychometric-profile",
    response_model=PsychometricProfileResponse,
)
async def get_profile(position_id: str, user=Depends(get_current_user)):
    """Fetch existing psychometric profile for a position."""
    user_id = _get_user_id(user)
    doc = await psychometric_profiles_collection.find_one(
        {"position_id": position_id, "user_id": user_id}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Psychometric profile not found")
    return _serialize(doc)


# ── CANDIDATE SCORE ENDPOINTS ──────────────────────────────────────────────

@router.post(
    "/candidates/{candidate_id}/psychometric-score",
    response_model=CandidateScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_scores(
    candidate_id: str,
    body: CandidateScoreSubmit,
    user=Depends(get_current_user),
):
    """Save interviewer-submitted trait scores for a candidate."""
    user_id = _get_user_id(user)

    candidate = await candidates_collection.find_one(
        {"_id": ObjectId(candidate_id), "user_id": user_id}
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    doc = {
        "candidate_id": candidate_id,
        "position_id": candidate["position_id"],
        "user_id": user_id,
        "scores": [s.model_dump() for s in body.scores],
        "submitted_at": datetime.utcnow().isoformat(),
    }

    await psychometric_scores_collection.update_one(
        {"candidate_id": candidate_id, "user_id": user_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await psychometric_scores_collection.find_one(
        {"candidate_id": candidate_id, "user_id": user_id}
    )
    return _serialize(saved)


@router.get(
    "/candidates/{candidate_id}/psychometric-score",
    response_model=CandidateScoreResponse,
)
async def get_scores(candidate_id: str, user=Depends(get_current_user)):
    """Fetch saved interviewer scores for a candidate."""
    user_id = _get_user_id(user)
    doc = await psychometric_scores_collection.find_one(
        {"candidate_id": candidate_id, "user_id": user_id}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Scores not found")
    return _serialize(doc)


# ── FITMENT REPORT ENDPOINTS ───────────────────────────────────────────────

@router.post(
    "/candidates/{candidate_id}/psychometric-report",
    response_model=FitmentReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_report(candidate_id: str, user=Depends(get_current_user)):
    """
    Generate the 4-part EOS-IA Fitment Report using stored scores.
    Requires scores to have been submitted first.
    """
    user_id = _get_user_id(user)

    # Get candidate
    candidate = await candidates_collection.find_one(
        {"_id": ObjectId(candidate_id), "user_id": user_id}
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get scores
    score_doc = await psychometric_scores_collection.find_one(
        {"candidate_id": candidate_id, "user_id": user_id}
    )
    if not score_doc or not score_doc.get("scores"):
        raise HTTPException(
            status_code=400,
            detail="Interviewer scores must be submitted before generating the report.",
        )

    # Get psychometric profile for position
    profile_doc = await psychometric_profiles_collection.find_one(
        {"position_id": candidate["position_id"], "user_id": user_id}
    )
    if not profile_doc:
        raise HTTPException(
            status_code=400,
            detail="Psychometric profile not found for this position. Generate it first.",
        )

    # Get position for role title
    pos = await positions_collection.find_one({"_id": ObjectId(candidate["position_id"])})
    role_title = pos["title"] if pos else "Unknown Role"

    # Call LLM
    try:
        report_data = await generate_fitment_report(
            profile=profile_doc,
            candidate_name=candidate["name"],
            role_title=role_title,
            scores=score_doc["scores"],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {str(e)}")

    # ── CRITICAL: Override trait_matrix scores with EXACT interviewer-submitted values ──
    # The LLM may hallucinate or round scores — we trust the interviewer's numbers.
    submitted_score_map = {s["trait"]: s["score"] for s in score_doc["scores"]}
    if "trait_matrix" in report_data and isinstance(report_data["trait_matrix"], list):
        for item in report_data["trait_matrix"]:
            trait = item.get("trait", "")
            # Exact match first, then case-insensitive fallback
            if trait in submitted_score_map:
                item["score"] = float(submitted_score_map[trait])
            else:
                for key, val in submitted_score_map.items():
                    if key.lower() == trait.lower():
                        item["score"] = float(val)
                        break

    doc = {
        "candidate_id": candidate_id,
        "position_id": candidate["position_id"],
        "user_id": user_id,
        **report_data,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Update candidate's psych score in candidates collection for fast display
    composite = report_data.get("composite_psych_score", 0)
    verdict_obj = report_data.get("verdict", {})
    verdict_str = verdict_obj.get("decision", "Conditional") if isinstance(verdict_obj, dict) else "Conditional"

    await candidates_collection.update_one(
        {"_id": ObjectId(candidate_id)},
        {"$set": {
            "scores.psych": round(float(composite) / 10, 1),
            "verdict": verdict_str,
        }},
    )

    await psychometric_reports_collection.update_one(
        {"candidate_id": candidate_id, "user_id": user_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await psychometric_reports_collection.find_one(
        {"candidate_id": candidate_id, "user_id": user_id}
    )
    return _serialize(saved)


@router.get(
    "/candidates/{candidate_id}/psychometric-report",
    response_model=FitmentReportResponse,
)
async def get_report(candidate_id: str):
    """Fetch existing fitment report for a candidate."""
    doc = await psychometric_reports_collection.find_one(
        {"candidate_id": candidate_id}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Fitment report not found")
    return _serialize(doc)

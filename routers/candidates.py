from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
import os
from bson import ObjectId
from datetime import datetime, timezone
from typing import List
import random
import string

from database import (
    positions_collection,
    candidates_collection,
    psychometric_profiles_collection,
    psychometric_scores_collection,
    psychometric_reports_collection,
    schedules_collection
)
from pydantic import BaseModel
from models.candidate import CandidateCreate, CandidateUpdate, CandidateResponse
from core.deps import get_current_user

class BulkEmailRequest(BaseModel):
    candidate_ids: List[str]
    email_type: str = "shortlist"



router = APIRouter()


def _generate_candidate_id() -> str:
    return "cand-" + ''.join(random.choices(string.digits, k=6))


def _doc_to_response(doc: dict) -> CandidateResponse:
    return CandidateResponse(
        id=str(doc["_id"]),
        position_id=doc.get("position_id", ""),
        name=doc.get("name", ""),
        role=doc.get("role", ""),
        email=doc.get("email", ""),
        stage=doc.get("stage", "Sourced"),
        scores=doc.get("scores", {"resume": 0.0, "psych": 0.0, "composite": 0}),
        verdict=doc.get("verdict", "Conditional"),
        added_date=doc.get("added_date", ""),
    )


@router.get("/{position_id}/candidates", response_model=List[CandidateResponse])
async def get_candidates(
    position_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all candidates for a specific position owned by the current user.
    Uses (position_id, user_id) compound index for O(1) lookups.
    """
    # Ensure position belongs to this user
    await _assert_position_owner(position_id, current_user["id"])

    cursor = candidates_collection.find(
        {"position_id": position_id, "user_id": current_user["id"]}
    ).sort("added_date", -1)
    docs = await cursor.to_list(length=1000)
    return [_doc_to_response(d) for d in docs]


@router.post("/{position_id}/candidates/bulk-email", status_code=status.HTTP_200_OK)
async def send_bulk_emails(
    position_id: str,
    body: BulkEmailRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send shortlisted email to multiple candidates."""
    await _assert_position_owner(position_id, current_user["id"])
    
    pos = await positions_collection.find_one({"_id": ObjectId(position_id)})
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
        
    position_title = pos.get("title", "Position")

    cand_oids = []
    for cid in body.candidate_ids:
        try:
            cand_oids.append(ObjectId(cid))
        except:
            pass
            
    if not cand_oids:
        return {"message": "No valid candidates provided", "sent_count": 0}
        
    cursor = candidates_collection.find({"_id": {"$in": cand_oids}, "user_id": current_user["id"]})
    candidates = await cursor.to_list(length=1000)
    
    from core.email import send_shortlisted_email, send_rejection_email
    
    sent_count = 0
    for cand in candidates:
        email = cand.get("email")
        if email:
            if body.email_type == "reject":
                send_rejection_email(email, cand.get("name", "Candidate"), position_title)
            else:
                send_shortlisted_email(email, cand.get("name", "Candidate"), position_title)
            sent_count += 1
            
    return {"message": f"Successfully sent emails to {sent_count} candidates", "sent_count": sent_count}


@router.post("/{position_id}/candidates", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def add_candidate(
    position_id: str,
    body: CandidateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add a candidate to a position and auto-generate AI scores."""
    await _assert_position_owner(position_id, current_user["id"])

    # Auto-generate scores
    resume = round(6.0 + random.random() * 3.5, 1)
    psych = round(6.0 + random.random() * 3.0, 1)
    composite = round(((resume + psych) / 2) * 10)
    if composite >= 85:
        verdict = "Go"
    elif composite >= 70:
        verdict = "Conditional"
    else:
        verdict = "No-Go"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "user_id": current_user["id"],
        "position_id": position_id,
        "candidate_ref_id": _generate_candidate_id(),
        "name": body.name,
        "role": body.role,
        "email": body.email,
        "stage": body.stage,
        "scores": {"resume": resume, "psych": psych, "composite": composite},
        "verdict": verdict,
        "added_date": today,
    }
    result = await candidates_collection.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Update the position's candidates_count
    await positions_collection.update_one(
        {"_id": ObjectId(position_id) if ObjectId.is_valid(position_id) else None,
         "user_id": current_user["id"]},
        {"$inc": {"candidates_count": 1},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    return _doc_to_response(doc)


@router.patch("/candidates/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: str,
    body: CandidateUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update stage, verdict, or scores for a candidate."""
    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")

    updates = {}
    if body.stage is not None:
        updates["stage"] = body.stage
    if body.verdict is not None:
        updates["verdict"] = body.verdict
    if body.scores is not None:
        updates["scores"] = body.scores.model_dump()

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await candidates_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {"$set": updates},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _doc_to_response(result)


@router.delete("/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove a candidate."""
    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")

    candidate = await candidates_collection.find_one({"_id": oid, "user_id": current_user["id"]})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    await candidates_collection.delete_one({"_id": oid})

    # Delete all associated schedules
    await schedules_collection.delete_many({"candidate_id": candidate_id})

    # Decrement position counter
    pos_id = candidate.get("position_id")
    if pos_id and ObjectId.is_valid(pos_id):
        await positions_collection.update_one(
            {"_id": ObjectId(pos_id), "user_id": current_user["id"]},
            {"$inc": {"candidates_count": -1},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )


@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Fetch full candidate details including resume analysis."""
    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")
        
    doc = await candidates_collection.find_one({"_id": oid, "user_id": current_user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("/candidates/{candidate_id}/resume")
async def download_candidate_resume(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download the original uploaded resume PDF."""
    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")
        
    candidate = await candidates_collection.find_one({"_id": oid, "user_id": current_user["id"]})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    file_path = f"uploads/resumes/{candidate_id}.pdf"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Original resume file not found on server.")
        
    return FileResponse(
        path=file_path,
        filename=f"{candidate.get('name', 'Candidate')}_Resume.pdf",
        media_type="application/pdf"
    )

async def _assert_position_owner(position_id: str, user_id: str):
    """Ensure position_id belongs to user_id — prevents cross-user access."""
    if not ObjectId.is_valid(position_id):
        raise HTTPException(status_code=400, detail="Invalid position ID")
    pos = await positions_collection.find_one(
        {"_id": ObjectId(position_id), "user_id": user_id},
        {"_id": 1}
    )
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

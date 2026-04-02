from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from datetime import datetime, timezone
from typing import List
import random
import string

from database import positions_collection, candidates_collection
from models.position import (
    PositionCreate, PositionUpdate, PositionStatusUpdate,
    PositionJDUpdate, PositionResponse, PositionL1QuestionsUpdate,
    PositionScreeningRules
)
from core.deps import get_current_user

router = APIRouter()


def _generate_req_id() -> str:
    year = datetime.now(timezone.utc).year
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"REQ-{year}-{suffix}"


def _doc_to_response(doc: dict) -> PositionResponse:
    return PositionResponse(
        id=str(doc["_id"]),
        req_id=doc.get("req_id", ""),
        title=doc.get("title", ""),
        business_unit=doc.get("business_unit", ""),
        location=doc.get("location", "Remote"),
        level=doc.get("level", "Mid"),
        years_of_experience=doc.get("years_of_experience"),
        status=doc.get("status", "Active"),
        jd=doc.get("jd"),
        jd_versions=doc.get("jd_versions", []),
        l1_questions=doc.get("l1_questions", []),
        screening_rules=doc.get("screening_rules"),
        candidates_count=doc.get("candidates_count", 0),
        shortlisted_count=doc.get("shortlisted_count", 0),
        risk_flag=doc.get("risk_flag"),
        risk_level=doc.get("risk_level"),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@router.get("/", response_model=List[PositionResponse])
async def get_positions(
    status_filter: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Return all positions for the current user.
    Optionally filter by status=Active or status=Closed.
    Uses the compound (user_id, status, updated_at) index for low-latency pagination.
    """
    query: dict = {"user_id": current_user["id"]}
    if status_filter:
        query["status"] = status_filter

    cursor = positions_collection.find(query).sort("updated_at", -1)
    docs = await cursor.to_list(length=500)
    return [_doc_to_response(d) for d in docs]


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific position by ID."""
    try:
        oid = ObjectId(position_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid position ID format")
        
    doc = await positions_collection.find_one({"_id": oid, "user_id": current_user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Position not found")
    return _doc_to_response(doc)


@router.post("/", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
async def create_position(
    body: PositionCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new position under the authenticated user."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_id": current_user["id"],
        "req_id": _generate_req_id(),
        "title": f"{body.level} {body.title}".strip(),
        "business_unit": body.business_unit or "General",
        "location": body.location or "Remote",
        "level": body.level,
        "years_of_experience": body.years_of_experience,
        "status": "Active",
        "jd": None,
        "jd_versions": [],
        "l1_questions": [],
        "candidates_count": 0,
        "shortlisted_count": 0,
        "risk_flag": "New Opening",
        "risk_level": "new",
        "created_at": now,
        "updated_at": now,
    }
    result = await positions_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_response(doc)


@router.put("/{position_id}", response_model=PositionResponse)
async def update_position(
    position_id: str,
    body: PositionUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Edit position metadata (title, bu, location, level)."""
    oid = _validate_oid(position_id)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await positions_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {"$set": updates},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Position not found")
    return _doc_to_response(result)


@router.patch("/{position_id}/status", response_model=PositionResponse)
async def update_position_status(
    position_id: str,
    body: PositionStatusUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Toggle position between Active and Closed."""
    oid = _validate_oid(position_id)
    if body.status not in ("Active", "Closed"):
        raise HTTPException(status_code=400, detail="status must be 'Active' or 'Closed'")

    result = await positions_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {"$set": {"status": body.status, "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Position not found")
    return _doc_to_response(result)


@router.patch("/{position_id}/jd", response_model=PositionResponse)
async def save_position_jd(
    position_id: str,
    body: PositionJDUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Save or update the JD for a position (with versioning)."""
    oid = _validate_oid(position_id)
    now = datetime.now(timezone.utc).isoformat()
    new_version = {"version": body.version, "jd": body.jd.model_dump(), "createdAt": now}

    result = await positions_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {
            "$set": {"jd": body.jd.model_dump(), "updated_at": now},
            "$push": {"jd_versions": new_version}
        },
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Position not found")
    return _doc_to_response(result)


@router.put("/{position_id}/l1-questions", response_model=PositionResponse)
async def update_position_l1_questions(
    position_id: str,
    body: PositionL1QuestionsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update or save the L1 Interview questions for a position."""
    oid = _validate_oid(position_id)
    questions_dump = [q.model_dump() for q in body.questions]
    result = await positions_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {"$set": {"l1_questions": questions_dump, "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Position not found")
    return _doc_to_response(result)


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Permanently delete a position and all its candidates."""
    oid = _validate_oid(position_id)
    result = await positions_collection.delete_one({"_id": oid, "user_id": current_user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Position not found")
    # Cascade delete all candidates belonging to this position
    await candidates_collection.delete_many({"position_id": position_id})


def _validate_oid(oid_str: str) -> ObjectId:
    try:
        return ObjectId(oid_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid position ID format")

@router.put("/{position_id}/screening-rules", response_model=PositionResponse)
async def update_screening_rules(
    position_id: str,
    rules: PositionScreeningRules,
    current_user: dict = Depends(get_current_user)
):
    """Update custom AI screening rules for a position."""
    oid = _validate_oid(position_id)
    
    if rules.enabled and rules.sections:
        total_weight = sum(s.weight_percentage for s in rules.sections)
        if total_weight != 100:
            raise HTTPException(status_code=400, detail=f"Weights must sum to 100. Current sum: {total_weight}")

    result = await positions_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {"$set": {
            "screening_rules": rules.model_dump(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        return_document=True
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Position not found")
        
    return _doc_to_response(result)

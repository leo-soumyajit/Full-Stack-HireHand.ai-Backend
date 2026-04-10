from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timezone, timedelta
from typing import List
import uuid
import os

from database import schedules_collection, candidates_collection, positions_collection
from models.schedule import ScheduleCreate, ScheduleUpdate, ScheduleResponse
from core.deps import get_current_user
from core.resend_email import send_interview_email

router = APIRouter()


def _doc_to_response(doc: dict, candidate: dict, position: dict) -> ScheduleResponse:
    return ScheduleResponse(
        id=str(doc["_id"]),
        candidate_id=doc.get("candidate_id", ""),
        position_id=doc.get("position_id", ""),
        user_id=doc.get("user_id", ""),
        candidate_name=candidate.get("name", "Unknown Candidate"),
        candidate_email=candidate.get("email", ""),
        candidate_role=candidate.get("role", ""),
        position_title=position.get("title", "Unknown Position"),
        scheduled_at=doc.get("scheduled_at", ""),
        meeting_link=doc.get("meeting_link", ""),
        room_id=doc.get("room_id"),
        interview_round=doc.get("interview_round", 1),
        status=doc.get("status", "Scheduled"),
        created_at=doc.get("created_at", ""),
    )


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Schedule an interview, send a real email (via background), and generate a meet link."""
    # 1. Verify candidate exists and belongs to user
    try:
        cand_oid = ObjectId(body.candidate_id)
        pos_oid = ObjectId(body.position_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID formats")

    candidate = await candidates_collection.find_one({"_id": cand_oid, "user_id": current_user["id"]})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    position = await positions_collection.find_one({"_id": pos_oid, "user_id": current_user["id"]})
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # 2. Prevent double-scheduling for the same candidate unless previous is cancelled or in the past
    cursor = schedules_collection.find({
        "candidate_id": body.candidate_id,
        "status": "Scheduled"
    })
    
    now_utc = datetime.now(timezone.utc)
    
    async for existing in cursor:
        existing_dt = datetime.fromisoformat(existing["scheduled_at"].replace("Z", "+00:00"))
        
        # Give a 1 hour grace period to allow the meeting to happen without being "Completed"
        if existing_dt + timedelta(hours=1) > now_utc:
            raise HTTPException(status_code=400, detail="Candidate already has an active future schedule.")
        else:
            # Auto-complete past schedules just in time so they no longer block
            await schedules_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"status": "Completed"}}
            )

    # 3. Auto-compute interview round (L1, L2, L3...) for this candidate
    previous_count = await schedules_collection.count_documents({
        "candidate_id": body.candidate_id,
        "status": {"$ne": "Cancelled"},  # Don't count cancelled interviews
    })
    interview_round = previous_count + 1  # 1st interview = L1, 2nd = L2, etc.

    # 4. Create Meeting Link & Email Action
    meet_id = str(uuid.uuid4())[:10]
    meeting_link = f"https://meet.jit.si/HireHand-Interview-{meet_id}"
    room_id = f"hh-{meet_id}"

    # UTC to IST Formatting for Email & Logs
    # body.scheduled_at looks like "2026-03-12T20:40:00.000Z"
    dt_utc = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    dt_ist = dt_utc.astimezone(ist_tz)
    ist_str = dt_ist.strftime("%d %b %Y, %I:%M %p (IST)")

    # Generate HireHand Interview Room Link for the Candidate
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip("/")
    hirehand_candidate_link = f"{frontend_url}/interview/{room_id}?role=guest"

    # Log Email Dispatch
    print(f"==================================================")
    print(f"📧 [EMAIL DISPATCH TRIGGERED] To: {candidate.get('email')}")
    print(f"📝 Subject: Interview Invitation: {position.get('title')}")
    print(f"🕒 Scheduled At: {ist_str}")
    print(f"🔗 Meeting Link: {hirehand_candidate_link}")
    print(f"==================================================")

    # Queue Real Email
    background_tasks.add_task(
        send_interview_email,
        to_email=candidate.get("email"),
        candidate_name=candidate.get("name"),
        position_title=position.get("title"),
        scheduled_time_ist=ist_str,
        meeting_link=hirehand_candidate_link
    )

    # 5. Insert Schedule Doc
    doc = {
        "candidate_id": body.candidate_id,
        "position_id": body.position_id,
        "user_id": current_user["id"],
        "scheduled_at": body.scheduled_at,
        "meeting_link": meeting_link,
        "room_id": room_id,
        "interview_round": interview_round,
        "status": "Scheduled",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await schedules_collection.insert_one(doc)
    doc["_id"] = result.inserted_id

    # 6. Automatically update candidate stage to "Interview L{round}"
    await candidates_collection.update_one(
        {"_id": cand_oid},
        {"$set": {"stage": f"Interview L{interview_round}"}}
    )

    return _doc_to_response(doc, candidate, position)


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(current_user: dict = Depends(get_current_user)):
    """List all interviews for the current user."""
    cursor = schedules_collection.find({"user_id": current_user["id"]}).sort("scheduled_at", 1)
    docs = await cursor.to_list(length=1000)

    # We need to fetch candidate and position details to populate the response
    responses = []
    
    # Simple batch caching for position and candidate resolving
    cand_cache = {}
    pos_cache = {}

    # Bulk resolve logic
    for doc in docs:
        c_id = doc["candidate_id"]
        p_id = doc["position_id"]

        if c_id not in cand_cache:
            cand = await candidates_collection.find_one({"_id": ObjectId(c_id)})
            cand_cache[c_id] = cand or {}
        
        if p_id not in pos_cache:
            pos = await positions_collection.find_one({"_id": ObjectId(p_id)})
            pos_cache[p_id] = pos or {}

        responses.append(_doc_to_response(doc, cand_cache[c_id], pos_cache[p_id]))

    return responses


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    current_user: dict = Depends(get_current_user)
):
    try:
        oid = ObjectId(schedule_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid schedule ID")

    updates = {}
    if body.status is not None:
        updates["status"] = body.status
    if body.scheduled_at is not None:
        updates["scheduled_at"] = body.scheduled_at

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await schedules_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["id"]},
        {"$set": updates},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Resolve links
    candidate = await candidates_collection.find_one({"_id": ObjectId(result["candidate_id"])})
    position = await positions_collection.find_one({"_id": ObjectId(result["position_id"])})

    return _doc_to_response(result, candidate or {}, position or {})


@router.get("/{schedule_id}/questions")
async def get_schedule_questions(schedule_id: str):
    """
    Public endpoint — returns pre-generated interview questions for the scheduled
    interview's position.  The InterviewRoom page calls this so the host can view
    the question bank while interviewing. No auth required because the room link
    itself is the access token.
    """
    try:
        schedule = await schedules_collection.find_one({"_id": ObjectId(schedule_id)})
    except Exception:
        return {"questions": [], "position_title": ""}

    if not schedule:
        return {"questions": [], "position_title": ""}

    try:
        position = await positions_collection.find_one(
            {"_id": ObjectId(schedule["position_id"])}
        )
    except Exception:
        return {"questions": [], "position_title": ""}

    if not position:
        return {"questions": [], "position_title": ""}

    return {
        "questions": position.get("l1_questions", []),
        "position_title": position.get("title", ""),
    }


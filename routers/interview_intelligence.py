"""
InterviewIQ — FastAPI Router for AI Interview Intelligence.
Handles interview transcript saving, AI analysis triggering, and report retrieval.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timezone
from typing import List

from database import (
    interview_analyses_collection,
    schedules_collection,
    candidates_collection,
    positions_collection,
)
from models.interview_analysis import (
    EndInterviewRequest,
    InterviewAnalysisResponse,
    InterviewAnalysisListItem,
)
from core.deps import get_current_user
from core.interview_intelligence import run_full_analysis_pipeline
from core.resend_email import send_interview_report_email
from pydantic import BaseModel, EmailStr

router = APIRouter()

class SendReportRequest(BaseModel):
    to_email: EmailStr
    subject: str = ""
    message_body: str = ""
    sender_name: str
    sender_email: str
    company_name: str = ""
    pdf_base64: str


def _build_jd_text(position: dict) -> str:
    """Extract JD text from position document for AI analysis."""
    jd = position.get("jd") or {}
    parts = []
    if jd.get("purpose"):
        parts.append(f"Purpose: {jd['purpose']}")
    if jd.get("responsibilities"):
        parts.append("Responsibilities:\n" + "\n".join(f"- {r}" for r in jd["responsibilities"][:8]))
    if jd.get("experience"):
        parts.append("Experience:\n" + "\n".join(f"- {e}" for e in jd["experience"][:5]))
    if jd.get("qualifications"):
        parts.append("Qualifications:\n" + "\n".join(f"- {q}" for q in jd["qualifications"][:5]))
    return "\n\n".join(parts) if parts else f"Role: {position.get('title', 'Unknown')}"


async def _run_analysis_bg(analysis_id: str, transcript: str, jd_text: str, role_title: str, candidate_name: str, duration_seconds: int):
    """Background task: Run AI pipeline and update MongoDB document."""
    try:
        result = await run_full_analysis_pipeline(
            transcript=transcript,
            jd_text=jd_text,
            role_title=role_title,
            candidate_name=candidate_name,
            duration_seconds=duration_seconds,
        )

        # Extract top-level scores for quick access
        ir = result.get("interviewer_report", {})
        overall_score = ir.get("role_fit_score", None)
        verdict = ir.get("verdict", None)

        await interview_analyses_collection.update_one(
            {"_id": ObjectId(analysis_id)},
            {"$set": {
                "status": "completed",
                "parsed_transcript": result.get("parsed_transcript", {}),
                "competency_analysis": result.get("competency_analysis", {}),
                "interviewer_report": ir,
                "candidate_report": result.get("candidate_report", {}),
                "interviewer_quality": result.get("interviewer_quality", {}),
                "overall_score": overall_score,
                "verdict": verdict,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        print(f"✅ [InterviewIQ] Analysis {analysis_id} completed — Score: {overall_score}, Verdict: {verdict}")

    except Exception as e:
        print(f"❌ [InterviewIQ] Analysis {analysis_id} FAILED: {str(e)}")
        await interview_analyses_collection.update_one(
            {"_id": ObjectId(analysis_id)},
            {"$set": {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )


# ══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/end-interview", status_code=status.HTTP_201_CREATED)
async def end_interview(
    body: EndInterviewRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Called when interviewer ends the call.
    Saves transcript and triggers AI analysis in background.
    """
    # 1. Verify schedule exists and belongs to user
    try:
        schedule = await schedules_collection.find_one({
            "_id": ObjectId(body.schedule_id),
            "user_id": current_user["id"],
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid schedule ID")

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # 2. Get candidate and position
    candidate = await candidates_collection.find_one({"_id": ObjectId(schedule["candidate_id"])})
    position = await positions_collection.find_one({"_id": ObjectId(schedule["position_id"])})

    if not candidate or not position:
        raise HTTPException(status_code=404, detail="Candidate or position not found")

    # 3. Check if analysis already exists
    existing = await interview_analyses_collection.find_one({"schedule_id": body.schedule_id})
    if existing:
        return {
            "id": str(existing["_id"]),
            "status": existing.get("status", "processing"),
            "message": "Analysis already exists for this interview",
        }

    # 4. Create analysis document (status = processing)
    doc = {
        "schedule_id": body.schedule_id,
        "position_id": schedule["position_id"],
        "candidate_id": schedule["candidate_id"],
        "user_id": current_user["id"],
        "candidate_name": candidate.get("name", "Unknown"),
        "position_title": position.get("title", "Unknown"),
        "transcript": body.transcript,
        "duration_seconds": body.duration_seconds,
        "tab_switch_count": body.tab_switch_count,
        "interview_round": schedule.get("interview_round", 1),
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Populated by background task
        "parsed_transcript": None,
        "competency_analysis": None,
        "interviewer_report": None,
        "candidate_report": None,
        "interviewer_quality": None,
        "overall_score": None,
        "verdict": None,
        "error": None,
    }
    result = await interview_analyses_collection.insert_one(doc)
    analysis_id = str(result.inserted_id)

    # 5. Update schedule status to Completed
    await schedules_collection.update_one(
        {"_id": ObjectId(body.schedule_id)},
        {"$set": {"status": "Completed"}}
    )

    # 6. Update candidate stage
    await candidates_collection.update_one(
        {"_id": ObjectId(schedule["candidate_id"])},
        {"$set": {"stage": "Interview Completed"}}
    )

    # 7. Kick off AI analysis in background
    jd_text = _build_jd_text(position)
    background_tasks.add_task(
        _run_analysis_bg,
        analysis_id=analysis_id,
        transcript=body.transcript,
        jd_text=jd_text,
        role_title=position.get("title", "Unknown"),
        candidate_name=candidate.get("name", "Unknown"),
        duration_seconds=body.duration_seconds,
    )

    print(f"🚀 [InterviewIQ] Analysis {analysis_id} queued for {candidate.get('name')} — {position.get('title')}")

    return {
        "id": analysis_id,
        "status": "processing",
        "message": "Interview saved. AI analysis started in background.",
    }


@router.get("/position/{position_id}", response_model=List[InterviewAnalysisListItem])
async def list_analyses_for_position(
    position_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all interview analyses for a position."""
    cursor = interview_analyses_collection.find({
        "position_id": position_id,
        "user_id": current_user["id"],
    }).sort("created_at", -1)

    docs = await cursor.to_list(length=100)
    return [
        InterviewAnalysisListItem(
            id=str(d["_id"]),
            schedule_id=d.get("schedule_id", ""),
            candidate_id=d.get("candidate_id", ""),
            candidate_name=d.get("candidate_name", "Unknown"),
            position_title=d.get("position_title", "Unknown"),
            status=d.get("status", "processing"),
            duration_seconds=d.get("duration_seconds", 0),
            created_at=d.get("created_at", ""),
            overall_score=d.get("overall_score"),
            verdict=d.get("verdict"),
            interview_round=d.get("interview_round"),
        )
        for d in docs
    ]


@router.get("/{analysis_id}", response_model=InterviewAnalysisResponse)
async def get_analysis(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get full analysis report."""
    try:
        doc = await interview_analyses_collection.find_one({
            "_id": ObjectId(analysis_id),
            "user_id": current_user["id"],
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return {
        "id": str(doc["_id"]),
        "schedule_id": doc.get("schedule_id", ""),
        "position_id": doc.get("position_id", ""),
        "candidate_id": doc.get("candidate_id", ""),
        "candidate_name": doc.get("candidate_name", "Unknown"),
        "position_title": doc.get("position_title", "Unknown"),
        "status": doc.get("status", "processing"),
        "duration_seconds": doc.get("duration_seconds", 0),
        "transcript": doc.get("transcript", ""),
        "created_at": doc.get("created_at", ""),
        "overall_score": doc.get("overall_score"),
        "verdict": doc.get("verdict"),
        "parsed_transcript": doc.get("parsed_transcript"),
        "competency_analysis": doc.get("competency_analysis"),
        "interviewer_report": doc.get("interviewer_report"),
        "candidate_report": doc.get("candidate_report"),
        "interviewer_quality": doc.get("interviewer_quality"),
        "tab_switch_count": doc.get("tab_switch_count", 0),
        "interview_round": doc.get("interview_round"),
        "error": doc.get("error"),
    }


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete an analysis."""
    try:
        result = await interview_analyses_collection.delete_one({
            "_id": ObjectId(analysis_id),
            "user_id": current_user["id"],
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Analysis not found")


@router.post("/retry/{analysis_id}")
async def retry_analysis(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Retry a failed analysis with the current API key."""
    try:
        doc = await interview_analyses_collection.find_one({
            "_id": ObjectId(analysis_id),
            "user_id": current_user["id"],
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if doc.get("status") not in ("failed", "error"):
        raise HTTPException(status_code=400, detail=f"Analysis status is '{doc.get('status')}', not 'failed'. Cannot retry.")

    # Reset status to processing
    await interview_analyses_collection.update_one(
        {"_id": ObjectId(analysis_id)},
        {"$set": {
            "status": "processing",
            "error": None,
            "parsed_transcript": None,
            "competency_analysis": None,
            "interviewer_report": None,
            "candidate_report": None,
            "interviewer_quality": None,
            "overall_score": None,
            "verdict": None,
        }}
    )

    # Get position for JD text
    position = await positions_collection.find_one({"_id": ObjectId(doc["position_id"])})
    jd_text = _build_jd_text(position) if position else ""

    # Re-trigger analysis
    background_tasks.add_task(
        _run_analysis_bg,
        analysis_id=analysis_id,
        transcript=doc.get("transcript", ""),
        jd_text=jd_text,
        role_title=doc.get("position_title", "Unknown"),
        candidate_name=doc.get("candidate_name", "Unknown"),
        duration_seconds=doc.get("duration_seconds", 0),
    )

    print(f"🔄 [InterviewIQ] Retrying analysis {analysis_id} for {doc.get('candidate_name')}")

    return {
        "id": analysis_id,
        "status": "processing",
        "message": "Analysis retry started.",
    }


@router.post("/{analysis_id}/send-report")
async def send_analysis_report(
    analysis_id: str,
    payload: SendReportRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate and send PDF report via email using Resend."""
    try:
        doc = await interview_analyses_collection.find_one({
            "_id": ObjectId(analysis_id),
            "user_id": current_user["id"],
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")

    pdf_base64 = payload.pdf_base64
    if pdf_base64.startswith("data:application/pdf;base64,"):
        pdf_base64 = pdf_base64.split("data:application/pdf;base64,")[1]

    try:
        send_interview_report_email(
            to_email=payload.to_email,
            subject=payload.subject,
            message_body=payload.message_body,
            candidate_name=doc.get("candidate_name", "Candidate"),
            position_title=doc.get("position_title", "Position"),
            sender_name=payload.sender_name,
            sender_email=payload.sender_email,
            company_name=payload.company_name,
            pdf_base64=pdf_base64
        )
        return {"message": "Report sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

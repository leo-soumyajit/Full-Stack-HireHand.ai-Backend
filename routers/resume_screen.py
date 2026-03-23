"""
AI Resume Screening Router — EOS-IA Talent Intelligence
POST /positions/{position_id}/screen-resume
Accepts base64-encoded PDF (JSON body), extracts text with pdfplumber,
analyzes vs JD with LLM, optionally auto-creates the candidate.

Why base64 JSON instead of multipart? Chrome blocks multipart POST cross-port
(localhost:8080→localhost:8000) on Windows. JSON body works fine like all other endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime
import io, base64

from core.deps import get_current_user
from core.openrouter import analyze_resume
from database import positions_collection, candidates_collection
from models.resume_screen import ResumeAnalysis, ResumeScreenResponse

router = APIRouter()


class ResumeUploadRequest(BaseModel):
    file_base64: str      # base64-encoded PDF bytes
    filename: str = "resume.pdf"
    auto_add: bool = True


def _get_user_id(user: dict) -> str:
    return user.get("id") or str(user.get("_id", ""))


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(pages).strip()
            return text
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract text from PDF: {str(e)}"
        )


def _verdict_to_stage(verdict: str) -> str:
    mapping = {
        "STRONG FIT": "Screened",
        "POTENTIAL FIT": "Screened",
        "WEAK FIT": "Screened",
        "NOT SUITABLE": "Rejected",
    }
    return mapping.get(verdict, "Sourced")


@router.post(
    "/positions/{position_id}/screen-resume",
    status_code=status.HTTP_201_CREATED,
)
async def screen_resume(
    position_id: str,
    payload: ResumeUploadRequest,
    user=Depends(get_current_user),
):
    """
    Accepts base64-encoded PDF → decodes → extracts text → AI analyzes vs JD → auto-creates candidate.
    """
    user_id = _get_user_id(user)

    # ── Validate + decode base64 ──────────────────────────────────────────
    if not payload.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    try:
        file_bytes = base64.b64decode(payload.file_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 file data.")

    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF file size must be under 10 MB.")

    # ── Extract text ──────────────────────────────────────────────────────
    resume_text = _extract_pdf_text(file_bytes)
    if len(resume_text.strip()) < 50:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from the PDF. Ensure it is not a scanned image."
        )

    # ── Fetch position + JD ───────────────────────────────────────────────

    pos = await positions_collection.find_one(
        {"_id": ObjectId(position_id), "user_id": user_id}
    )
    if not pos:
        # Fallback without user_id for flexibility
        pos = await positions_collection.find_one({"_id": ObjectId(position_id)})
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found.")

    jd = pos.get("jd") or {}
    if not jd:
        raise HTTPException(
            status_code=400,
            detail="Position must have a saved JD before screening resumes."
        )

    # ── Call LLM ──────────────────────────────────────────────────────────
    try:
        analysis_data = await analyze_resume(
            resume_text=resume_text,
            jd_purpose=jd.get("purpose", ""),
            jd_responsibilities=jd.get("responsibilities", []),
            jd_experience=jd.get("experience", []),
            role_title=pos["title"],
            level=pos.get("level", "Mid"),
            business_unit=pos.get("business_unit", "General"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)}")

    # ── Clamp/validate score ──────────────────────────────────────────────
    analysis_data["resume_score"] = round(
        max(0.0, min(10.0, float(analysis_data.get("resume_score", 5.0)))), 1
    )
    analysis_data["jd_match_percent"] = int(
        max(0, min(100, analysis_data.get("jd_match_percent", 50)))
    )

    analysis = ResumeAnalysis(**analysis_data)
    candidate_id = None

    # ── Auto-create candidate ─────────────────────────────────────────────
    if payload.auto_add:
        resume_score = analysis.resume_score
        jd_match = analysis.jd_match_percent
        composite = int(jd_match * 0.7 + resume_score * 3)

        verdict_map = {
            "STRONG FIT": "Go",
            "POTENTIAL FIT": "Conditional",
            "WEAK FIT": "Conditional",
            "NOT SUITABLE": "No-Go",
        }

        candidate_doc = {
            "position_id": position_id,
            "user_id": user_id,
            "name": analysis.candidate_name,
            "role": analysis.candidate_current_role or "Not specified",
            "email": analysis.candidate_email or "",
            "stage": "Rejected" if analysis.recommended_stage == "Rejected" else "Screened",
            "scores": {
                "resume": resume_score,
                "psych": 0.0,
                "composite": composite,
            },
            "verdict": verdict_map.get(analysis.verdict, "Conditional"),
            "resume_analysis": analysis_data,
            "added_via": "resume_screen",
            "created_at": datetime.utcnow().isoformat(),
        }

        result = await candidates_collection.insert_one(candidate_doc)
        candidate_id = str(result.inserted_id)

        # Increment candidates_count for the position
        await positions_collection.update_one(
            {"_id": ObjectId(position_id)},
            {"$inc": {"candidates_count": 1}}
        )

        # Save resume to disk
        try:
            import os
            os.makedirs("uploads/resumes", exist_ok=True)
            with open(f"uploads/resumes/{candidate_id}.pdf", "wb") as f:
                f.write(file_bytes)
        except Exception as e:
            print(f"Warning: Could not save resume PDF to disk: {e}")

    return {
        "analysis": analysis.model_dump(),
        "candidate_id": candidate_id,
        "position_id": position_id,
        "raw_text_length": len(resume_text),
    }


@router.get("/positions/{position_id}/screened-resumes")
async def get_screened_candidates(position_id: str, user=Depends(get_current_user)):
    """Return all candidates that were added via resume screening, sorted by score."""
    user_id = _get_user_id(user)
    cursor = candidates_collection.find(
        {"position_id": position_id, "user_id": user_id, "added_via": "resume_screen"}
    ).sort("scores.resume", -1)
    candidates = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        candidates.append(doc)
    return candidates

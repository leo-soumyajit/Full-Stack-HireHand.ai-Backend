"""
HireHand AI Interview Router
═══════════════════════════════════════════════════════
Handles dispatching, validation, and the real-time WebSocket
for autonomous AI-conducted interviews.

100% ISOLATED — Does NOT modify any existing router or file.
Reuses the existing interview_intelligence analysis pipeline for scoring.
"""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from bson import ObjectId
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
import uuid
import os
import asyncio
import time

from database import (
    ai_interview_sessions_collection,
    candidates_collection,
    positions_collection,
    interview_analyses_collection,
    schedules_collection,
)
from core.deps import get_current_user
from core.ai_interviewer import AIInterviewSession
from core.ai_tts import stream_tts_to_client, get_voice_model
from core.resend_email import send_ai_interview_email

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _build_jd_text(position: dict) -> str:
    """Extract JD text from position document for AI context."""
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
    if jd.get("skills"):
        parts.append("Skills:\n" + "\n".join(f"- {s}" for s in jd["skills"][:8]))
    return "\n\n".join(parts) if parts else f"Role: {position.get('title', 'Unknown')}"


# ══════════════════════════════════════════════════════════════════════
# ENDPOINT 1: DISPATCH AI INTERVIEW
# ══════════════════════════════════════════════════════════════════════

class DispatchAIInterviewRequest(BaseModel):
    candidate_id: str
    position_id: str
    round: int = 1
    interview_type: str = "hybrid"   # technical | behavioral | managerial | culture_fit | hybrid
    max_questions: int = 10
    time_limit_minutes: int = 20
    voice: str = "asteria"           # HR-selected voice


@router.post("/dispatch")
async def dispatch_ai_interview(
    body: DispatchAIInterviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Dispatch an AI interview to a candidate.
    Creates a session with a magic token and sends an email invitation.
    """
    # 1. Validate candidate and position exist
    try:
        cand_oid = ObjectId(body.candidate_id)
        pos_oid = ObjectId(body.position_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    candidate = await candidates_collection.find_one({"_id": cand_oid})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    position = await positions_collection.find_one({"_id": pos_oid})
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # 2. Check for existing active session
    existing = await ai_interview_sessions_collection.find_one({
        "candidate_id": body.candidate_id,
        "position_id": body.position_id,
        "round": body.round,
        "status": {"$in": ["pending", "in_progress"]},
    })
    if existing:
        return {
            "message": "AI interview already dispatched for this round",
            "token": existing["token"],
            "status": existing["status"],
        }

    # 3. Create session document
    magic_token = str(uuid.uuid4())
    expiration = datetime.now(timezone.utc) + timedelta(days=7)

    # Resolve voice model
    voice_model = get_voice_model(body.voice)

    session_doc = {
        "token": magic_token,
        "candidate_id": body.candidate_id,
        "position_id": body.position_id,
        "user_id": current_user["id"],
        "round": body.round,
        "interview_type": body.interview_type,
        "max_questions": body.max_questions,
        "time_limit_minutes": body.time_limit_minutes,
        "voice": voice_model,
        "voice_key": body.voice,
        "status": "pending",  # pending → in_progress → completed → analyzed
        "expires_at": expiration.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "duration_seconds": 0,
        "question_count": 0,
        "transcript": None,
        "transcript_entries": [],
        "tab_switch_count": 0,
        "analysis_id": None,
    }

    await ai_interview_sessions_collection.insert_one(session_doc)

    # 4. Send email to candidate
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip("/")
    interview_url = f"{frontend_url}/ai-interview/{magic_token}"

    try:
        send_ai_interview_email(
            to_email=candidate.get("email"),
            candidate_name=candidate.get("name", "Candidate"),
            position_title=position.get("title", "Position"),
            company_name=current_user.get("company_name", ""),
            interview_url=interview_url,
            interview_type=body.interview_type,
            time_limit=body.time_limit_minutes,
        )
    except Exception as e:
        print(f"⚠️ [AI-Interview] Email send failed: {e}")
        # Don't fail the dispatch — candidate can still use the link

    # 5. Update candidate stage
    await candidates_collection.update_one(
        {"_id": cand_oid},
        {"$set": {"stage": f"AI Interview L{body.round} Pending"}}
    )

    print(f"🤖 [AI-Interview] Dispatched for {candidate.get('name')} — {position.get('title')} (Round {body.round})")

    return {
        "message": "AI Interview dispatched successfully",
        "token": magic_token,
        "url": interview_url,
    }


# ══════════════════════════════════════════════════════════════════════
# ENDPOINT 2: LIST VOICES (for HR dropdown)
# ══════════════════════════════════════════════════════════════════════
# ⚠️ MUST be defined BEFORE /{token} routes to prevent route shadowing

@router.get("/voices/list")
async def list_available_voices():
    """Return available TTS voices for HR to choose from."""
    return {
        "voices": [
            {"key": "asteria", "name": "Asteria", "description": "Professional Female", "model": "aura-2-asteria-en"},
            {"key": "luna", "name": "Luna", "description": "Warm Female", "model": "aura-2-luna-en"},
            {"key": "stella", "name": "Stella", "description": "Clear Female", "model": "aura-2-stella-en"},
            {"key": "orion", "name": "Orion", "description": "Professional Male", "model": "aura-2-orion-en"},
            {"key": "arcas", "name": "Arcas", "description": "Warm Male", "model": "aura-2-arcas-en"},
        ]
    }


# ══════════════════════════════════════════════════════════════════════
# ENDPOINT 3: VALIDATE TOKEN (Candidate Pre-Join)
# ══════════════════════════════════════════════════════════════════════

@router.get("/{token}")
async def get_ai_interview_info(token: str):
    """
    Public endpoint — candidate uses this to get interview details before joining.
    Returns position, company info, and interview config.
    """
    session = await ai_interview_sessions_collection.find_one({"token": token})
    if not session:
        raise HTTPException(status_code=404, detail="Invalid interview link")

    if session.get("status") == "completed":
        raise HTTPException(status_code=400, detail="This interview has already been completed")

    if session.get("status") == "analyzed":
        raise HTTPException(status_code=400, detail="This interview has already been completed and evaluated")

    # Check expiry
    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Interview link has expired")

    # Get position and candidate info
    try:
        position = await positions_collection.find_one({"_id": ObjectId(session["position_id"])})
        candidate = await candidates_collection.find_one({"_id": ObjectId(session["candidate_id"])})
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load interview data")

    # Get company info from the user who dispatched
    from database import user_collection
    user = await user_collection.find_one({"_id": ObjectId(session.get("user_id", session.get("candidate_id")))})

    return {
        "candidate_name": candidate.get("name", "Candidate") if candidate else "Candidate",
        "position_title": position.get("title", "Position") if position else "Position",
        "company_name": user.get("company_name", "") if user else "",
        "company_logo": user.get("company_logo") if user else None,
        "time_limit_minutes": session.get("time_limit_minutes", 20),
        "max_questions": session.get("max_questions", 10),
        "round": session.get("round", 1),
        "interview_type": session.get("interview_type", "hybrid"),
        "status": session.get("status", "pending"),
    }


# ══════════════════════════════════════════════════════════════════════
# ENDPOINT 4: CHECK STATUS (HR Dashboard)
# ══════════════════════════════════════════════════════════════════════

@router.get("/{token}/status")
async def get_ai_interview_status(token: str, current_user: dict = Depends(get_current_user)):
    """HR checks if candidate has completed the AI interview."""
    session = await ai_interview_sessions_collection.find_one({"token": token})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": session.get("status"),
        "started_at": session.get("started_at"),
        "completed_at": session.get("completed_at"),
        "duration_seconds": session.get("duration_seconds", 0),
        "question_count": session.get("question_count", 0),
        "analysis_id": session.get("analysis_id"),
    }


# ══════════════════════════════════════════════════════════════════════
# ENDPOINT 5: WEBSOCKET — THE LIVE AI INTERVIEW
# ══════════════════════════════════════════════════════════════════════

async def _run_post_interview_analysis(session_id: str, session: dict, transcript: str):
    """
    Background task: Run the EXISTING interview intelligence analysis pipeline
    on the AI interview transcript. 100% reuses run_full_analysis_pipeline().
    """
    from core.interview_intelligence import run_full_analysis_pipeline

    try:
        # Get position for JD text
        position = await positions_collection.find_one({"_id": ObjectId(session["position_id"])})
        candidate = await candidates_collection.find_one({"_id": ObjectId(session["candidate_id"])})

        if not position or not candidate:
            raise ValueError("Position or candidate not found for analysis")

        jd_text = _build_jd_text(position)

        # Run the exact same 3-chain pipeline used for manual interviews
        result = await run_full_analysis_pipeline(
            transcript=transcript,
            jd_text=jd_text,
            role_title=position.get("title", "Unknown"),
            candidate_name=candidate.get("name", "Unknown"),
            duration_seconds=session.get("duration_seconds", 0),
        )

        # Extract top-level scores
        ir = result.get("interviewer_report", {})
        overall_score = ir.get("role_fit_score", None)
        verdict = ir.get("verdict", None)

        # Save analysis to the SAME collection used by manual interviews
        analysis_doc = {
            "schedule_id": f"ai-{session_id}",  # Prefix to distinguish from manual
            "position_id": session["position_id"],
            "candidate_id": session["candidate_id"],
            "user_id": session["user_id"],
            "candidate_name": candidate.get("name", "Unknown"),
            "position_title": position.get("title", "Unknown"),
            "transcript": transcript,
            "duration_seconds": session.get("duration_seconds", 0),
            "tab_switch_count": session.get("tab_switch_count", 0),
            "interview_round": session.get("round", 1),
            "interview_mode": "ai",  # 🤖 This distinguishes AI from manual
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "parsed_transcript": result.get("parsed_transcript", {}),
            "competency_analysis": result.get("competency_analysis", {}),
            "interviewer_report": ir,
            "candidate_report": result.get("candidate_report", {}),
            "interviewer_quality": result.get("interviewer_quality", {}),
            "overall_score": overall_score,
            "verdict": verdict,
            "error": None,
        }

        insert_result = await interview_analyses_collection.insert_one(analysis_doc)
        analysis_id = str(insert_result.inserted_id)

        # Update session with analysis reference
        await ai_interview_sessions_collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"status": "analyzed", "analysis_id": analysis_id}}
        )

        # Update candidate stage and scores
        update_fields = {"stage": f"AI Interview L{session.get('round', 1)} Completed"}
        if overall_score is not None:
            update_fields["verdict"] = verdict
            # Update composite score
            update_fields["scores.interview"] = overall_score / 10.0 if overall_score else 0

        await candidates_collection.update_one(
            {"_id": ObjectId(session["candidate_id"])},
            {"$set": update_fields}
        )

        print(f"✅ [AI-Interview] Analysis complete for session {session_id} — Score: {overall_score}, Verdict: {verdict}")

    except Exception as e:
        print(f"❌ [AI-Interview] Analysis failed for session {session_id}: {str(e)}")
        await ai_interview_sessions_collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"status": "completed", "analysis_error": str(e)}}
        )


@router.websocket("/{token}/ws")
async def ai_interview_websocket(websocket: WebSocket, token: str):
    """
    The live AI interview WebSocket.
    
    Client messages:
        {"type": "ready"}                          — Candidate is ready to start
        {"type": "candidate_speech", "text": "..."}  — Final transcript of candidate's speech
        {"type": "speech_interim", "text": "..."}    — Interim speech (for UI display)
        {"type": "tab_switch"}                       — Candidate switched tabs
        {"type": "end"}                              — Candidate wants to end early
    
    Server messages:
        {"type": "ai_audio", "data": "<base64 mp3>"}  — Audio chunk for playback
        {"type": "ai_text", "text": "..."}             — AI's text (for transcript display)
        {"type": "state", "state": "..."}              — State change notification
        {"type": "progress", "current": N, "total": M} — Question progress
        {"type": "interview_complete", "duration": N}  — Interview ended
        {"type": "error", "message": "..."}            — Error message
    """
    await websocket.accept()

    # 1. Validate session
    session = await ai_interview_sessions_collection.find_one({"token": token})
    if not session:
        await websocket.send_json({"type": "error", "message": "Invalid interview token"})
        await websocket.close()
        return

    if session.get("status") in ("completed", "analyzed"):
        await websocket.send_json({"type": "error", "message": "This interview has already been completed"})
        await websocket.close()
        return

    session_id = str(session["_id"])

    # 2. Load position, candidate, and user info
    try:
        position = await positions_collection.find_one({"_id": ObjectId(session["position_id"])})
        candidate = await candidates_collection.find_one({"_id": ObjectId(session["candidate_id"])})
    except Exception:
        await websocket.send_json({"type": "error", "message": "Failed to load interview data"})
        await websocket.close()
        return

    if not position or not candidate:
        await websocket.send_json({"type": "error", "message": "Position or candidate not found"})
        await websocket.close()
        return

    # Get company name
    from database import user_collection
    user = await user_collection.find_one({"_id": ObjectId(session.get("user_id", ""))})
    company_name = user.get("company_name", "the company") if user else "the company"

    # 3. Build AI session
    jd_text = _build_jd_text(position)
    l1_questions = position.get("l1_questions", [])
    # Extract question text if they're objects
    if l1_questions and isinstance(l1_questions[0], dict):
        l1_questions = [q.get("question", q.get("text", "")) for q in l1_questions if isinstance(q, dict)]

    ai_session = AIInterviewSession(
        company_name=company_name,
        position_title=position.get("title", "Unknown"),
        candidate_name=candidate.get("name", "Candidate"),
        jd_text=jd_text,
        interview_type=session.get("interview_type", "hybrid"),
        max_questions=session.get("max_questions", 10),
        time_limit_minutes=session.get("time_limit_minutes", 20),
        l1_questions=l1_questions,
        focus_areas=session.get("focus_areas", []),
        round_number=session.get("round", 1),
    )

    voice = session.get("voice", "aura-2-en-US-asteria")
    tab_switch_count = 0
    start_time = None

    # Helper: send audio chunk to client
    async def send_audio(audio_b64: str):
        try:
            await websocket.send_json({"type": "ai_audio", "data": audio_b64})
        except Exception:
            pass

    # Helper: send state to client
    async def send_state(state: str):
        try:
            await websocket.send_json({"type": "state", "state": state})
        except Exception:
            pass

    # 4. Mark session as in_progress
    await ai_interview_sessions_collection.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {
            "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    # Update candidate stage
    await candidates_collection.update_one(
        {"_id": ObjectId(session["candidate_id"])},
        {"$set": {"stage": f"AI Interview L{session.get('round', 1)} In Progress"}}
    )

    try:
        # 5. Wait for client "ready" signal
        while True:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=120)
            if data.get("type") == "ready":
                break

        start_time = time.time()

        # 6. Generate and speak greeting
        await send_state("thinking")
        greeting = await ai_session.generate_greeting()

        await websocket.send_json({"type": "ai_text", "text": greeting})
        await websocket.send_json({"type": "progress", "current": 1, "total": ai_session.max_questions})

        # Stream TTS
        await stream_tts_to_client(greeting, send_audio, send_state, voice)

        # 7. Main interview loop
        time_limit_seconds = session.get("time_limit_minutes", 20) * 60

        while not ai_session.is_complete:
            # Check time limit
            elapsed = time.time() - start_time
            if elapsed >= time_limit_seconds:
                # Time's up — force end
                await send_state("thinking")
                closing = await ai_session.force_end()
                await websocket.send_json({"type": "ai_text", "text": closing})
                await stream_tts_to_client(closing, send_audio, send_state, voice)
                break

            # Wait for candidate speech
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=time_limit_seconds - elapsed + 30  # Extra buffer
                )
            except asyncio.TimeoutError:
                # Candidate stopped talking for too long
                await send_state("thinking")
                closing = await ai_session.force_end()
                await websocket.send_json({"type": "ai_text", "text": closing})
                await stream_tts_to_client(closing, send_audio, send_state, voice)
                break

            msg_type = data.get("type", "")

            if msg_type == "candidate_speech":
                # Process the candidate's answer
                candidate_text = data.get("text", "").strip()
                if not candidate_text:
                    continue

                await send_state("thinking")
                response = await ai_session.process_candidate_answer(candidate_text)

                if response:
                    await websocket.send_json({"type": "ai_text", "text": response})
                    await websocket.send_json({
                        "type": "progress",
                        "current": ai_session.question_count,
                        "total": ai_session.max_questions,
                    })

                    # Stream TTS
                    await stream_tts_to_client(response, send_audio, send_state, voice)

            elif msg_type == "tab_switch":
                tab_switch_count += 1

            elif msg_type == "end":
                # Candidate wants to end early
                await send_state("thinking")
                closing = await ai_session.force_end()
                await websocket.send_json({"type": "ai_text", "text": closing})
                await stream_tts_to_client(closing, send_audio, send_state, voice)
                break

            elif msg_type == "speech_interim":
                # Just for display — ignore for processing
                pass

        # 8. Interview complete
        duration = int(time.time() - start_time) if start_time else 0
        transcript = ai_session.get_formatted_transcript()

        await websocket.send_json({
            "type": "interview_complete",
            "duration": duration,
        })

        # 9. Save session results
        await ai_interview_sessions_collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "question_count": ai_session.question_count,
                "transcript": transcript,
                "transcript_entries": ai_session.get_transcript_entries(),
                "tab_switch_count": tab_switch_count,
            }}
        )

        # 10. Trigger analysis in background
        # Fetch fresh session data
        updated_session = await ai_interview_sessions_collection.find_one({"_id": ObjectId(session_id)})
        if updated_session:
            asyncio.create_task(
                _run_post_interview_analysis(session_id, updated_session, transcript)
            )

        print(f"🤖 [AI-Interview] Session {session_id} completed — {duration}s, {ai_session.question_count} questions")

    except WebSocketDisconnect:
        # Candidate disconnected
        duration = int(time.time() - start_time) if start_time else 0
        transcript = ai_session.get_formatted_transcript()

        if ai_session.question_count >= 3 and transcript:
            # Enough data to analyze — save and score
            await ai_interview_sessions_collection.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": duration,
                    "question_count": ai_session.question_count,
                    "transcript": transcript,
                    "transcript_entries": ai_session.get_transcript_entries(),
                    "tab_switch_count": tab_switch_count,
                    "disconnected": True,
                }}
            )
            # Still trigger analysis
            updated_session = await ai_interview_sessions_collection.find_one({"_id": ObjectId(session_id)})
            if updated_session:
                asyncio.create_task(
                    _run_post_interview_analysis(session_id, updated_session, transcript)
                )
        else:
            # Not enough data — mark as pending for retry
            await ai_interview_sessions_collection.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {"status": "pending"}}
            )

        print(f"🔌 [AI-Interview] Candidate disconnected from session {session_id} after {duration}s")

    except Exception as e:
        print(f"❌ [AI-Interview] WebSocket error in session {session_id}: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": "An error occurred. Please try again."})
        except Exception:
            pass


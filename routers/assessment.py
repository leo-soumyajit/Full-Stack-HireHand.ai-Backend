from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from bson import ObjectId
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

from database import (
    assessment_tests_collection,
    assessment_links_collection,
    assessment_submissions_collection,
    psychometric_reports_collection,
    candidates_collection,
    positions_collection,
)
from models.psychometric import (
    AssessmentTest,
    AssessmentLink,
    AssessmentSubmission,
    QuestionResponse,
    FitmentReport
)
from core.openrouter import (
    generate_psychometric_mcq_test,
    analyze_psychometric_mcq_submission
)
from core.resend_email import send_assessment_email
from core.deps import get_current_user

router = APIRouter()

class GenerateAssessmentRequest(BaseModel):
    position_id: str
    time_limit_minutes: int
    num_questions: int
    question_type: str = "Scenario"  # Scenario | Conventional | Math & Aptitude | Behavioral | Hybrid
    distribution: Dict[str, int] = None  # For Hybrid: {"scenario": 3, "behavioral": 3, ...}

@router.post("/generate")
async def generate_assessment(req: GenerateAssessmentRequest, current_user: dict = Depends(get_current_user)):
    try:
        pos_oid = ObjectId(req.position_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid position ID format")
        
    position = await positions_collection.find_one({"_id": pos_oid})
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
        
    jd = position.get("jd")
    if not jd or not jd.get("responsibilities"):
        raise HTTPException(status_code=400, detail="Position must have a valid Job Description first")

    # Clear any previous test first
    await assessment_tests_collection.delete_many({"position_id": req.position_id})
    
    jd_text_blocks = [
        position.get('title', ''), jd.get('purpose', ''),
        *jd.get('responsibilities', []), *jd.get('skills', [])
    ]
    jd_text = "\n".join(filter(None, jd_text_blocks))
    
    # Call AI to generate test
    try:
        raw_test_data = await generate_psychometric_mcq_test(
            jd_text=jd_text,
            role_title=position.get('title', 'Unknown Role'),
            level=position.get('level', 'Mid'),
            business_unit=position.get('business_unit', 'General'),
            num_questions=req.num_questions,
            question_type=req.question_type,
            distribution=req.distribution
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail="AI generation failed. Please try again.")
    
    # Sanitize AI output in case it messes up the schema
    for q in raw_test_data.get("questions", []):
        # Fallback: AI sometimes renames 'scenario' to 'question' or 'text' for math/logic questions
        if "scenario" not in q:
            q["scenario"] = q.get("question") or q.get("text") or "Question text missing due to AI formatting error."
            
        raw_options = q.get("options", [])
        sanitized_opts = []
        for i, opt in enumerate(raw_options):
            if isinstance(opt, str):
                # AI returned a string instead of a dict
                sanitized_opts.append({"id": ["A", "B", "C", "D"][i] if i < 4 else f"Opt-{i}", "text": opt})
            elif isinstance(opt, dict):
                if "text" not in opt and "id" in opt and len(opt["id"]) > 3:
                    # LLM accidentally put the option text in the "id" field
                    opt["text"] = opt["id"]
                    opt["id"] = ["A", "B", "C", "D"][i] if i < 4 else f"Opt-{i}"
                if "id" not in opt:
                    opt["id"] = ["A", "B", "C", "D"][i] if i < 4 else f"Opt-{i}"
                if "text" not in opt:
                    opt["text"] = "Option text missing due to AI error."
                sanitized_opts.append(opt)
            else:
                sanitized_opts.append({"id": ["A", "B", "C", "D"][i] if i < 4 else f"Opt-{i}", "text": "Invalid option format"})
        q["options"] = sanitized_opts
                
    new_test = AssessmentTest(
        position_id=req.position_id,
        role_title=position.get('title', 'Unknown Role'),
        time_limit_minutes=req.time_limit_minutes,
        questions=raw_test_data.get("questions", [])
    )
    
    await assessment_tests_collection.insert_one(new_test.model_dump())
    return {"message": "Assessment generated successfully"}

@router.get("/position/{position_id}")
async def get_position_assessment(position_id: str):
    test_doc = await assessment_tests_collection.find_one({"position_id": position_id}, {"_id": 0})
    if not test_doc:
        raise HTTPException(status_code=404, detail="Test not found")
    return test_doc

@router.delete("/position/{position_id}")
async def clear_position_assessment(position_id: str):
    res = await assessment_tests_collection.delete_many({"position_id": position_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Test not found")
    # Also invalidate outstanding links? (Optional, skipping for now)
    return {"message": "Assessment cleared"}

class UpdateQuestionRequest(BaseModel):
    scenario: str
    options: List[dict]

@router.patch("/position/{position_id}/questions/{question_id}")
async def update_question(position_id: str, question_id: str, req: UpdateQuestionRequest):
    test_doc = await assessment_tests_collection.find_one({"position_id": position_id})
    if not test_doc:
        raise HTTPException(status_code=404, detail="Test not found")
    
    questions = test_doc.get("questions", [])
    for q in questions:
        if q["id"] == question_id:
            q["scenario"] = req.scenario
            q["options"] = req.options
            await assessment_tests_collection.update_one(
                {"position_id": position_id},
                {"$set": {"questions": questions}}
            )
            return {"message": "Question updated"}
            
    raise HTTPException(status_code=404, detail="Question not found")

@router.delete("/position/{position_id}/questions/{question_id}")
async def delete_question(position_id: str, question_id: str):
    test_doc = await assessment_tests_collection.find_one({"position_id": position_id})
    if not test_doc:
        raise HTTPException(status_code=404, detail="Test not found")
    
    questions = test_doc.get("questions", [])
    new_questions = [q for q in questions if q["id"] != question_id]
    
    if len(questions) == len(new_questions):
         raise HTTPException(status_code=404, detail="Question not found")
         
    await assessment_tests_collection.update_one(
        {"position_id": position_id},
        {"$set": {"questions": new_questions}}
    )
    return {"message": "Question deleted"}

class SendAssessmentRequest(BaseModel):
    position_id: str
    candidate_id: str

@router.post("/send")
async def send_assessment(req: SendAssessmentRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    try:
        cand_oid = ObjectId(req.candidate_id)
        pos_oid = ObjectId(req.position_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    # 1. Validate Candidate & Test
    candidate = await candidates_collection.find_one({"_id": cand_oid})
    test_doc = await assessment_tests_collection.find_one({"position_id": req.position_id})
    position = await positions_collection.find_one({"_id": pos_oid})
    
    if not candidate or not test_doc:
        raise HTTPException(status_code=404, detail="Candidate or Generated Test not found")
    
    # 2. Generate Link Token
    magic_token = str(uuid.uuid4())
    expiration = datetime.now(timezone.utc) + timedelta(days=7) # link valid for 7 days
    
    # Invalidate previous uncompleted links for this candidate/position
    await assessment_links_collection.update_many(
        {"candidate_id": req.candidate_id, "position_id": req.position_id, "is_completed": False},
        {"$set": {"is_completed": True}} # Deactivate previous links
    )
    
    link_doc = AssessmentLink(
        token=magic_token,
        candidate_id=req.candidate_id,
        position_id=req.position_id,
        user_id=user_id,
        expires_at=expiration.isoformat()
    )
    await assessment_links_collection.insert_one(link_doc.model_dump())
    
    # 3. Send Real Email
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
    assessment_url = f"{frontend_url}/assessment/{magic_token}"
    
    send_assessment_email(
        to_email=candidate.get('email'),
        candidate_name=candidate.get('name'),
        position_title=position.get('title', 'Position'),
        assessment_url=assessment_url,
        time_limit=test_doc.get('time_limit_minutes', 15)
    )
    
    return {"message": "Assessment sent successfully", "url": assessment_url}

@router.get("/{token}")
async def get_assessment(token: str):
    link = await assessment_links_collection.find_one({"token": token})
    if not link:
        raise HTTPException(status_code=404, detail="Invalid token")
    if link.get("is_completed"):
        raise HTTPException(status_code=400, detail="Assessment already completed or expired")
        
    expires_at = datetime.fromisoformat(link["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
         raise HTTPException(status_code=400, detail="Assessment link expired")
    
    test = await assessment_tests_collection.find_one({"position_id": link["position_id"]})
    try:
        cand_oid = ObjectId(link["candidate_id"])
        pos_oid = ObjectId(link["position_id"])
    except:
        raise HTTPException(status_code=400, detail="Invalid link IDs")
        
    candidate = await candidates_collection.find_one({"_id": cand_oid})
    position = await positions_collection.find_one({"_id": pos_oid})
    
    if not test:
        raise HTTPException(status_code=404, detail="Test data missing")
        
    return {
        "candidate_name": candidate.get("name") if candidate else "Candidate",
        "role_title": test.get("role_title"),
        "company_name": position.get("business_unit", "Our Company") if position else "Our Company",
        "time_limit_minutes": test.get("time_limit_minutes", 15),
        "questions": test.get("questions", [])
    }

class SubmissionRequest(BaseModel):
    responses: List[QuestionResponse]
    total_time_spent_ms: int

async def trigger_background_ai_analysis(link: dict, submission_doc: AssessmentSubmission):
    """Background task to run AI analysis without keeping the HTTP connection open."""
    try:
        cand_oid = ObjectId(link["candidate_id"])
        pos_oid = ObjectId(link["position_id"])
    except:
        return
        
    position = await positions_collection.find_one({"_id": pos_oid})
    test = await assessment_tests_collection.find_one({"position_id": link["position_id"]})
    
    if position and test:
        jd = position.get("jd", {})
        jd_text_blocks = [
            position.get('title', ''), jd.get('purpose', ''),
            *jd.get('responsibilities', []), *jd.get('skills', [])
        ]
        jd_text = "\n".join(filter(None, jd_text_blocks))
        
        try:
            report_data = await analyze_psychometric_mcq_submission(
                jd_text=jd_text,
                role_title=position.get('title', 'Unknown Role'),
                test_data=test,
                submission_data=submission_doc.model_dump()
            )
            
            new_report = FitmentReport(
                candidate_id=link["candidate_id"],
                position_id=link["position_id"],
                user_id=link["user_id"],
                trait_matrix=report_data.get("trait_matrix", []),
                pattern_cluster=report_data.get("pattern_cluster", {}),
                risk=report_data.get("risk", {}),
                verdict=report_data.get("verdict", {}),
                composite_psych_score=report_data.get("composite_psych_score", 0)
            )
            
            await psychometric_reports_collection.update_one(
                {"candidate_id": link["candidate_id"], "position_id": link["position_id"]},
                {"$set": new_report.model_dump()},
                upsert=True
            )
            
            # Store score directly on candidate for list view
            await candidates_collection.update_one(
                {"_id": cand_oid},
                {"$set": {"scores.psych": new_report.composite_psych_score / 10.0}}
            )
        except Exception as e:
            print(f"Background AI evaluation failed: {e}")

@router.post("/{token}/submit")
async def submit_assessment(token: str, req: SubmissionRequest, background_tasks: BackgroundTasks):
    link = await assessment_links_collection.find_one({"token": token})
    if not link:
        raise HTTPException(status_code=404, detail="Invalid token")
    if link.get("is_completed"):
        raise HTTPException(status_code=400, detail="Assessment already completed")
        
    # Mark link as completed
    await assessment_links_collection.update_one({"token": token}, {"$set": {"is_completed": True}})
    
    submission_doc = AssessmentSubmission(
        candidate_id=link["candidate_id"],
        position_id=link["position_id"],
        responses=req.responses,
        total_time_spent_ms=req.total_time_spent_ms
    )
    
    await assessment_submissions_collection.update_one(
        {"candidate_id": link["candidate_id"], "position_id": link["position_id"]},
        {"$set": submission_doc.model_dump()},
        upsert=True
    )
    
    # --- Trigger AI Fitment Analysis in Background ---
    background_tasks.add_task(trigger_background_ai_analysis, link, submission_doc)

    return {"message": "Assessment submitted successfully"}

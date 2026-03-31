from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from core.openrouter import (
    generate_jd_questions,
    enhance_partial_jd,
    enhance_full_jd,
    generate_structured_interview_questions
)

router = APIRouter()

# Input Models
class JDInputProps(BaseModel):
    job_description: str

class EnhancePartialJDProps(BaseModel):
    raw_jd: str
    existing_jd: Optional[Dict[str, Any]] = None

class EnhanceFullJDProps(BaseModel):
    raw_jd: str

class InterviewQuestionsProps(BaseModel):
    job_description: str
    role: str
    level: str
    category: str
    counts: Dict[str, int]  # e.g., {"easy": 1, "medium": 2, "hard": 1}
    existing_questions: Optional[List[Dict[str, Any]]] = None


@router.post("/generate-questions-from-jd")
async def generate_questions(req: JDInputProps):
    try:
        if not req.job_description.strip():
            raise HTTPException(status_code=400, detail="Job description is empty")
        
        result = await generate_jd_questions(req.job_description)
        # Should return array in {"questions": [...]}
        questions_array = result.get("questions", [])
        if not questions_array and isinstance(result, list):
            questions_array = result
            
        import time
        for i, q in enumerate(questions_array):
            if "id" not in q:
                q["id"] = f"gen-{int(time.time()*1000)}-{i}"
                
        return {"questions": questions_array}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="AI generation failed. Please try again.")

@router.post("/enhance-jd")
async def enhance_jd(req: EnhancePartialJDProps):
    try:
        if not req.raw_jd.strip():
            raise HTTPException(status_code=400, detail="Requested instruction is empty")
            
        result = await enhance_partial_jd(req.raw_jd, req.existing_jd)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="AI generation failed. Please try again.")

@router.post("/enhance-full-jd")
async def enhance_full_jd_route(req: EnhanceFullJDProps):
    try:
        if not req.raw_jd.strip():
            raise HTTPException(status_code=400, detail="Raw JD is empty")
            
        result = await enhance_full_jd(req.raw_jd)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="AI generation failed. Please try again.")

@router.post("/generate-interview")
async def generate_interview(req: InterviewQuestionsProps):
    try:
        easy = req.counts.get("easy", 0)
        medium = req.counts.get("medium", 0)
        hard = req.counts.get("hard", 0)
        
        result = await generate_structured_interview_questions(
            job_description=req.job_description,
            role=req.role,
            level=req.level,
            category=req.category,
            easy=easy,
            medium=medium,
            hard=hard,
            existing_questions=req.existing_questions
        )
        questions_array = result.get("questions", [])
        if not questions_array and isinstance(result, list):
            questions_array = result
            
        import time
        for i, q in enumerate(questions_array):
            if "id" not in q:
                cat_formatted = req.category.lower().replace(" ", "-")
                q["id"] = f"{req.level.lower()}-{cat_formatted}-{int(time.time()*1000)}-{i}"
            if "text" not in q:
                q["text"] = "Missing question text"
            if "category" not in q:
                q["category"] = req.category
            if "difficulty" not in q or q["difficulty"] not in ["Easy", "Medium", "Hard"]:
                q["difficulty"] = "Medium"
            q["level"] = req.level
            
        return {"questions": questions_array}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="AI generation failed. Please try again.")

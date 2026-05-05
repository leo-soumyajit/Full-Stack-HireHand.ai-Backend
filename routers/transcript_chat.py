"""
HireHand Insight AI — Transcript Chatbot API Router
═══════════════════════════════════════════════════════════════
100% ISOLATED — Does NOT modify any existing router or file.
Provides REST endpoints for HR to chat with a RAG-powered AI
about any candidate's interview performance.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.deps import get_current_user
from core.transcript_rag import ask_about_candidate

router = APIRouter()


# ── Request / Response Models ──────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AskRequest(BaseModel):
    question: str
    position_id: str
    chat_history: list[ChatMessage] = []


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    chunks_used: int


class SuggestedQuestion(BaseModel):
    text: str
    category: str


# ══════════════════════════════════════════════════════════════
# ENDPOINT 1: ASK QUESTION
# ══════════════════════════════════════════════════════════════

@router.post("/{candidate_id}/ask", response_model=AskResponse)
async def ask_question(
    candidate_id: str,
    body: AskRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    HR asks a question about a candidate's interview performance.
    Uses RAG pipeline: MongoDB → ChromaDB → GPT-4o-mini.
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(body.question) > 2000:
        raise HTTPException(status_code=400, detail="Question is too long (max 2000 chars)")

    # Convert chat_history to dict format
    history = [{"role": m.role, "content": m.content} for m in body.chat_history]

    result = await ask_about_candidate(
        candidate_id=candidate_id,
        position_id=body.position_id,
        question=body.question.strip(),
        chat_history=history,
    )

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        chunks_used=result["chunks_used"],
    )


# ══════════════════════════════════════════════════════════════
# ENDPOINT 2: GET SUGGESTED QUESTIONS
# ══════════════════════════════════════════════════════════════

@router.get("/{candidate_id}/suggestions")
async def get_suggestions(
    candidate_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns pre-built suggested questions for HR.
    These are smart contextual questions that HR commonly asks.
    """
    suggestions = [
        {"text": "What are this candidate's key strengths?", "category": "overview"},
        {"text": "What are the main areas of concern?", "category": "overview"},
        {"text": "How does this candidate match the job requirements?", "category": "fit"},
        {"text": "What projects or experience did they mention?", "category": "technical"},
        {"text": "How was their communication during the interview?", "category": "behavioral"},
        {"text": "Should I reconsider this candidate for a different role?", "category": "decision"},
        {"text": "What specific technical skills did they demonstrate?", "category": "technical"},
        {"text": "Summarize their entire interview performance.", "category": "overview"},
    ]

    return {"suggestions": suggestions}

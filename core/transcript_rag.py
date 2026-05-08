"""
HireHand Insight AI — RAG-Powered Transcript Chatbot Engine
═══════════════════════════════════════════════════════════════
100% ISOLATED — Does NOT modify any existing file.
Uses ChromaDB (in-memory) + sentence-transformers for embeddings,
and GPT-4o-mini (via OpenRouter) for intelligent answers.
"""

import os
import hashlib
import httpx
from typing import Optional

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    ChromaSettings = None

from bson import ObjectId
from database import (
    candidates_collection,
    positions_collection,
    interview_analyses_collection,
    ai_interview_sessions_collection,
)

# ── Config ──────────────────────────────────────────────────
CHATBOT_API_URL = os.getenv("CHATBOT_AI_API_URL", "https://openrouter.ai/api/v1/chat/completions")
CHATBOT_API_KEY = os.getenv("CHATBOT_AI_API_KEY", "")
CHATBOT_MODEL = os.getenv("CHATBOT_AI_MODEL", "openai/gpt-4o-mini")

# ── ChromaDB Client (in-memory, ephemeral) ──────────────────
_chroma_client = None

def _get_chroma():
    global _chroma_client
    if _chroma_client is None:
        if not CHROMA_AVAILABLE:
            return None
        _chroma_client = chromadb.EphemeralClient(
            settings=ChromaSettings(anonymized_telemetry=False)
        )
    return _chroma_client


# ══════════════════════════════════════════════════════════════
# 1. DATA GATHERING — Fetch all candidate context from MongoDB
# ══════════════════════════════════════════════════════════════

async def gather_candidate_context(candidate_id: str, position_id: str) -> dict:
    """
    Gather ALL available data for a candidate:
    - Candidate profile + resume analysis
    - Position JD
    - Manual interview analyses
    - AI interview transcripts
    """
    context = {
        "candidate": None,
        "position": None,
        "manual_interviews": [],
        "ai_interviews": [],
    }

    # Candidate
    try:
        cand = await candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if cand:
            cand["_id"] = str(cand["_id"])
            context["candidate"] = cand
    except Exception:
        pass

    # Position + JD
    try:
        pos = await positions_collection.find_one({"_id": ObjectId(position_id)})
        if pos:
            pos["_id"] = str(pos["_id"])
            context["position"] = pos
    except Exception:
        pass

    # Manual Interview Analyses
    try:
        cursor = interview_analyses_collection.find({"candidate_id": candidate_id})
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            context["manual_interviews"].append(doc)
    except Exception:
        pass

    # AI Interview Sessions (with transcripts)
    try:
        cursor = ai_interview_sessions_collection.find({"candidate_id": candidate_id})
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            context["ai_interviews"].append(doc)
    except Exception:
        pass

    return context


# ══════════════════════════════════════════════════════════════
# 2. TEXT EXTRACTION — Convert context to searchable text chunks
# ══════════════════════════════════════════════════════════════

def _extract_text_chunks(context: dict) -> list[dict]:
    """
    Convert gathered context into labeled text chunks for embedding.
    Each chunk has: {"text": "...", "source": "resume|jd|interview_L1|..."}
    """
    chunks = []

    # ── Candidate Resume ──
    cand = context.get("candidate")
    if cand:
        # Basic info
        basic = f"Candidate: {cand.get('name', 'Unknown')}, Email: {cand.get('email', '')}, Role: {cand.get('role', '')}."
        basic += f" Stage: {cand.get('stage', '')}, Verdict: {cand.get('verdict', '')}."
        chunks.append({"text": basic, "source": "candidate_profile"})

        # Resume analysis
        ra = cand.get("resume_analysis", {})
        if ra:
            if ra.get("strengths"):
                for i, s in enumerate(ra["strengths"]):
                    chunks.append({"text": f"Resume Strength: {s}", "source": "resume_strengths"})
            if ra.get("gaps"):
                for g in ra["gaps"]:
                    chunks.append({"text": f"Resume Weakness/Gap: {g}", "source": "resume_gaps"})
            if ra.get("verdict_rationale"):
                chunks.append({"text": f"AI Resume Verdict: {ra['verdict_rationale']}", "source": "resume_verdict"})
            if ra.get("skills"):
                chunks.append({"text": f"Candidate Skills: {', '.join(ra['skills'])}", "source": "resume_skills"})
            if ra.get("experience_summary"):
                chunks.append({"text": f"Experience Summary: {ra['experience_summary']}", "source": "resume_experience"})
            if ra.get("jd_match_percent"):
                chunks.append({"text": f"JD Match Percentage: {ra['jd_match_percent']}%", "source": "resume_jd_match"})

        # Scores
        scores = cand.get("scores", {})
        if scores:
            chunks.append({
                "text": f"Scores — Resume: {scores.get('resume', 0)}/10, Interview: {scores.get('interview', 0)}/10, Psychometric: {scores.get('psych', 0)}/10.",
                "source": "scores"
            })

    # ── Position JD ──
    pos = context.get("position")
    if pos:
        # The actual JD field in MongoDB is "jd" (not "jd_analysis" or "jd_structured")
        jd = pos.get("jd") or pos.get("jd_analysis") or pos.get("jd_structured") or {}
        chunks.append({"text": f"Position: {pos.get('title', '')}", "source": "position_title"})
        if isinstance(jd, dict):
            # Purpose / Summary
            if jd.get("purpose"):
                chunks.append({"text": f"JD Purpose: {jd['purpose']}", "source": "jd_purpose"})
            # Responsibilities
            if jd.get("responsibilities"):
                for r in jd["responsibilities"][:10]:
                    chunks.append({"text": f"JD Responsibility: {r}", "source": "jd_responsibilities"})
            # Education requirements
            if jd.get("education"):
                edu = jd["education"]
                if isinstance(edu, list):
                    for e in edu:
                        chunks.append({"text": f"JD Education Requirement: {e}", "source": "jd_education"})
                elif isinstance(edu, str):
                    chunks.append({"text": f"JD Education Requirement: {edu}", "source": "jd_education"})
            # Experience requirements
            if jd.get("experience"):
                exp = jd["experience"]
                if isinstance(exp, list):
                    for e in exp:
                        chunks.append({"text": f"JD Experience Requirement: {e}", "source": "jd_experience"})
                elif isinstance(exp, str):
                    chunks.append({"text": f"JD Experience Requirement: {exp}", "source": "jd_experience"})
            # Qualifications
            if jd.get("qualifications"):
                for q in jd["qualifications"][:6]:
                    chunks.append({"text": f"JD Qualification: {q}", "source": "jd_qualifications"})
            # Skills
            if jd.get("skills"):
                if isinstance(jd["skills"][0], str):
                    for s in jd["skills"][:10]:
                        chunks.append({"text": f"JD Required Skill: {s}", "source": "jd_skills"})
                else:
                    chunks.append({"text": f"JD Required Skills: {', '.join(str(s) for s in jd['skills'][:10])}", "source": "jd_skills"})

    # ── Manual Interview Analyses ──
    for analysis in context.get("manual_interviews", []):
        round_num = analysis.get("interview_round", "?")
        
        # Add date to label to distinguish multiple interviews in the same round
        date_str = ""
        if analysis.get("created_at"):
            ca = analysis["created_at"]
            date_str = f" ({str(ca)[:10]})"
            
        label = f"Manual Interview L{round_num}{date_str}"

        if analysis.get("executive_summary"):
            chunks.append({"text": f"[{label}] Executive Summary: {analysis['executive_summary']}", "source": label})

        if analysis.get("key_strengths"):
            for s in analysis["key_strengths"]:
                chunks.append({"text": f"[{label}] Strength: {s}", "source": label})

        if analysis.get("areas_of_concern"):
            for c in analysis["areas_of_concern"]:
                chunks.append({"text": f"[{label}] Concern: {c}", "source": label})

        if analysis.get("transcript"):
            # Split transcript into smaller chunks (~500 chars)
            transcript = analysis["transcript"]
            for i in range(0, len(transcript), 500):
                chunk_text = transcript[i:i+500]
                chunks.append({"text": f"[{label}] Transcript: {chunk_text}", "source": f"{label}_transcript"})

        # Scores
        ai_scores = analysis.get("ai_scores", {})
        if ai_scores:
            score_text = f"[{label}] Scores — Technical: {ai_scores.get('technical', 'N/A')}, Behavioral: {ai_scores.get('behavioral', 'N/A')}, Communication: {ai_scores.get('communication', 'N/A')}, Overall: {ai_scores.get('overall', 'N/A')}."
            chunks.append({"text": score_text, "source": f"{label}_scores"})

    # ── AI Interview Sessions ──
    for session in context.get("ai_interviews", []):
        round_num = session.get("round", "?")
        
        # Add date to label to distinguish multiple interviews in the same round
        date_str = ""
        if session.get("created_at"):
            ca = session["created_at"]
            date_str = f" ({str(ca)[:10]})"
            
        label = f"AI Interview L{round_num}{date_str}"

        # Transcript entries — group into ~500 char chunks to handle long interviews
        entries = session.get("transcript_entries", [])
        if entries:
            buffer = ""
            for entry in entries:
                speaker = entry.get("speaker", "Unknown")
                text = entry.get("text", "").strip()
                if not text:
                    continue
                line = f"{speaker}: {text}\n"
                if len(buffer) + len(line) > 500:
                    chunks.append({"text": f"[{label}] {buffer.strip()}", "source": f"{label}_transcript"})
                    buffer = line
                else:
                    buffer += line
            if buffer.strip():
                chunks.append({"text": f"[{label}] {buffer.strip()}", "source": f"{label}_transcript"})

        # Full transcript fallback
        if not entries and session.get("transcript"):
            transcript = session["transcript"]
            for i in range(0, len(transcript), 500):
                chunk_text = transcript[i:i+500]
                chunks.append({"text": f"[{label}] Transcript: {chunk_text}", "source": f"{label}_transcript"})

    return chunks


# ══════════════════════════════════════════════════════════════
# 3. VECTOR INDEX — Build / retrieve ChromaDB collection
# ══════════════════════════════════════════════════════════════

def _collection_name(candidate_id: str) -> str:
    """Generate a stable, short collection name for ChromaDB."""
    h = hashlib.md5(candidate_id.encode()).hexdigest()[:12]
    return f"cand_{h}"


def build_vector_index(candidate_id: str, chunks: list[dict]) -> Optional[object]:
    """
    Build an in-memory ChromaDB collection from text chunks.
    Uses a content hash to detect when data has changed (e.g., new L2 interview added)
    and automatically rebuilds the index.
    """
    client = _get_chroma()
    if client is None:
        return None

    coll_name = _collection_name(candidate_id)

    # Compute a hash of current data to detect changes
    data_hash = hashlib.md5("".join(c["text"] for c in chunks).encode()).hexdigest()

    # Check if cached collection is still valid
    try:
        collection = client.get_collection(coll_name)
        cached_hash = collection.metadata.get("data_hash", "")
        if collection.count() > 0 and cached_hash == data_hash:
            # Data hasn't changed, reuse cached index
            return collection
        else:
            # Data changed (new interview added etc.) — delete and rebuild
            client.delete_collection(coll_name)
    except Exception:
        pass

    if not chunks:
        return None

    collection = client.get_or_create_collection(
        name=coll_name,
        metadata={"hnsw:space": "cosine", "data_hash": data_hash},
    )

    # Add all chunks
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    documents = [c["text"] for c in chunks]
    metadatas = [{"source": c["source"]} for c in chunks]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return collection


def query_vector_index(candidate_id: str, query: str, n_results: int = 8) -> list[dict]:
    """
    Query the ChromaDB collection for a candidate.
    Returns top-N relevant chunks with their source labels.
    """
    client = _get_chroma()
    if client is None:
        return []

    coll_name = _collection_name(candidate_id)

    try:
        collection = client.get_collection(coll_name)
    except Exception:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
    )

    retrieved = []
    if results and results.get("documents"):
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            retrieved.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "relevance": round(1 - dist, 3),  # cosine similarity
            })

    return retrieved


# ══════════════════════════════════════════════════════════════
# 4. LLM ANSWER GENERATION — GPT-4o-mini via OpenRouter
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are HireHand Insight AI — a highly intelligent Candidate Intelligence Assistant for HR professionals.

You have access to a candidate's complete interview transcripts, resume analysis, AI scores, and the job description. Your job is to answer HR's questions about the candidate accurately and insightfully.

Rules:
1. Always base your answers on the provided evidence. If the evidence doesn't contain the answer, say so honestly.
2. When referencing specific information, mention which source it came from (e.g., "In their L1 interview...", "According to their resume...").
3. Be concise but thorough. Use bullet points when listing multiple items.
4. Provide actionable insights when asked for recommendations.
5. Never fabricate information. Only use what's in the provided context.
6. If asked about skills not mentioned in any data, clearly state "This was not discussed or found in the available data."
7. Be professional but conversational — you're helping an HR professional make decisions.
8. You may provide comparative analysis (e.g., how the candidate's skills match the JD requirements).

Remember: You are an AI assistant helping HR make informed hiring decisions based on real interview data."""


async def generate_answer(
    query: str,
    retrieved_chunks: list[dict],
    chat_history: list[dict],
    candidate_name: str = "the candidate",
) -> str:
    """
    Generate an intelligent answer using GPT-4o-mini based on retrieved context.
    """
    # Build context from retrieved chunks
    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        context_parts.append(f"[Source: {chunk['source']}] {chunk['text']}")

    context_text = "\n\n".join(context_parts) if context_parts else "No relevant data found for this query."

    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add chat history (last 10 messages max)
    for msg in chat_history[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    # Add current query with context
    user_message = f"""Based on the following evidence about {candidate_name}, answer the HR's question.

── Retrieved Evidence ──
{context_text}

── HR's Question ──
{query}"""

    messages.append({"role": "user", "content": user_message})

    # Call GPT-4o-mini via OpenRouter
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                CHATBOT_API_URL,
                headers={
                    "Authorization": f"Bearer {CHATBOT_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": CHATBOT_MODEL,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ [Insight AI] LLM call failed: {e}")
        return f"I'm sorry, I encountered an error processing your question. Please try again. (Error: {str(e)[:100]})"


# ══════════════════════════════════════════════════════════════
# 5. MAIN PIPELINE — End-to-end RAG query
# ══════════════════════════════════════════════════════════════

async def ask_about_candidate(
    candidate_id: str,
    position_id: str,
    question: str,
    chat_history: list[dict] = None,
    rebuild_index: bool = False,
) -> dict:
    """
    Full RAG pipeline:
    1. Gather context from MongoDB
    2. Build/query vector index
    3. Generate answer with GPT-4o-mini
    
    Returns: {"answer": str, "sources": list, "chunks_used": int}
    """
    if chat_history is None:
        chat_history = []

    # 1. Gather all candidate data
    context = await gather_candidate_context(candidate_id, position_id)
    candidate_name = context.get("candidate", {}).get("name", "the candidate") if context.get("candidate") else "the candidate"

    # 2. Extract text chunks
    chunks = _extract_text_chunks(context)

    if not chunks:
        return {
            "answer": "I don't have any data available for this candidate yet. Please ensure they have completed at least one interview or have been screened.",
            "sources": [],
            "chunks_used": 0,
        }

    # 3. Build vector index
    collection = build_vector_index(candidate_id, chunks)

    if collection is None:
        # Fallback: no ChromaDB, use all chunks as context directly
        top_chunks = [{"text": c["text"], "source": c["source"], "relevance": 1.0} for c in chunks[:15]]
    else:
        # 4. Semantic search
        top_chunks = query_vector_index(candidate_id, question, n_results=15)

    # 5. Generate answer
    answer = await generate_answer(
        query=question,
        retrieved_chunks=top_chunks,
        chat_history=chat_history,
        candidate_name=candidate_name,
    )

    # Unique sources used
    sources = list(set(c["source"] for c in top_chunks))

    return {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(top_chunks),
    }

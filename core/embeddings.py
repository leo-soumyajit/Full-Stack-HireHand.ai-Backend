"""
Embedding helper for AI job recommendations.

Primary: Google Gemini embedding API (remote → no local ML model, so it is
safe on small EC2 instances where ONNX/sentence-transformers OOM).
Set EMBEDDING_API_KEY (a fresh Google AI Studio key) to enable it.

Everything degrades gracefully: if embeddings are unavailable, callers fall
back to structured skill/keyword matching (see skill_overlap).
"""
import os
import math
import httpx
from typing import Optional, List, Tuple

EMBEDDING_API_KEY = (
    os.getenv("EMBEDDING_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or ""
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
_EMBED_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"
)


def embeddings_enabled() -> bool:
    return bool(EMBEDDING_API_KEY)


async def embed_text(text: str) -> Optional[List[float]]:
    """Return an embedding vector for `text`, or None if unavailable."""
    if not EMBEDDING_API_KEY or not text or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_EMBED_URL}?key={EMBEDDING_API_KEY}",
                json={
                    "model": f"models/{EMBEDDING_MODEL}",
                    "content": {"parts": [{"text": text[:9000]}]},
                },
            )
            if resp.status_code == 200:
                return resp.json().get("embedding", {}).get("values")
            print(f"⚠️ [embeddings] {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"⚠️ [embeddings] error: {e}")
    return None


def cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    """Cosine similarity in [0, 1]-ish range (clamped to >= 0)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, dot / (na * nb))


# ── Text serialization for embedding ────────────────────────────────
def profile_to_text(seeker: dict) -> str:
    parts: List[str] = []
    if seeker.get("headline"):
        parts.append(str(seeker["headline"]))
    if seeker.get("current_role"):
        parts.append(f"Current role: {seeker['current_role']}")
    if seeker.get("total_experience_years") is not None:
        parts.append(f"Experience: {seeker['total_experience_years']} years")
    if seeker.get("summary"):
        parts.append(str(seeker["summary"]))
    skills = seeker.get("skills") or []
    if skills:
        parts.append("Skills: " + ", ".join(map(str, skills)))
    for w in (seeker.get("work_experience") or [])[:6]:
        seg = " ".join(filter(None, [w.get("title"), w.get("company"), w.get("description")]))
        if seg:
            parts.append(seg)
    prefs = seeker.get("preferences") or {}
    if prefs.get("desired_roles"):
        parts.append("Looking for: " + ", ".join(map(str, prefs["desired_roles"])))
    # Fall back to raw resume text if the structured profile is thin
    if len("\n".join(parts)) < 120 and seeker.get("resume_text"):
        parts.append(str(seeker["resume_text"])[:4000])
    return "\n".join(parts).strip()


def job_to_text(job: dict, jd: dict) -> str:
    parts: List[str] = [job.get("title", "")]
    if job.get("level"):
        parts.append(f"Level: {job['level']}")
    if job.get("business_unit"):
        parts.append(f"Team: {job['business_unit']}")
    if jd.get("purpose"):
        parts.append(str(jd["purpose"]))
    for key in ("responsibilities", "skills", "experience", "education"):
        vals = jd.get(key) or []
        if vals:
            parts.append(f"{key.capitalize()}: " + ", ".join(map(str, vals)))
    return "\n".join(parts).strip()


# ── Structured skill matching (fallback + signal) ───────────────────
def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower().strip() if ch.isalnum() or ch == "+" or ch == "#")


def skill_overlap(seeker_skills: List[str], job_skills: List[str]) -> Tuple[List[str], List[str], float]:
    """Return (matched_job_skills, missing_job_skills, coverage_ratio)."""
    job_skills = [s for s in (job_skills or []) if s]
    if not job_skills:
        return [], [], 0.0
    seeker_norm = {_norm(s) for s in (seeker_skills or []) if s}
    matched, missing = [], []
    for js in job_skills:
        jn = _norm(js)
        hit = jn in seeker_norm or any(jn and (jn in sn or sn in jn) for sn in seeker_norm)
        (matched if hit else missing).append(js)
    ratio = len(matched) / len(job_skills) if job_skills else 0.0
    return matched, missing, ratio

"""
AI Job Recommendations for a logged-in seeker. Mounted at /api/seeker.

Scoring (EC2-safe — no local ML model):
  semantic  = cosine(seeker profile embedding, job JD embedding)   [Gemini API]
  skill     = overlap ratio of the job's required skills the seeker has
  score     = 0.65*semantic + 0.35*skill   (skill-only if embeddings off)
Top matches get a one-line AI explanation (single Groq call).
"""
from fastapi import APIRouter, Depends, Query
from typing import List

from core.seeker_deps import get_current_seeker
from core.embeddings import (
    embeddings_enabled, embed_text, cosine_similarity,
    job_to_text, profile_to_text, skill_overlap,
)
from core.seeker_ai import explain_matches
from database import positions_collection, applications_collection
from models.job_seeker import RecommendationItem
from routers.jobs_public import _company_map, _applicant_counts, _to_public

router = APIRouter()


def _rescale_semantic(sem: float) -> float:
    # Gemini cosine for related text sits ~0.35-0.9; stretch to a friendlier 0..1
    return max(0.0, min(1.0, (sem - 0.35) / 0.5))


@router.get("/recommendations", response_model=List[RecommendationItem])
async def get_recommendations(
    seeker: dict = Depends(get_current_seeker),
    limit: int = Query(20, le=50),
    explain: bool = Query(True, description="attach AI 'why it fits' lines to top matches"),
):
    seeker_skills = seeker.get("skills") or []
    seeker_vec = seeker.get("profile_embedding")

    # Ensure the seeker has an embedding if possible (first call after enabling embeddings)
    if not seeker_vec and embeddings_enabled():
        seeker_vec = await embed_text(profile_to_text(seeker))

    positions = [p async for p in positions_collection.find(
        {"is_published": True, "status": "Active"}
    )]
    if not positions:
        return []

    applied = set()
    async for a in applications_collection.find(
        {"seeker_id": seeker["id"]}, {"position_id": 1}
    ):
        applied.add(a["position_id"])

    scored = []
    for pos in positions:
        jd = pos.get("jd") or {}
        matched, missing, ratio = skill_overlap(seeker_skills, jd.get("skills", []))

        sem = 0.0
        if seeker_vec:
            jvec = pos.get("jd_embedding")
            if not jvec and embeddings_enabled():
                jvec = await embed_text(job_to_text(pos, jd))
                if jvec:
                    await positions_collection.update_one(
                        {"_id": pos["_id"]}, {"$set": {"jd_embedding": jvec}}
                    )
            sem = _rescale_semantic(cosine_similarity(seeker_vec, jvec)) if jvec else 0.0

        if seeker_vec and sem > 0:
            score = 0.65 * sem + 0.35 * ratio
        else:
            score = ratio if jd.get("skills") else 0.3  # neutral if JD has no skills listed

        scored.append({
            "pos": pos, "jd": jd, "score": score,
            "matched": matched, "missing": missing,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = scored[:limit]

    # Company + applicant counts (batch)
    company = await _company_map([s["pos"].get("user_id", "") for s in scored])
    counts = await _applicant_counts([str(s["pos"]["_id"]) for s in scored])

    # AI explanations for the top few (single call)
    reasons = {}
    if explain and scored:
        brief = [{
            "id": str(s["pos"]["_id"]),
            "title": s["pos"].get("title", ""),
            "matched_skills": s["matched"],
            "missing_skills": s["missing"],
        } for s in scored[:6]]
        reasons = await explain_matches(profile_to_text(seeker)[:1500], brief)

    items: List[RecommendationItem] = []
    for s in scored:
        pid = str(s["pos"]["_id"])
        items.append(RecommendationItem(
            job=_to_public(s["pos"], company.get(s["pos"].get("user_id", "")), counts.get(pid, 0)),
            match_percent=int(round(s["score"] * 100)),
            matched_skills=s["matched"],
            missing_skills=s["missing"],
            reason=reasons.get(pid),
            already_applied=pid in applied,
        ))
    return items

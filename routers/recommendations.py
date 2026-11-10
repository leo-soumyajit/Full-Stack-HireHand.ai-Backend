"""
Pro-level AI Job Recommendations. Mounted at /api/seeker.

Multi-factor scoring (see core/scoring.py):
  skills 35% • semantic 25% • experience 15% • title 10% • location 10% • recency 5%

Returns:
  match_percent, breakdown-per-factor, matched/missing skills,
  AI "why this fits" line, days_ago, saved/applied flags.

Also enforces diversity (max 2 per company) and filters out dismissed jobs.
"""
from fastapi import APIRouter, Depends, Query
from typing import List

from core.seeker_deps import get_current_seeker
from core.embeddings import embeddings_enabled, embed_text, job_to_text, profile_to_text
from core.scoring import compute_match, is_relevant
from core.seeker_ai import explain_matches
from database import positions_collection, applications_collection
from models.job_seeker import RecommendationItem, MatchBreakdown
from routers.jobs_public import _company_map, _applicant_counts, _to_public

router = APIRouter()


@router.get("/recommendations", response_model=List[RecommendationItem])
async def get_recommendations(
    seeker: dict = Depends(get_current_seeker),
    limit: int = Query(20, le=50),
    explain: bool = Query(True, description="attach AI 'why it fits' lines to top matches"),
    include_saved: bool = Query(True, description="include saved jobs in the mix"),
    min_score: int = Query(0, le=100, description="filter out jobs under this match%"),
):
    seeker_vec = seeker.get("profile_embedding")
    if not seeker_vec and embeddings_enabled():
        seeker_vec = await embed_text(profile_to_text(seeker))

    saved = set(seeker.get("saved_jobs") or [])
    dismissed = set(seeker.get("dismissed_jobs") or [])

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
        pid = str(pos["_id"])
        if pid in dismissed:
            continue

        jd = pos.get("jd") or {}

        # Lazily compute + cache JD embedding
        job_vec = pos.get("jd_embedding")
        if seeker_vec and not job_vec and embeddings_enabled():
            job_vec = await embed_text(job_to_text(pos, jd))
            if job_vec:
                await positions_collection.update_one(
                    {"_id": pos["_id"]}, {"$set": {"jd_embedding": job_vec}}
                )

        match = compute_match(seeker, seeker_vec, pos, jd, job_vec)
        # Relevance gate — drop jobs that have no meaningful signal to this
        # seeker (e.g. mechanical roles for a frontend engineer). This is
        # what Naukri/LinkedIn do: never show off-domain jobs even if some
        # weak factors (location/recency) push the raw score up a little.
        if not is_relevant(match):
            continue
        if match["match_percent"] < min_score:
            continue
        scored.append({"pos": pos, "pid": pid, "match": match})

    # Sort by match
    scored.sort(key=lambda x: x["match"]["match_percent"], reverse=True)

    # Diversity: max 2 jobs per company unless we're low on results
    max_per_company = 2
    counts, diversified = {}, []
    for s in scored:
        cid = s["pos"].get("user_id", "")
        if counts.get(cid, 0) < max_per_company:
            diversified.append(s)
            counts[cid] = counts.get(cid, 0) + 1
    # Top-up if under limit
    if len(diversified) < limit:
        seen = {s["pid"] for s in diversified}
        for s in scored:
            if s["pid"] not in seen:
                diversified.append(s)
            if len(diversified) >= limit:
                break
    scored = diversified[:limit]

    # Company + applicant counts (batched)
    company = await _company_map([s["pos"].get("user_id", "") for s in scored])
    counts_map = await _applicant_counts([s["pid"] for s in scored])

    # AI "why it fits" lines for the top handful (single call)
    reasons: dict = {}
    if explain and scored:
        brief = [{
            "id": s["pid"],
            "title": s["pos"].get("title", ""),
            "matched_skills": s["match"]["matched_skills"],
            "missing_skills": s["match"]["missing_skills"],
        } for s in scored[:6]]
        reasons = await explain_matches(profile_to_text(seeker)[:1500], brief)

    items: List[RecommendationItem] = []
    for s in scored:
        pid = s["pid"]
        match = s["match"]
        items.append(RecommendationItem(
            job=_to_public(s["pos"], company.get(s["pos"].get("user_id", "")), counts_map.get(pid, 0)),
            match_percent=match["match_percent"],
            matched_skills=match["matched_skills"],
            missing_skills=match["missing_skills"],
            reason=reasons.get(pid),
            already_applied=pid in applied,
            saved=pid in saved,
            days_ago=match["days_ago"],
            breakdown=MatchBreakdown(**match["breakdown"]),
        ))

    # If include_saved=False, drop the saved ones (dashboard uses this)
    if not include_saved:
        items = [i for i in items if not i.saved]
    return items


@router.get("/saved-jobs", response_model=List[RecommendationItem])
async def get_saved_jobs(seeker: dict = Depends(get_current_seeker)):
    """Return the seeker's saved jobs with the same breakdown format."""
    from bson import ObjectId
    saved = seeker.get("saved_jobs") or []
    if not saved:
        return []

    oids = []
    for sid in saved:
        try: oids.append(ObjectId(sid))
        except Exception: pass

    seeker_vec = seeker.get("profile_embedding")
    if not seeker_vec and embeddings_enabled():
        seeker_vec = await embed_text(profile_to_text(seeker))

    positions = [p async for p in positions_collection.find(
        {"_id": {"$in": oids}, "is_published": True}
    )]

    applied = set()
    async for a in applications_collection.find(
        {"seeker_id": seeker["id"]}, {"position_id": 1}
    ):
        applied.add(a["position_id"])

    company = await _company_map([p.get("user_id", "") for p in positions])
    counts_map = await _applicant_counts([str(p["_id"]) for p in positions])

    items: List[RecommendationItem] = []
    for pos in positions:
        pid = str(pos["_id"])
        jd = pos.get("jd") or {}
        match = compute_match(seeker, seeker_vec, pos, jd, pos.get("jd_embedding"))
        items.append(RecommendationItem(
            job=_to_public(pos, company.get(pos.get("user_id", "")), counts_map.get(pid, 0)),
            match_percent=match["match_percent"],
            matched_skills=match["matched_skills"],
            missing_skills=match["missing_skills"],
            already_applied=pid in applied,
            saved=True,
            days_ago=match["days_ago"],
            breakdown=MatchBreakdown(**match["breakdown"]),
        ))
    # Preserve the order the user saved them in (newest saved first)
    order = {sid: i for i, sid in enumerate(reversed(saved))}
    items.sort(key=lambda i: order.get(i.job.id, 999))
    return items


@router.get("/similar-jobs/{job_id}", response_model=List[RecommendationItem])
async def similar_jobs(
    job_id: str,
    seeker: dict = Depends(get_current_seeker),
    limit: int = 6,
):
    """Return jobs similar to the given job (used on JobDetail page). Requires seeker login."""
    from bson import ObjectId
    try:
        base = await positions_collection.find_one({"_id": ObjectId(job_id)})
    except Exception:
        return []
    if not base:
        return []

    base_skills = set((s or "").lower() for s in (base.get("jd") or {}).get("skills", []))
    base_title_words = set((base.get("title") or "").lower().split())

    seeker_vec = seeker.get("profile_embedding")
    if not seeker_vec and embeddings_enabled():
        seeker_vec = await embed_text(profile_to_text(seeker))

    applied = set()
    saved = set(seeker.get("saved_jobs") or [])
    async for a in applications_collection.find(
        {"seeker_id": seeker["id"]}, {"position_id": 1}
    ):
        applied.add(a["position_id"])

    candidates = []
    async for p in positions_collection.find(
        {"is_published": True, "status": "Active", "_id": {"$ne": base["_id"]}}
    ):
        jd = p.get("jd") or {}
        p_skills = set((s or "").lower() for s in jd.get("skills", []))
        skill_sim = len(base_skills & p_skills) / max(1, len(base_skills | p_skills))
        p_title_words = set((p.get("title") or "").lower().split())
        title_sim = len(base_title_words & p_title_words) / max(1, len(base_title_words | p_title_words))
        sim = 0.7 * skill_sim + 0.3 * title_sim
        candidates.append((sim, p))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in candidates[:limit]]

    company = await _company_map([p.get("user_id", "") for p in top])
    counts_map = await _applicant_counts([str(p["_id"]) for p in top])

    items: List[RecommendationItem] = []
    for pos in top:
        pid = str(pos["_id"])
        jd = pos.get("jd") or {}
        match = compute_match(seeker, seeker_vec, pos, jd, pos.get("jd_embedding"))
        items.append(RecommendationItem(
            job=_to_public(pos, company.get(pos.get("user_id", "")), counts_map.get(pid, 0)),
            match_percent=match["match_percent"],
            matched_skills=match["matched_skills"],
            missing_skills=match["missing_skills"],
            already_applied=pid in applied,
            saved=pid in saved,
            days_ago=match["days_ago"],
            breakdown=MatchBreakdown(**match["breakdown"]),
        ))
    return items

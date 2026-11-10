"""
Pro-level multi-factor job match scoring.

Weighted blend of 6 signals (LinkedIn/Naukri-style):
  skills (35%)   must-have + nice-to-have skill overlap
  semantic (25%) Gemini embedding cosine (profile ↔ JD)
  experience (15%) years-of-experience fit (with over/under-qual penalty)
  title (10%)    role-title alignment (current/desired ↔ job title)
  location (10%) location & preference match
  recency (5%)   freshness boost for newly posted jobs

Each factor returns a 0..1 sub-score PLUS a short reason snippet, so the UI
can render per-factor breakdown bars like Naukri/LinkedIn.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import re

from core.embeddings import cosine_similarity, skill_overlap


# ── Weights (sum to 1.0) ────────────────────────────────────────────
W_SKILLS = 0.35
W_SEMANTIC = 0.25
W_EXPERIENCE = 0.15
W_TITLE = 0.10
W_LOCATION = 0.10
W_RECENCY = 0.05


_LEVEL_YEARS = {
    "junior": (0, 2),
    "mid": (2, 5),
    "senior": (5, 10),
    "executive": (10, 25),
}

_TOKEN_SPLIT = re.compile(r"[^a-z0-9+#]+")


def _tokens(s: str) -> set:
    return {t for t in _TOKEN_SPLIT.split((s or "").lower()) if len(t) > 1}


def _rescale_semantic(sem: float) -> float:
    """Gemini cosine for related text sits roughly 0.35..0.9. Stretch to 0..1."""
    return max(0.0, min(1.0, (sem - 0.35) / 0.5))


# ── Individual factors ──────────────────────────────────────────────
def score_skills(seeker_skills: List[str], job_skills: List[str],
                 non_negotiables: Optional[List[str]] = None) -> Tuple[float, List[str], List[str]]:
    """Return (score 0..1, matched, missing). Non-negotiables weigh double."""
    matched, missing, ratio = skill_overlap(seeker_skills, job_skills or [])
    if not (job_skills or non_negotiables):
        return 0.5, [], []  # neutral when the JD lists no skills

    # Weight non-negotiables 2x
    nn = non_negotiables or []
    if nn:
        nn_matched, nn_missing, nn_ratio = skill_overlap(seeker_skills, nn)
        # Blend: must-have carries 60%, nice-to-have 40%
        total = 0.6 * nn_ratio + 0.4 * ratio
        # If any non-negotiable missing, cap at 0.7
        if nn_missing:
            total = min(total, 0.7)
        return round(total, 3), matched, missing
    return round(ratio, 3), matched, missing


def score_semantic(seeker_vec: Optional[list], job_vec: Optional[list]) -> float:
    if not seeker_vec or not job_vec:
        return 0.0
    return round(_rescale_semantic(cosine_similarity(seeker_vec, job_vec)), 3)


def score_experience(seeker_years: Optional[float], job_level: str,
                     job_yoe: Optional[str]) -> Tuple[float, str]:
    """Bell-curve around target years. Over/under-qual both penalise."""
    if seeker_years is None:
        return 0.5, "Experience unknown"

    low, high = _parse_yoe(job_yoe) or _LEVEL_YEARS.get((job_level or "mid").lower(), (2, 5))
    mid = (low + high) / 2 if (low + high) else 3

    if low <= seeker_years <= high:
        return 1.0, f"{seeker_years:.0f}y fits {low}-{high}y target"
    if seeker_years < low:
        gap = low - seeker_years
        # 1 year under = 0.8, 2y = 0.6, 3y = 0.4
        s = max(0.2, 1.0 - 0.2 * gap)
        return round(s, 3), f"{seeker_years:.0f}y vs {low}-{high}y needed ({gap:.0f}y short)"
    # Over-qualified (gentler penalty)
    gap = seeker_years - high
    s = max(0.55, 1.0 - 0.1 * gap)
    return round(s, 3), f"{seeker_years:.0f}y vs {low}-{high}y target (over-qualified)"


def _parse_yoe(s: Optional[str]):
    if not s: return None
    m = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", s)
    if m: return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d+)\+?", s)
    if m:
        y = int(m.group(1))
        return (y, y + 3)
    return None


def score_title(current_role: Optional[str], desired_roles: List[str],
                job_title: str) -> Tuple[float, str]:
    """Token overlap between current/desired roles and job title."""
    jt = _tokens(job_title)
    if not jt:
        return 0.5, ""
    best = 0.0
    best_src = ""
    for src in [current_role] + (desired_roles or []):
        if not src: continue
        st = _tokens(src)
        if not st: continue
        overlap = len(st & jt) / max(1, len(jt))
        if overlap > best:
            best, best_src = overlap, src
    return round(min(1.0, best * 1.5), 3), best_src  # 1.5x nudge because titles are short


def score_location(seeker_location: Optional[str], preferred_locations: List[str],
                   job_location: str) -> Tuple[float, str]:
    if not job_location:
        return 0.7, ""
    jl = (job_location or "").lower()
    if "remote" in jl:
        return 1.0, "Remote role"

    def _match(loc: Optional[str]) -> bool:
        if not loc: return False
        lo = loc.lower()
        return lo in jl or jl in lo or any(w in jl for w in lo.split() if len(w) > 3)

    if _match(seeker_location):
        return 1.0, f"Matches your location ({seeker_location})"
    for pl in preferred_locations or []:
        if _match(pl):
            return 1.0, f"Matches preferred: {pl}"
    # No match — mild penalty but don't tank the score
    return 0.35, "Different city"


def score_recency(published_at: Optional[str]) -> Tuple[float, int]:
    """Newer jobs get a boost. Returns (score, days_since_posted)."""
    if not published_at:
        return 0.5, 999
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 0.5, 999
    days = max(0, days)
    if days <= 1: return 1.0, days
    if days <= 7: return 0.9, days
    if days <= 14: return 0.75, days
    if days <= 30: return 0.6, days
    if days <= 60: return 0.4, days
    return 0.2, days


# ── Relevance gate ─────────────────────────────────────────────────
# Drop jobs with NO meaningful signal to this seeker. A chemistry-seeker
# shouldn't see mechanical jobs; filter noise out before ranking.
RELEVANCE_MIN_SKILLS = 25      # at least some overlap
RELEVANCE_MIN_SEMANTIC = 55    # real semantic similarity
RELEVANCE_MIN_TITLE = 35       # title token overlap
RELEVANCE_MIN_OVERALL = 32     # catch-all floor


def is_relevant(match: dict) -> bool:
    """True if the job has at least one strong signal of relevance to the seeker."""
    b = match.get("breakdown", {})
    skills = (b.get("skills") or {}).get("score", 0)
    semantic = (b.get("semantic") or {}).get("score", 0)
    title = (b.get("title") or {}).get("score", 0)
    return (
        skills >= RELEVANCE_MIN_SKILLS
        or semantic >= RELEVANCE_MIN_SEMANTIC
        or title >= RELEVANCE_MIN_TITLE
        or match.get("match_percent", 0) >= RELEVANCE_MIN_OVERALL
    )


# ── Composite ──────────────────────────────────────────────────────
def compute_match(
    seeker: dict,
    seeker_vec: Optional[list],
    job: dict,
    jd: dict,
    job_vec: Optional[list],
) -> dict:
    """Return a complete breakdown + overall match_percent for a single job."""
    seeker_skills = seeker.get("skills") or []
    non_neg = (jd.get("non_negotiables") or [])

    skills_s, matched, missing = score_skills(seeker_skills, jd.get("skills", []), non_neg)
    semantic_s = score_semantic(seeker_vec, job_vec)
    exp_s, exp_reason = score_experience(
        seeker.get("total_experience_years"),
        job.get("level", "Mid"),
        job.get("years_of_experience"),
    )
    desired = (seeker.get("preferences") or {}).get("desired_roles") or []
    title_s, title_src = score_title(seeker.get("current_role"), desired, job.get("title", ""))
    pref_locs = (seeker.get("preferences") or {}).get("preferred_locations") or []
    loc_s, loc_reason = score_location(seeker.get("location"), pref_locs, job.get("location", ""))
    rec_s, days_ago = score_recency(job.get("published_at"))

    # If embeddings unavailable, redistribute semantic weight into skills + title
    has_semantic = bool(seeker_vec and job_vec)
    if has_semantic:
        overall = (
            W_SKILLS * skills_s
            + W_SEMANTIC * semantic_s
            + W_EXPERIENCE * exp_s
            + W_TITLE * title_s
            + W_LOCATION * loc_s
            + W_RECENCY * rec_s
        )
    else:
        overall = (
            (W_SKILLS + W_SEMANTIC * 0.6) * skills_s   # bulk of semantic weight → skills
            + W_EXPERIENCE * exp_s
            + (W_TITLE + W_SEMANTIC * 0.4) * title_s   # some to title
            + W_LOCATION * loc_s
            + W_RECENCY * rec_s
        )

    match_percent = int(round(max(0.0, min(1.0, overall)) * 100))

    return {
        "match_percent": match_percent,
        "matched_skills": matched,
        "missing_skills": missing,
        "days_ago": days_ago,
        "breakdown": {
            "skills":     {"score": round(skills_s * 100), "weight": int(W_SKILLS * 100)},
            "semantic":   {"score": round(semantic_s * 100), "weight": int(W_SEMANTIC * 100),
                            "available": has_semantic},
            "experience": {"score": round(exp_s * 100), "weight": int(W_EXPERIENCE * 100),
                            "reason": exp_reason},
            "title":      {"score": round(title_s * 100), "weight": int(W_TITLE * 100),
                            "reason": f"vs '{title_src}'" if title_src else ""},
            "location":   {"score": round(loc_s * 100), "weight": int(W_LOCATION * 100),
                            "reason": loc_reason},
            "recency":    {"score": round(rec_s * 100), "weight": int(W_RECENCY * 100),
                            "days_ago": days_ago},
        },
    }


# ── Profile strength (Naukri-style) ─────────────────────────────────
PROFILE_CHECKS = [
    ("name", "Full name", 5),
    ("headline", "Professional headline", 10),
    ("current_role", "Current role", 5),
    ("location", "Location", 5),
    ("total_experience_years", "Years of experience", 10),
    ("summary", "Professional summary", 10),
    ("skills", "At least 3 skills", 15),
    ("resume_url", "Resume uploaded", 15),
    ("phone", "Phone number", 5),
    ("avatar_url", "Profile photo", 5),
    ("education", "Education", 5),
    ("work_experience", "Work experience", 5),
    ("preferences.desired_roles", "Desired roles", 3),
    ("preferences.preferred_locations", "Preferred locations", 2),
]


def profile_strength(seeker: dict) -> dict:
    """Return {percent, missing: [{field, label, points}], tips: [...]}"""
    score = 0
    missing = []
    for path, label, pts in PROFILE_CHECKS:
        val = seeker
        for part in path.split("."):
            val = (val or {}).get(part) if isinstance(val, dict) else None
        ok = False
        if path == "skills":
            ok = isinstance(val, list) and len(val) >= 3
        elif path in ("education", "work_experience",
                      "preferences.desired_roles", "preferences.preferred_locations"):
            ok = isinstance(val, list) and len(val) > 0
        else:
            ok = bool(val)
        if ok:
            score += pts
        else:
            missing.append({"field": path, "label": label, "points": pts})
    percent = min(100, score)
    # Top 3 tips (highest point value)
    tips = sorted(missing, key=lambda x: -x["points"])[:3]
    return {"percent": percent, "missing": missing, "tips": tips}

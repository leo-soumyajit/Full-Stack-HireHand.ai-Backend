"""
Groq-powered helpers for the Job Seeker portal:
  - extract_profile_from_resume: parse resume text -> structured Naukri-style profile
  - explain_matches: one call that writes a short "why this fits you" line per job

Reuses core.openrouter._call_llm (already pointed at Groq via env), which
returns parsed JSON and handles retries.
"""
from typing import List, Dict
from core.openrouter import _call_llm


async def extract_profile_from_resume(resume_text: str) -> dict:
    """Return a structured profile dict extracted from raw resume text."""
    system_prompt = (
        "You are an elite resume parser. Extract a clean, structured candidate "
        "profile from the resume text. Return ONLY valid JSON, no markdown, no commentary. "
        "Infer total_experience_years as a number from the work history. "
        "Normalize skills to concise canonical names (e.g. 'React', 'Node.js', 'Python'). "
        "If a field is unknown, use null or an empty list."
    )
    schema = (
        '{\n'
        '  "name": string|null,\n'
        '  "email": string|null,\n'
        '  "phone": string|null,\n'
        '  "headline": string|null,            // e.g. "Senior Frontend Engineer"\n'
        '  "location": string|null,\n'
        '  "current_role": string|null,\n'
        '  "total_experience_years": number|null,\n'
        '  "summary": string|null,             // 2-3 sentence professional summary\n'
        '  "skills": string[],\n'
        '  "education": [{"degree": string, "institution": string, "year": string}],\n'
        '  "work_experience": [{"title": string, "company": string, "duration": string, "description": string}],\n'
        '  "social_links": {"linkedin": string|null, "github": string|null, "portfolio": string|null}\n'
        '}'
    )
    user_prompt = f"RESUME TEXT:\n{resume_text[:12000]}\n\nReturn JSON exactly in this shape:\n{schema}"
    return await _call_llm(system_prompt, user_prompt)


async def explain_matches(seeker_summary: str, jobs_brief: List[dict]) -> Dict[str, str]:
    """
    jobs_brief: [{"id","title","matched_skills","missing_skills"}]
    Returns {job_id: one-line reason}. Best-effort — returns {} on failure.
    """
    if not jobs_brief:
        return {}
    system_prompt = (
        "You are a career advisor. For each job, write ONE short, specific, encouraging "
        "sentence (max 22 words) explaining why it fits this candidate, referencing their "
        "matched strengths and (gently) one gap if relevant. Return ONLY JSON: "
        '{"reasons": {"<job_id>": "<one sentence>"}}'
    )
    lines = []
    for j in jobs_brief:
        lines.append(
            f"- id={j['id']} | title={j.get('title','')} | "
            f"matched={', '.join(j.get('matched_skills', [])[:8])} | "
            f"missing={', '.join(j.get('missing_skills', [])[:5])}"
        )
    user_prompt = (
        f"CANDIDATE:\n{seeker_summary[:1500]}\n\nJOBS:\n" + "\n".join(lines)
        + '\n\nReturn: {"reasons": {"<id>": "<sentence>"}}'
    )
    try:
        data = await _call_llm(system_prompt, user_prompt)
        reasons = data.get("reasons", data) if isinstance(data, dict) else {}
        return {str(k): str(v) for k, v in reasons.items()} if isinstance(reasons, dict) else {}
    except Exception as e:
        print(f"⚠️ [seeker_ai] explain_matches failed: {e}")
        return {}

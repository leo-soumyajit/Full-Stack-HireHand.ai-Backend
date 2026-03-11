"""
AI helper for EOS-IA Psychometric Intelligence System.
Calls OpenRouter (same API key as frontend) from the backend.
"""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def _call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Generic async LLM call — returns parsed JSON dict."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)


async def generate_psychometric_profile(
    jd_purpose: str,
    jd_responsibilities: list[str],
    jd_experience: list[str],
    role_title: str,
    level: str,
    business_unit: str,
    location: str,
) -> dict:
    """
    Given a JD, generate a role-calibrated psychometric profile with 5 tailored
    behavioural questions for this specific role's stress environment.
    """
    system_prompt = """You are EOS-IA, an elite psychometric intelligence system used by top executive search firms.

Your task: Analyze this Job Description and generate a ROLE-CALIBRATED psychometric profile.
Do NOT generate generic personality questions. Every question must be specifically designed 
for the pressures, authority structure, and execution demands of THIS exact role.

Return ONLY valid JSON in this exact structure:
{
  "company_context": "2-3 sentences describing the organizational context and culture inferred from the JD",
  "business_model": "one of: Tech Startup | FinTech | FMCG | Manufacturing | Infrastructure | Professional Services | Healthcare | E-Commerce | SaaS | Consulting",
  "role_type": "one of: execution-heavy | strategy-heavy | governance-heavy | people-heavy | hybrid",
  "key_stressors": ["stressor 1", "stressor 2", "stressor 3", "stressor 4"],
  "required_traits": [
    {
      "trait": "Name of behavioral trait",
      "question": "Specific, scenario-based interview question that reveals this trait in context of the role",
      "why_important": "Why this trait is critical for THIS specific role",
      "scoring_guide": "1 = [worst behavior], 5 = [average behavior], 10 = [elite behavior]"
    }
  ]
}
Generate exactly 5 traits. Make them role-specific, not generic."""

    user_prompt = f"""Role: {role_title} | Level: {level} | Department: {business_unit} | Location: {location}

JD Purpose:
{jd_purpose}

Key Responsibilities:
{chr(10).join(f'- {r}' for r in jd_responsibilities[:6])}

Experience Requirements:
{chr(10).join(f'- {e}' for e in jd_experience[:4])}

Generate the psychometric profile for this specific role."""

    return await _call_llm(system_prompt, user_prompt)


async def generate_fitment_report(
    profile: dict,
    candidate_name: str,
    role_title: str,
    scores: list[dict],
) -> dict:
    """
    Given a psychometric profile and interviewer-submitted scores,
    generate the 4-part EOS-IA Fitment Report via LLM.
    """
    system_prompt = """You are EOS-IA, generating a Psychometric Fitment Report.
    
You receive:
1. The role's psychometric profile (context, stressors, required traits)
2. Interviewer-submitted scores (1-10) per trait with optional notes

Your task: Generate a predictive, intelligent fitment report — not just an average.
Model BEHAVIORAL PATTERNS, not just scores. Consider how traits INTERACT under the role's specific stressors.

Return ONLY valid JSON in this exact structure:
{
  "trait_matrix": [
    {
      "trait": "trait name",
      "score": 7.5,
      "interpretation": "Specific behavioral interpretation of this score in the context of this role. 1-2 sentences."
    }
  ],
  "pattern_cluster": {
    "name": "Short archetype name (e.g. Strategic Executor, Reactive Operator, Governance Shield)",
    "description": "2-3 sentences describing how this person will behave in this role specifically",
    "sentiment": "positive | neutral | negative"
  },
  "risk": {
    "level": "LOW | MEDIUM | HIGH",
    "statement": "One-line risk headline",
    "role_specific_risk": "2-3 sentences on the specific failure mode for this person in this role under this role's stressors"
  },
  "verdict": {
    "decision": "GO | CONDITIONAL GO | NO-GO",
    "rationale": "2-3 sentences justifying the verdict based on trait interactions and role stressors",
    "coaching_note": "Specific development area if CONDITIONAL GO, positive reinforcement if GO, disqualifying reason if NO-GO"
  },
  "composite_psych_score": 74
}

composite_psych_score should be 0-100. It is NOT a simple average — it weights critical role traits more heavily 
and penalizes HIGH risk profiles."""

    scores_text = "\n".join(
        f"- {s['trait']}: {s['score']}/10" + (f" | Notes: {s['notes']}" if s.get("notes") else "")
        for s in scores
    )

    user_prompt = f"""Candidate: {candidate_name}
Role: {role_title}

ROLE PSYCHOMETRIC CONTEXT:
- Company Context: {profile.get('company_context', '')}
- Business Model: {profile.get('business_model', '')}
- Role Type: {profile.get('role_type', '')}
- Key Stressors: {', '.join(profile.get('key_stressors', []))}

INTERVIEWER SCORES:
{scores_text}

TRAIT DESCRIPTIONS:
{chr(10).join(f"- {t['trait']}: {t['why_important']}" for t in profile.get('required_traits', []))}

Generate the Psychometric Fitment Report."""

    return await _call_llm(system_prompt, user_prompt)

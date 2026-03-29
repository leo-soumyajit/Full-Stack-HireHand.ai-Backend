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


async def analyze_resume(
    resume_text: str,
    jd_purpose: str,
    jd_responsibilities: list,
    jd_experience: list,
    role_title: str,
    level: str,
    business_unit: str,
) -> dict:
    """
    AI Resume Screening — analyzes a resume against the position JD.
    Returns structured fitment analysis for this specific role.
    """
    system_prompt = """You are an elite AI Talent Intelligence system used by top executive search firms.

Your task: Analyze a candidate's resume against a specific Job Description and return a structured fitment assessment.

Rules:
- Be specific — reference actual content from the resume and JD
- Do NOT give generic feedback — tie every point to THIS EXACT role
- Extract the candidate's name and email from the resume text if present
- Be honest about gaps — do not inflate scores

Return ONLY valid JSON in this exact structure:
{
  "candidate_name": "Full name extracted from resume, or 'Unknown Candidate' if not found",
  "candidate_email": "email@domain.com or null",
  "candidate_current_role": "Current job title and company from resume, or null",
  "resume_score": 7.8,
  "jd_match_percent": 78,
  "strengths": [
    "Specific strength 1 tied to JD requirement",
    "Specific strength 2 tied to JD requirement",
    "Specific strength 3 tied to JD requirement"
  ],
  "gaps": [
    "Specific gap 1 vs JD requirement",
    "Specific gap 2 vs JD requirement"
  ],
  "experience_summary": "2 sentences summarizing the candidate's relevance to this specific role",
  "verdict": "STRONG FIT",
  "verdict_rationale": "2-3 sentences explaining why this verdict for THIS role specifically",
  "recommended_stage": "Interview L1"
}

verdict must be exactly one of: STRONG FIT | POTENTIAL FIT | WEAK FIT | NOT SUITABLE
recommended_stage must be exactly one of: Screened | Interview L1 | Interview L2 | Rejected
resume_score is 0-10 (not inflated — 10 means near-perfect match)
jd_match_percent is 0-100"""

    user_prompt = f"""ROLE TO FILL:
Title: {role_title}
Level: {level}
Department: {business_unit}

JD PURPOSE:
{jd_purpose}

KEY RESPONSIBILITIES:
{chr(10).join(f'- {r}' for r in jd_responsibilities[:8])}

EXPERIENCE REQUIREMENTS:
{chr(10).join(f'- {e}' for e in jd_experience[:5])}

---
CANDIDATE RESUME:
{resume_text[:6000]}

Analyze this candidate's fit for the above role."""

    return await _call_llm(system_prompt, user_prompt)

# ── FULL AUTOMATED PSYCHOMETRIC TEST (CANDIDATE FACING) ───────────────────

async def generate_psychometric_mcq_test(
    jd_text: str, role_title: str, level: str, business_unit: str, num_questions: int = 10
) -> dict:
    """
    Generate a role-calibrated, scenario-based MCQ test.
    Instead of asking direct questions, frame them as complex scenarios a person in THIS role would face.
    Each option represents a different behavioral trait.
    """
    system_prompt = f"""You are EOS-IA, an elite psychometric intelligence system.
Your task: Generate exactly {num_questions} hyper-specific, scenario-based behavioral multiple-choice questions for the following role.

Rules:
1. Do NOT ask generic questions ("What is your greatest weakness?").
2. Create highly realistic, stressful, or ambiguous scenarios specific to THIS role's context.
3. Provide exactly 4 options for each question (A, B, C, D).
4. Do NOT mark a "correct" answer. Every option must represent a valid but distinct behavioral archetype (e.g., Risk-averse vs. Risk-seeking, Collaborative vs. Autocratic, Speed vs. Accuracy).
5. The options must be subtle; no obvious "bad" answers.

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "id": "q_1",
      "trait_assessed": "Risk Tolerance vs. Governance",
      "scenario": "A highly detailed 2-3 sentence realistic scenario specific to the role's pressures.",
      "options": [
        {{ "id": "A", "text": "Detailed action corresponding to Archetype 1" }},
        {{ "id": "B", "text": "Detailed action corresponding to Archetype 2" }},
        {{ "id": "C", "text": "Detailed action corresponding to Archetype 3" }},
        {{ "id": "D", "text": "Detailed action corresponding to Archetype 4" }}
      ]
    }}
  ]
}}"""

    user_prompt = f"""Role: {role_title} | Level: {level} | BU: {business_unit}

JOB DESCRIPTION CONTEXT:
{jd_text}

Generate {num_questions} scenario questions now."""

    return await _call_llm(system_prompt, user_prompt)


async def analyze_psychometric_mcq_submission(
    jd_text: str, role_title: str, test_data: dict, submission_data: dict
) -> dict:
    """
    Analyze the candidate's chosen answers AND the behavioral telemetry (time spent).
    Returns a full FitmentReport structure.
    """
    system_prompt = """You are EOS-IA, an elite psychometric intelligence system.
Your task: Analyze a candidate's responses to a role-calibrated scenario test.
Critically, you must evaluate TWO dimensions:
1. THE DECISION (Which option they chose, mapping to behavioral traits).
2. THE BEHAVIORAL TELEMETRY (How long they took in milliseconds).

Telemetry interpretation heuristics:
- Very fast (< 5000ms) on complex scenarios = Rushed, impulsive, or lack of depth.
- Average (10000ms - 25000ms) = Measured, confident decision making.
- Very slow (> 45000ms) on ambiguous scenarios = Overthinking, hesitation, risk-aversion, or freezing under pressure.

You must output a highly judgmental, specific, corporate-grade Fitment Report matching the role's JD.

Return ONLY valid JSON matching this exact structure:
{
  "trait_matrix": [
    {
      "trait": "Name of trait assessed (e.g., Decisiveness under ambiguity)",
      "score": 8.5,
      "interpretation": "2 sentences analyzing their choices AND their timing for this trait."
    }
  ],
  "pattern_cluster": {
    "name": "Short archetype name (e.g., Hesitant Analyst, Impulsive Executor)",
    "description": "2-3 sentences describing their overall behavioral pattern.",
    "sentiment": "positive | neutral | negative"
  },
  "risk": {
    "level": "LOW | MEDIUM | HIGH",
    "statement": "One-line core behavioral risk",
    "role_specific_risk": "How this specific behavioral pattern will fail inside THIS specific role's context."
  },
  "verdict": {
    "decision": "GO | CONDITIONAL GO | NO-GO",
    "rationale": "Why this decision, based on the intersection of their choices, telemetry, and the JD demands.",
    "coaching_note": "What to watch for if hired, or exact reason for rejection."
  },
  "composite_psych_score": 75
}

composite_psych_score must be 0-100."""

    # Reconstruct the candidate's journey for the prompt
    responses_mapped = []
    questions_dict = {q['id']: q for q in test_data.get('questions', [])}
    
    for resp in submission_data.get('responses', []):
        q_id = resp.get('question_id')
        q = questions_dict.get(q_id)
        if q:
            opt = next((o for o in q['options'] if o['id'] == resp.get('selected_option_id')), None)
            responses_mapped.append(f"""
Question: {q['scenario']}
Trait Assessed: {q['trait_assessed']}
Candidate Chose: {opt['text'] if opt else 'Skipped'}
Time Spent: {resp.get('time_spent_ms', 0)} ms""")

    user_prompt = f"""Role: {role_title}

JOB DESCRIPTION CONTEXT:
{jd_text}

CANDIDATE'S ASSESSMENT JOURNEY (Telemetry included):
{''.join(responses_mapped)}

Generate the Fitment Report JSON."""

    return await _call_llm(system_prompt, user_prompt)

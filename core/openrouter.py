"""
AI helper for EOS-IA Psychometric Intelligence System.
Supports Google Gemini (primary) with OpenRouter fallback.
"""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

# ── AI Provider Config ───────────────────────────────────────────────
# We read from standard AI_ variables, with fallbacks to legacy names so nothing breaks.
AI_API_KEY = os.getenv("AI_API_KEY", os.getenv("GEMINI_API_KEY", os.getenv("OPENROUTER_API_KEY", "")))
AI_MODEL = os.getenv("AI_MODEL", os.getenv("GEMINI_MODEL", os.getenv("OPENROUTER_MODEL", "gemini-2.5-flash")))
# Default to Gemini url if not set
AI_API_URL = os.getenv(
    "AI_API_URL", 
    os.getenv("OPENROUTER_URL", "https://generativelanguage.googleapis.com/v1beta/models")
)

async def _call_llm(system_prompt: str, user_prompt: str, _retries: int = 3) -> dict:
    """Generic async LLM call with automatic retry — returns parsed JSON dict.
    Dynamically routes to the correct API format based on the configured AI_API_URL.
    """
    if not AI_API_KEY:
        raise ValueError("AI service is not configured. Please add AI_API_KEY in your .env file.")

    if "generativelanguage.googleapis" in AI_API_URL:
        return await _call_gemini(system_prompt, user_prompt, _retries)
    else:
        return await _call_openai_format(system_prompt, user_prompt, _retries)


async def _call_gemini(system_prompt: str, user_prompt: str, _retries: int = 3) -> dict:
    """Call Google Gemini API with native JSON mode and retry."""
    import asyncio as _asyncio
    last_error = None

    base_url = AI_API_URL.rstrip('/')
    # If the user put the full url including the model, we can try to use it directly,
    # but normally the URL in .env should just be the base: https://generativelanguage.googleapis.com/v1beta/models
    gemini_url = f"{base_url}/{AI_MODEL}:generateContent?key={AI_API_KEY}"

    for attempt in range(1, _retries + 1):
        try:
            async with httpx.AsyncClient(timeout=150.0) as client:
                resp = await client.post(
                    gemini_url,
                    json={
                        "contents": [
                            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n---\n\n{user_prompt}"}]}
                        ],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.7,
                        },
                        "safetySettings": [
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        ]
                    },
                )

                # ── Error handling ───────────────────────────────────────
                if resp.status_code == 400:
                    try:
                        err_msg = resp.json().get("error", {}).get("message", "")
                    except Exception:
                        err_msg = resp.text[:200]
                    print(f"⚠️ Gemini attempt {attempt}/{_retries} — 400: {err_msg}")
                    
                    if ("not available" in err_msg.lower() or "not found" in err_msg.lower()):
                        raise ValueError(f"AI model '{AI_MODEL}' is not available. Please check AI_MODEL in your .env file.")
                    
                    last_error = err_msg
                    if attempt < _retries:
                        await _asyncio.sleep(2.0 * attempt)
                        continue
                    raise ValueError(f"AI generation failed: {err_msg[:150]}")

                if resp.status_code == 403:
                    raise ValueError("Gemini API key is invalid or lacks permissions. Please check your AI_API_KEY.")
                
                if resp.status_code == 429:
                    print(f"⚠️ Gemini attempt {attempt}/{_retries} — rate limited")
                    last_error = "Rate limited"
                    if attempt < _retries:
                        await _asyncio.sleep(3.0 * attempt)
                        continue
                    raise ValueError("AI rate limit reached. Please wait a moment and try again.")

                if resp.status_code >= 500:
                    print(f"⚠️ Gemini attempt {attempt}/{_retries} — server error {resp.status_code}")
                    last_error = f"Server error {resp.status_code}"
                    if attempt < _retries:
                        await _asyncio.sleep(2.0 * attempt)
                        continue
                    raise ValueError("AI service is temporarily unavailable. Please try again.")

                if resp.status_code != 200:
                    raise ValueError(f"AI service error ({resp.status_code}). Please try again.")

                # ── Success path ─────────────────────────────────────────
                data = resp.json()
                candidates = data.get("candidates", [])
                
                if not candidates:
                    # Check for safety block
                    block_reason = data.get("promptFeedback", {}).get("blockReason", "")
                    if block_reason:
                        raise ValueError(f"AI blocked the request due to safety policy: {block_reason}")
                    if attempt < _retries:
                        last_error = "Empty candidates"
                        await _asyncio.sleep(1.0)
                        continue
                    raise ValueError("AI returned an empty response. Please try again.")

                content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if not content or not content.strip():
                    if attempt < _retries:
                        last_error = "Empty content"
                        await _asyncio.sleep(1.0)
                        continue
                    raise ValueError("AI returned an empty response. Please try again.")

                # Parse JSON (Gemini with responseMimeType should return clean JSON)
                content = _extract_json(content)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    if attempt < _retries:
                        last_error = "Invalid JSON"
                        continue
                    raise ValueError("AI returned an invalid response format. Please try again.")

        except httpx.TimeoutException:
            print(f"⚠️ Gemini attempt {attempt}/{_retries} timed out")
            last_error = "Timeout"
            if attempt < _retries:
                continue
            raise ValueError("AI request timed out. Try reducing the question count or try again.")
        except httpx.ConnectError:
            raise ValueError("Could not connect to AI service. Please check your internet connection.")
        except ValueError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt < _retries:
                continue
            raise ValueError(f"AI service error: {str(e)[:100]}")

    raise ValueError(f"AI failed after {_retries} attempts. Last error: {last_error}")


async def _call_openai_format(system_prompt: str, user_prompt: str, _retries: int = 3) -> dict:
    """Fallback: Call standard OpenAI-compatible API (e.g. OpenRouter) with retry."""
    import asyncio as _asyncio
    last_error = None

    for attempt in range(1, _retries + 1):
        try:
            async with httpx.AsyncClient(timeout=150.0) as client:
                resp = await client.post(
                    AI_API_URL,
                    headers={
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://hirehand.ai",
                        "X-Title": "HireHand AI",
                    },
                    json={
                        "model": AI_MODEL,
                        "route": "fallback", # Specific to OpenRouter but harmless for others
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )

                if resp.status_code == 401:
                    raise ValueError("AI API key is invalid or expired. Please update your AI_API_KEY.")
                if resp.status_code == 402:
                    raise ValueError("AI credits exhausted. Please add credits to your AI provider account.")
                
                if resp.status_code in (429, 503) or resp.status_code >= 500:
                    print(f"⚠️ OpenRouter attempt {attempt}/{_retries} failed: {resp.status_code}")
                    last_error = f"Status {resp.status_code}"
                    if attempt < _retries:
                        await _asyncio.sleep(2.0 * attempt)
                        continue
                    raise ValueError("AI service is temporarily unavailable. Please try again.")

                if resp.status_code == 400:
                    try:
                        err_msg = resp.json().get("error", {}).get("message", "")
                    except Exception:
                        err_msg = resp.text[:200]
                    
                    transient_kw = ["provider", "model output", "try again", "empty", "timeout", "overloaded"]
                    if any(kw in err_msg.lower() for kw in transient_kw) and attempt < _retries:
                        print(f"⚠️ OpenRouter attempt {attempt}/{_retries} — 400: {err_msg}")
                        last_error = err_msg
                        await _asyncio.sleep(2.0 * attempt)
                        continue
                    raise ValueError(f"AI generation failed: {err_msg[:150]}")

                if resp.status_code >= 400:
                    raise ValueError(f"AI service error ({resp.status_code}).")

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    if attempt < _retries:
                        last_error = "Empty response"
                        continue
                    raise ValueError("AI returned an empty response.")

                content = choices[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    if attempt < _retries:
                        last_error = "Empty content"
                        continue
                    raise ValueError("AI returned an empty response.")

                content = _extract_json(content)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    if attempt < _retries:
                        last_error = "Invalid JSON"
                        continue
                    raise ValueError("AI returned an invalid response format.")

        except httpx.TimeoutException:
            last_error = "Timeout"
            if attempt < _retries:
                continue
            raise ValueError("AI request timed out.")
        except httpx.ConnectError:
            raise ValueError("Could not connect to AI service.")
        except ValueError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt < _retries:
                continue
            raise ValueError(f"AI error: {str(e)[:100]}")

    raise ValueError(f"AI failed after {_retries} attempts. Last error: {last_error}")


def _extract_json(content: str) -> str:
    """Robust JSON extraction from LLM output."""
    content = content.strip()
    if "```json" in content:
        content = content.split("```json", 1)[1]
    if "```" in content:
        content = content.split("```", 1)[0]
    content = content.strip()
    if not content.startswith("{") and not content.startswith("["):
        brace = content.find("{")
        bracket = content.find("[")
        if brace >= 0 and (bracket < 0 or brace < bracket):
            content = content[brace:]
        elif bracket >= 0:
            content = content[bracket:]
    return content


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
    system_prompt = """You are EOS-IA, generating a Psychometric Fitment Report based on interviewer-submitted trait scores.

You receive:
1. The role's psychometric profile (context, stressors, required traits)
2. Interviewer-submitted scores (1-10) per trait with optional notes

Your task: Generate a predictive, intelligent fitment report — not just an average.
Model BEHAVIORAL PATTERNS, not just scores. Consider how traits INTERACT under the role's specific stressors.

═══ SCORING INTERPRETATION GUIDELINES ═══
• 1-3: Critical deficiency — this person will struggle severely in this trait area
• 4-5: Below expectations — noticeable gaps that require significant development  
• 6-7: Meets minimum bar — adequate but not differentiated
• 8-9: Strong performer — clear strength with minor refinement needed
• 10: Exceptional — rare elite-level capability

═══ COMPOSITE SCORE CALCULATION ═══
composite_psych_score (0-100) is NOT a simple average of trait scores × 10.
You must:
1. Weight traits by their criticality for THIS role (inferred from stressors and role type)
2. Apply interaction effects: contradictory trait combinations (e.g., high autonomy + low communication) should PENALIZE
3. Penalize if 2+ traits are below 5.0
4. DO NOT default to 74-76. These are lazy anchor scores and are FORBIDDEN.
5. Use the FULL 0-100 range based on genuine analysis.

═══ VERDICT DETERMINATION ═══
• GO: composite >= 78, risk LOW, no critical trait below 5.0
• CONDITIONAL GO: composite 55-77, OR risk MEDIUM, OR 1 critical trait below 5.0
• NO-GO: composite < 55, OR risk HIGH, OR 2+ traits below 4.0

Return ONLY valid JSON in this exact structure:
{
  "trait_matrix": [
    {
      "trait": "trait name",
      "score": "<1.0 to 10.0 — calculate based on actual data, use FULL range>",
      "interpretation": "2-3 sentences: Specific behavioral interpretation of this score in the context of this role. Reference the interviewer's notes if provided."
    }
  ],
  "pattern_cluster": {
    "name": "Precise archetype (e.g., Strategic Executor, Reactive Operator, Governance Shield, Collaborative Strategist)",
    "description": "3 sentences describing how this person will behave in this role specifically, based on the interaction of their trait scores.",
    "sentiment": "positive | neutral | negative"
  },
  "risk": {
    "level": "LOW | MEDIUM | HIGH",
    "statement": "One-line risk headline",
    "role_specific_risk": "2-3 sentences on the specific failure mode for this person in this role under this role's stressors"
  },
  "verdict": {
    "decision": "GO | CONDITIONAL GO | NO-GO",
    "rationale": "3 sentences justifying the verdict based on trait interactions, scores, and role stressors. Reference specific low/high scores.",
    "coaching_note": "2-3 actionable sentences: Development area if CONDITIONAL GO, strength reinforcement if GO, disqualifying evidence if NO-GO"
  },
  "composite_psych_score": "<CALCULATE: 0-100 based on weighted trait scores, telemetry, and risk. DO NOT copy any number from this example — derive it from the actual scores above.>"
}

CRITICAL: The composite_psych_score MUST be a raw integer (not a string). The placeholder above is just to show you must CALCULATE it yourself.
ANTI-ANCHORING RULE: You are FORBIDDEN from outputting 62, 68, 74, 75, or 76 as composite_psych_score. These are known anchor values. Calculate the real score from the data."""

    scores_text = "\n".join(
        f"- {s['trait']}: {s['score']}/10" + (f" | Notes: {s['notes']}" if s.get("notes") else "")
        for s in scores
    )

    # Calculate simple average for AI context
    avg_score = sum(s['score'] for s in scores) / max(len(scores), 1)

    user_prompt = f"""Candidate: {candidate_name}
Role: {role_title}

ROLE PSYCHOMETRIC CONTEXT:
- Company Context: {profile.get('company_context', '')}
- Business Model: {profile.get('business_model', '')}
- Role Type: {profile.get('role_type', '')}
- Key Stressors: {', '.join(profile.get('key_stressors', []))}

INTERVIEWER SCORES (Simple Average: {avg_score:.1f}/10):
{scores_text}

TRAIT DESCRIPTIONS:
{chr(10).join(f"- {t['trait']}: {t['why_important']}" for t in profile.get('required_traits', []))}

Generate the Psychometric Fitment Report.

SCORING FORMULA — You MUST follow this process:
1. For each trait: Score = interviewer's raw score (already provided above as X/10)
2. Compute weighted_avg = sum(trait_score × criticality_weight) / sum(criticality_weights). Assign criticality weights 1-3 per trait based on stressor relevance.
3. composite_psych_score = round(weighted_avg × 10, adjusted for risk: subtract 5-15 if HIGH risk, subtract 0-5 if MEDIUM)
4. The final composite_psych_score MUST be a single integer. DO NOT use 62, 68, 74, 75, or 76."""

    return await _call_llm(system_prompt, user_prompt)


async def analyze_resume(
    resume_text: str,
    jd_purpose: str,
    jd_responsibilities: list,
    jd_experience: list,
    role_title: str,
    level: str,
    business_unit: str,
    custom_rules: dict = None,
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
- CRITICAL: For social links (github), DO NOT guess, makeup, or hallucinate URLs. ONLY return the link if it is EXACTLY present in the text. If absent, you MUST return null.

Return ONLY valid JSON in this exact structure:
{
  "candidate_name": "Full name extracted from resume, or 'Unknown Candidate' if not found",
  "candidate_email": "email@domain.com or null",
  "candidate_current_role": "Current job title and company from resume, or null",
  "social_links": {
    "github": "EXTRACT EXACT FULL GitHub URL from text. DO NOT GUESS. If none, return null"
  },
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

    if custom_rules and custom_rules.get("enabled"):
        sections = custom_rules.get("sections", [])
        if sections:
            weights_text = "\n".join(f"- {s['name']}: {s['weight_percentage']}% weight" for s in sections)
            system_prompt += f"""\n\nCRITICAL HR EVALUATION RULES IN EFFECT:
The hiring manager has overridden default scoring. You MUST calculate `resume_score` exactly according to the following weighted sections:
{weights_text}

SCORING FORMULA (Crucial for Mathematical Accuracy):
1. Evaluate the candidate independently out of 10 for each defined section.
2. Multiply each score by its equivalent decimal weight (e.g., if weight is 40%, multiply by 0.4).
3. Sum these weighted values together to get the final `resume_score` (must be a float between 0.0 and 10.0). Example: (8 * 0.4) + (7 * 0.6) = 7.4.
4. The final `resume_score` MUST strictly use this computed average. Do not inflate it."""

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
    jd_text: str, role_title: str, level: str, business_unit: str, num_questions: int = 10,
    question_type: str = "Scenario",
    distribution: dict = None
) -> dict:
    """
    Generate a role-calibrated MCQ test.
    question_type: Scenario | Conventional | Math & Aptitude | Behavioral | Hybrid
    distribution: dict with keys like {"scenario": 3, "behavioral": 3, "math": 2, "conventional": 2}
    """
    # Build type-specific instructions
    type_instructions = {
        "Scenario": """Create highly realistic, stressful, or ambiguous SCENARIO-BASED questions specific to THIS role's context.
Each scenario should be 2-3 sentences describing a complex workplace situation the candidate would face in this role.
Every option represents a valid but distinct behavioral archetype (e.g., Risk-averse vs. Risk-seeking, Collaborative vs. Autocratic).""",
        "Conventional": """Create CONVENTIONAL psychometric questions — direct questions about personality, preferences, and work style.
These are straightforward self-report items like "How do you typically handle conflict?" or "What best describes your approach to deadlines?"
Each option represents a different personality dimension.""",
        "Math & Aptitude": """Create MATH & APTITUDE questions — numerical reasoning, logical puzzles, pattern recognition, and analytical word problems.
Each question should test quantitative or logical thinking relevant to this role's decision-making demands.
Options must have exactly ONE correct answer. Tag the correct option with "correct": true.""",
        "Behavioral": """Create BEHAVIORAL interview-style questions — "Tell me about a time when..." style questions rephrased as MCQs.
Each question should ask how the candidate WOULD behave in a specific work situation tied to this role.
Options should represent different behavioral responses from passive to proactive.""",
        "Logical Reasoning": """Create LOGICAL REASONING questions — deductive logic, syllogisms, pattern sequences, if-then reasoning, and analytical argument evaluation.
Each question should test the candidate's ability to think critically, identify logical fallacies, evaluate arguments, or solve abstract reasoning problems relevant to the role.
Options must have exactly ONE correct answer. Tag the correct option with "correct": true.""",
    }

    if question_type == "Hybrid" and distribution:
        # Build mixed instructions
        parts = []
        for qtype, count in distribution.items():
            label = qtype.replace("_", " ").title()
            if label in type_instructions and count > 0:
                parts.append(f"\n--- Generate exactly {count} {label.upper()} questions ---\n{type_instructions[label]}")
            elif label.lower() == "math & aptitude" and count > 0:
                parts.append(f"\n--- Generate exactly {count} MATH & APTITUDE questions ---\n{type_instructions['Math & Aptitude']}")
            elif count > 0:
                # Fallback for unmapped types
                mapped = label if label in type_instructions else "Scenario"
                parts.append(f"\n--- Generate exactly {count} {label.upper()} questions ---\n{type_instructions.get(mapped, type_instructions['Scenario'])}")
        type_block = "\n".join(parts)
    else:
        instr = type_instructions.get(question_type, type_instructions["Scenario"])
        type_block = f"ALL {num_questions} questions must follow this style:\n{instr}"

    system_prompt = f"""You are EOS-IA, an elite psychometric intelligence system.
Your task: Generate exactly {num_questions} hyper-specific multiple-choice questions for the following role.

QUESTION TYPE INSTRUCTIONS:
{type_block}

General Rules:
1. Do NOT ask generic questions ("What is your greatest weakness?").
2. Each question must have exactly 4 options (A, B, C, D).
3. For behavioral/scenario/conventional types: Do NOT mark a "correct" answer. Every option must represent a valid but distinct behavioral archetype.
4. For Math & Aptitude types: There IS one correct answer. Mark it with "correct": true in that option object.
5. The options must be subtle; no obviously bad answers (except Math where one answer is correct).
6. Each question must have a "trait_assessed" field describing what it evaluates.
7. CRITICAL: The question text MUST be named exactly "scenario" in the JSON, even if it is a Math problem or a Direct question. Do NOT rename the key to "question" or "text".
8. CRITICAL: DO NOT LEAK META-DATA. NEVER put the string ", correct: true" inside the actual "text" or "scenario" strings! The "correct": true flag must be a separate boolean key-value pair as a standard JSON property INSIDE the option object, NEVER embedded in the question text.

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "id": "q_1",
      "trait_assessed": "Risk Tolerance vs. Governance",
      "scenario": "The actual question text (scenario/problem statement/direct question) EVERY question MUST use this exact key.",
      "question_type": "Scenario",
      "options": [
        {{ "id": "A", "text": "Option text" }},
        {{ "id": "B", "text": "Option text" }},
        {{ "id": "C", "text": "Option text" }},
        {{ "id": "D", "text": "Option text" }}
      ]
    }}
  ]
}}"""

    user_prompt = f"""Role: {role_title} | Level: {level} | BU: {business_unit}

JOB DESCRIPTION CONTEXT:
{jd_text}

Generate {num_questions} questions now."""

    return await _call_llm(system_prompt, user_prompt)



async def analyze_psychometric_mcq_submission(
    jd_text: str, role_title: str, test_data: dict, submission_data: dict
) -> dict:
    """
    Analyze the candidate's chosen answers AND the behavioral telemetry (time spent).
    Returns a full FitmentReport structure with accurate, non-biased scoring.
    """
    system_prompt = """You are EOS-IA, an elite psychometric intelligence system used by top-tier executive search firms (Korn Ferry, Egon Zehnder, McKinsey Talent).

Your task: Perform a RIGOROUS, DATA-DRIVEN analysis of a candidate's psychometric test submission.

You must analyze THREE critical dimensions:
1. THE DECISION — Which option they chose and what behavioral archetype it maps to.
2. THE ALTERNATIVES — What they did NOT choose reveals equally important signals.
3. THE BEHAVIORAL TELEMETRY — Response timing in milliseconds reveals unconscious decision patterns.

═══ TELEMETRY INTERPRETATION RUBRIC ═══
• Ultra-fast (< 3000ms): Gut-instinct / impulsive / didn't read fully → PENALIZE on complex scenarios
• Fast (3000-8000ms): Quick pattern recognition OR superficial reading → Context-dependent
• Measured (8000-20000ms): Deliberate, confident decision-making → NEUTRAL to POSITIVE
• Slow (20000-40000ms): Careful analysis OR indecision → Role-dependent (good for governance roles, bad for execution roles)
• Very slow (> 40000ms): Overthinking, analysis paralysis, freezing under pressure → PENALIZE for leadership/execution roles
• Skipped (0ms or missing response): Candidate avoided the question entirely → STRONG NEGATIVE signal

═══ SCORING SYSTEM (CRITICAL — READ CAREFULLY) ═══
Each trait score must be 1.0 to 10.0 with genuine variance:
• 1.0-3.0: Candidate's responses actively CONTRADICT what this role demands. Red flag.
• 3.1-5.0: Weak alignment. Candidate shows opposing behavioral tendencies to what the role needs.
• 5.1-6.5: Below average. Some alignment but significant gaps or concerning patterns.
• 6.6-7.5: Average. Adequate but not differentiated. Would survive but not excel.
• 7.6-8.5: Strong alignment. Clear behavioral fit with minor development areas.
• 8.6-10.0: Exceptional. Near-perfect behavioral alignment for this exact role's demands.

DO NOT cluster all scores between 7-9. Use the FULL range. If a candidate chose risk-averse options for a role demanding bold decision-making, their "Risk Tolerance" should be 2-4, NOT 7.

═══ COMPOSITE SCORE FORMULA ═══
composite_psych_score (0-100) is calculated by:
1. Weight each trait by its CRITICALITY for this specific role (inferred from JD)
2. Apply telemetry modifiers: consistent <3000ms across questions = -5 to -15 points, consistent >40000ms = -3 to -10 points
3. Apply pattern penalty: If the behavioral pattern cluster is "negative" sentiment, cap score at 55
4. Distribution enforcement: Scores of exactly 74, 75, or 76 are FORBIDDEN — these are lazy defaults

═══ VERDICT RULES ═══
• GO: composite_psych_score >= 78 AND risk level is LOW AND no critical trait below 5.0
• CONDITIONAL GO: composite_psych_score 55-77, OR risk is MEDIUM, OR 1 critical trait below 5.0
• NO-GO: composite_psych_score < 55, OR risk is HIGH, OR 2+ critical traits below 4.0, OR pattern sentiment is "negative" with score < 65

Return ONLY valid JSON matching this exact structure:
{
  "trait_matrix": [
    {
      "trait": "Exact trait name from the test question (e.g., Decisiveness under ambiguity)",
      "score": "<1.0 to 10.0 — calculate based on actual response data, use FULL range>",
      "interpretation": "3-4 sentences: (1) What their chosen option reveals about this trait. (2) What they rejected reveals. (3) How their response time modifies the interpretation. (4) How this maps to the specific JD demands."
    }
  ],
  "pattern_cluster": {
    "name": "Precise archetype (e.g., Hesitant Analyst, Impulsive Executor, Governance Shield, Collaborative Strategist, Reactive Firefighter)",
    "description": "3-4 sentences describing their overall behavioral fingerprint — the intersection of ALL their choices and timing patterns. Include specific references to their actual responses.",
    "sentiment": "positive | neutral | negative"
  },
  "risk": {
    "level": "LOW | MEDIUM | HIGH",
    "statement": "One-line core behavioral risk based on actual response data",
    "role_specific_risk": "3 sentences: How this specific behavioral pattern will create friction or failure inside THIS specific role, referencing specific JD requirements that conflict with their demonstrated tendencies."
  },
  "verdict": {
    "decision": "GO | CONDITIONAL GO | NO-GO",
    "rationale": "3-4 sentences justifying using specific data points from their responses — cite specific questions, choices, and timing.",
    "coaching_note": "2-3 actionable sentences: If GO — what to watch post-hire. If CONDITIONAL GO — exact development plan needed. If NO-GO — the disqualifying behavioral evidence."
  },
  "composite_psych_score": "<CALCULATE: 0-100 based on weighted trait scores, telemetry, and risk. DO NOT copy any number from this example — derive it from actual candidate data above.>"
}

CRITICAL: The composite_psych_score MUST be a raw integer (not a string). The placeholder above is just to show you must CALCULATE it yourself.
ANTI-ANCHORING RULE: You are FORBIDDEN from outputting 62, 68, 74, 75, or 76 as composite_psych_score. These are known anchor values. Calculate the real score from the data."""

    # Reconstruct the candidate's journey with FULL option context
    responses_mapped = []
    questions_dict = {q['id']: q for q in test_data.get('questions', [])}
    
    answered_count = 0
    skipped_count = 0
    total_time = 0
    
    for resp in submission_data.get('responses', []):
        q_id = resp.get('question_id')
        q = questions_dict.get(q_id)
        if q:
            selected_id = resp.get('selected_option_id')
            chosen_opt = next((o for o in q['options'] if o['id'] == selected_id), None)
            time_ms = resp.get('time_spent_ms', 0)
            total_time += time_ms
            
            if chosen_opt:
                answered_count += 1
            else:
                skipped_count += 1
            
            # Show ALL options so AI knows what was rejected
            all_options_text = "\n".join(
                f"    {'→ CHOSEN →' if o['id'] == selected_id else '           '} {o['id']}. {o['text']}"
                for o in q['options']
            )
            
            responses_mapped.append(f"""
━━━ Question: {q['scenario']}
    Trait Assessed: {q['trait_assessed']}
    Question Type: {q.get('question_type', 'Scenario')}
    Response Time: {time_ms}ms ({
        'ULTRA-FAST — possible impulsive' if time_ms < 3000 else
        'FAST' if time_ms < 8000 else
        'MEASURED' if time_ms < 20000 else
        'SLOW — possible overthinking' if time_ms < 40000 else
        'VERY SLOW — analysis paralysis risk'
    })
    Options Available:
{all_options_text}
    Candidate's Decision: {'CHOSE ' + chosen_opt['id'] + ' — ' + chosen_opt['text'] if chosen_opt else '⚠️ SKIPPED / NO ANSWER'}""")

    # Identify questions that were never answered (not in responses at all)
    responded_q_ids = {r.get('question_id') for r in submission_data.get('responses', [])}
    for q_id, q in questions_dict.items():
        if q_id not in responded_q_ids:
            skipped_count += 1
            responses_mapped.append(f"""
━━━ Question: {q['scenario']}
    Trait Assessed: {q['trait_assessed']}
    ⚠️ COMPLETELY SKIPPED — Candidate did not answer this question at all.""")

    user_prompt = f"""Role: {role_title}

JOB DESCRIPTION CONTEXT:
{jd_text}

═══ ASSESSMENT STATISTICS ═══
• Total Questions: {len(questions_dict)}
• Answered: {answered_count}
• Skipped/Unanswered: {skipped_count}
• Total Assessment Time: {total_time}ms ({total_time // 1000}s / {total_time // 60000}min)
• Average Time Per Answered Question: {total_time // max(answered_count, 1)}ms

═══ CANDIDATE'S COMPLETE ASSESSMENT JOURNEY ═══
{''.join(responses_mapped)}

═══ ANALYSIS INSTRUCTION ═══
Based on the above data, generate the Fitment Report JSON.

SCORING FORMULA — You MUST follow this process:
1. For each trait: assess behavioral alignment (1-10) based on CHOSEN option + REJECTED options + response time
2. Compute weighted_avg = sum(trait_score × criticality_weight) / sum(criticality_weights). Assign criticality weights 1-3 per trait based on JD relevance.
3. Apply modifiers: avg response time <3000ms → subtract 5-10 points. Skipped questions → subtract 5 per skip.
4. composite_psych_score = round(weighted_avg × 10 + modifiers)
5. The final composite_psych_score MUST be a single integer. DO NOT use 62, 68, 74, 75, or 76.
6. Reference specific questions and response times in your interpretations.
7. If {skipped_count} questions were skipped, this is a MAJOR negative signal.
8. CRITICAL: You MUST generate exactly ONE entry in the `trait_matrix` array for EVERY UNIQUE "Trait Assessed" present in the candidate's assessment journey below. Do not combine, skip, or omit any traits!"""

    return await _call_llm(system_prompt, user_prompt)

# ── DASHBOARD AI TOOLS (Recruiter Facing) ──────────────────────────

async def generate_jd_questions(job_description: str) -> dict:
    system_prompt = """You are an expert HR Technical Recruiter. Your task is to analyze the following Job Description (JD) and generate a highly structured, professional set of 8-12 interview questions tailored specifically to the requirements and responsibilities outlined in the JD.

For each question, assign it to ONE of the following precise categories: Technical, Behavioral, Problem Solving, Aptitude, Managerial, Communication, Cultural Fit, Leadership, Domain Knowledge, System Design, Math & Logical. Ensure there is a good mix of categories represented.

You MUST respond strictly with a valid JSON object containing a single key "questions" which is an array of objects. Do not include any markdown formatting or explanations.

Example required format:
{
  "questions": [
    {
      "id": "unique-string-1",
      "text": "How do you approach debugging complex technical issues in [Technology from JD]?",
      "category": "Technical"
    }
  ]
}"""
    user_prompt = f"Please generate interview questions based on this Job Description:\n\n{job_description}"
    return await _call_llm(system_prompt, user_prompt)


async def enhance_partial_jd(raw_jd: str, existing_jd: dict = None) -> dict:
    existing_context = f"CRITICAL CONTEXT: The user is requesting modifications to an EXISTING Job Description. Here is the current Job Description:\n{existing_jd}\nYou must ONLY modify the specific sections requested by the user. Keep everything else identical."
    new_context = "CRITICAL CONTEXT: You are creating a NEW Job Description from scratch."
    
    system_prompt = f"""You are an Elite Executive Technical Recruiter at a FAANG tier company. You write highly professional, expansive, and deeply engaging Job Descriptions. Your task is to process the user's input and return a fully structured Job Description.

{existing_context if existing_jd else new_context}

OUTPUT REQUIREMENTS:
- "purpose": 4-6 highly professional sentences.
- "education": 4+ rigorous bullet points.
- "experience": 6+ highly descriptive bullet points.
- "responsibilities": 8-10 expansive, action-oriented bullet points.
- "skills": 10+ specific hard and soft skills.
- "non_negotiables": 2-4 absolute MUST-HAVE requirements that are critical dealbreakers for this role. These are the non-negotiable criteria that a candidate MUST meet — no exceptions. Examples: specific certifications, minimum years of experience, mandatory technologies, security clearances, etc. Be very specific and role-relevant.

Required JSON format:
{{
  "purpose": "string",
  "education": ["string", "string"],
  "experience": ["string", "string"],
  "responsibilities": ["string", "string"],
  "skills": ["string", "string"],
  "non_negotiables": ["string", "string"]
}}"""
    user_prompt = f"Please modify the job description according to these instructions:\n\n{raw_jd}" if existing_jd else f"Please enhance and structure this raw Job Description:\n\n{raw_jd}"
    return await _call_llm(system_prompt, user_prompt)


async def enhance_full_jd(raw_jd: str) -> dict:
    system_prompt = """You are an Elite Executive Technical Recruiter at a FAANG tier company. You write highly professional, expansive, and deeply engaging Job Descriptions. 
Your task is to take an ENTIRE existing, potentially unformatted, messy, or basic Job Description provided by the user, and completely rewrite it to an elite FAANG standard.

Required JSON format:
{
  "purpose": "string",
  "education": ["string", "string"],
  "experience": ["string", "string"],
  "responsibilities": ["string", "string"],
  "skills": ["string", "string"],
  "non_negotiables": ["string", "string"]
}

IMPORTANT: The "non_negotiables" field must contain 2-4 absolute MUST-HAVE requirements that are critical dealbreakers for this role. These are the non-negotiable criteria that a candidate MUST meet — no exceptions. Examples: specific certifications, minimum years of experience, mandatory technologies, security clearances, etc. Be very specific and role-relevant."""
    user_prompt = f"Please completely restructure and enhance this raw Job Description into an elite format:\n\n{raw_jd}"
    return await _call_llm(system_prompt, user_prompt)


async def generate_non_negotiables(role_title: str, level: str, jd_purpose: str, jd_skills: list, jd_experience: list, custom_instruction: str = "") -> dict:
    """
    Generate ONLY non-negotiable requirements for a JD.
    Completely isolated — does NOT modify any other JD field.
    """
    system_prompt = """You are an elite HR Talent Intelligence system. Your ONLY task is to generate non-negotiable requirements for a specific role.

Non-negotiables are absolute MUST-HAVE criteria that a candidate MUST meet — no exceptions. These are dealbreakers.
Examples: mandatory certifications, minimum years of experience in specific technologies, required security clearances, regulatory compliance knowledge, etc.

Rules:
1. Generate exactly 3-5 non-negotiable requirements.
2. Each must be specific, measurable, and directly tied to the role.
3. Do NOT include generic soft skills (e.g., "good communication"). Only hard, verifiable requirements.
4. If the user provides custom instructions, follow them to tailor the non-negotiables.

Return ONLY valid JSON:
{
  "non_negotiables": ["requirement 1", "requirement 2", "requirement 3"]
}"""

    custom_block = f"\\n\\nHR CUSTOM INSTRUCTION: {custom_instruction}" if custom_instruction.strip() else ""

    user_prompt = f"""Role: {role_title} | Level: {level}

JD PURPOSE:
{jd_purpose}

KEY SKILLS:
{', '.join(jd_skills[:15]) if jd_skills else 'Not specified'}

EXPERIENCE REQUIREMENTS:
{chr(10).join(f'- {e}' for e in jd_experience[:5]) if jd_experience else 'Not specified'}
{custom_block}

Generate the non-negotiable requirements for this role."""

    return await _call_llm(system_prompt, user_prompt)


async def generate_structured_interview_questions(
    job_description: str,
    role: str,
    level: str,
    category: str,
    easy: int,
    medium: int,
    hard: int,
    existing_questions: list = None
) -> dict:
    total = easy + medium + hard
    if total == 0:
        return {"questions": []}
        
    system_prompt = f"""You are an elite HR Technical Recruiter at a FAANG-level organization. Generate exactly {total} highly professional "{level}" interview questions for the role of **"{role}"**.

LEVEL: {level}
CATEGORY: {category}
DIFFICULTY: {easy} Easy, {medium} Medium, {hard} Hard.

RULES: All {total} questions must be specifically in the "{category}" category and derived from the JD context.

Required format:
{{
  "questions": [
    {{
      "id": "unique-string",
      "text": "Your question text?",
      "category": "{category}",
      "difficulty": "Easy"
    }}
  ]
}}"""
    if existing_questions:
        system_prompt += f"\n\nCRITICAL - DO NOT REPEAT: The following questions already exist: {[q.get('text') for q in existing_questions]!s}"

    user_prompt = f"Generate exactly {total} {level} \"{category}\" interview questions ({easy} Easy, {medium} Medium, {hard} Hard) based on this Job Description for the \"{role}\" role:\n\n{job_description}"
    return await _call_llm(system_prompt, user_prompt)

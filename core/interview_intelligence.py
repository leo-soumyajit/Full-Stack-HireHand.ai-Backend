"""
InterviewIQ — LangChain-powered AI Interview Intelligence Engine.
Completely isolated from the main AI system with its own API key.
"""
import json
import os
import httpx
import asyncio
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════
# ISOLATED AI CONFIG — Separate key to avoid shared rate limits
# ══════════════════════════════════════════════════════════════════════
INTERVIEW_AI_KEY = os.getenv("INTERVIEW_AI_KEY", "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")
INTERVIEW_AI_MODEL = os.getenv("INTERVIEW_AI_MODEL", "openai/gpt-4o-mini")
INTERVIEW_AI_URL = os.getenv("INTERVIEW_AI_URL", "https://openrouter.ai/api/v1/chat/completions")


async def _call_interview_llm(system_prompt: str, user_prompt: str, retries: int = 3) -> dict:
    """Call the dedicated interview AI with retry logic. Returns parsed JSON."""
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    INTERVIEW_AI_URL,
                    headers={
                        "Authorization": f"Bearer {INTERVIEW_AI_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://hirehand.ai",
                        "X-Title": "HireHand InterviewIQ",
                    },
                    json={
                        "model": INTERVIEW_AI_MODEL,
                        "route": "fallback",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )

                if resp.status_code in (401, 402, 403):
                    raise ValueError(f"InterviewIQ API key error ({resp.status_code})")

                if resp.status_code in (429, 503) or resp.status_code >= 500:
                    print(f"⚠️ InterviewIQ attempt {attempt}/{retries} — {resp.status_code}")
                    last_error = f"Status {resp.status_code}"
                    if attempt < retries:
                        await asyncio.sleep(3.0 * attempt)
                        continue
                    raise ValueError(f"InterviewIQ service unavailable ({resp.status_code})")

                if resp.status_code == 400:
                    try:
                        err_msg = resp.json().get("error", {}).get("message", "")
                    except Exception:
                        err_msg = resp.text[:200]
                    transient_kw = ["provider", "model output", "try again", "empty", "timeout", "overloaded"]
                    if any(kw in err_msg.lower() for kw in transient_kw) and attempt < retries:
                        last_error = err_msg
                        await asyncio.sleep(2.0 * attempt)
                        continue
                    raise ValueError(f"InterviewIQ error: {err_msg[:150]}")

                if resp.status_code >= 400:
                    raise ValueError(f"InterviewIQ error ({resp.status_code})")

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    if attempt < retries:
                        last_error = "Empty response"
                        continue
                    raise ValueError("InterviewIQ returned empty response")

                content = choices[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    if attempt < retries:
                        last_error = "Empty content"
                        continue
                    raise ValueError("InterviewIQ returned empty content")

                content = _extract_json(content)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    if attempt < retries:
                        last_error = "Invalid JSON"
                        continue
                    raise ValueError("InterviewIQ returned invalid JSON")

        except httpx.TimeoutException:
            last_error = "Timeout"
            if attempt < retries:
                continue
            raise ValueError("InterviewIQ request timed out")
        except httpx.ConnectError:
            raise ValueError("Could not connect to InterviewIQ service")
        except ValueError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                continue
            raise ValueError(f"InterviewIQ error: {str(e)[:100]}")

    raise ValueError(f"InterviewIQ failed after {retries} attempts: {last_error}")


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


# ══════════════════════════════════════════════════════════════════════
# CHAIN 1: TRANSCRIPT PARSER
# ══════════════════════════════════════════════════════════════════════
async def parse_transcript(raw_transcript: str) -> dict:
    """Parse raw transcript into structured Q&A pairs with speaker labels."""
    system_prompt = """You are an expert interview transcript parser. Your task is to take a raw interview transcript and structure it into clear question-answer pairs.

Rules:
1. Identify who is the INTERVIEWER and who is the CANDIDATE based on context clues (who asks questions vs who answers)
2. Extract each question asked by the interviewer and the candidate's corresponding answer
3. Preserve the natural conversation flow
4. If the transcript is informal or partially captured, do your best to structure it
5. Estimate confidence of speaker identification

Return ONLY valid JSON:
{
  "parsed_qa": [
    {
      "question_number": 1,
      "interviewer_question": "The question asked by the interviewer",
      "candidate_answer": "The candidate's answer",
      "topic_category": "Technical | Behavioral | Situational | General | Introduction | Closing"
    }
  ],
  "total_questions": 8,
  "total_duration_estimate": "Based on transcript length, estimate interview duration",
  "conversation_quality": "HIGH | MEDIUM | LOW — based on depth, back-and-forth, and specificity",
  "key_topics_discussed": ["topic1", "topic2", "topic3"],
  "speaker_identification_confidence": "HIGH | MEDIUM | LOW"
}"""

    user_prompt = f"""Parse this interview transcript into structured Q&A pairs:

--- TRANSCRIPT START ---
{raw_transcript[:8000]}
--- TRANSCRIPT END ---

Extract all question-answer pairs and categorize them."""

    return await _call_interview_llm(system_prompt, user_prompt)


# ══════════════════════════════════════════════════════════════════════
# CHAIN 2: COMPETENCY ANALYZER
# ══════════════════════════════════════════════════════════════════════
async def analyze_competencies(parsed_qa: dict, jd_text: str, role_title: str) -> dict:
    """Analyze candidate competencies based on their interview answers mapped to JD requirements."""
    system_prompt = """You are an elite talent assessment AI used by McKinsey, Korn Ferry, and top executive search firms.

Your task: Analyze a candidate's interview answers against a specific Job Description and produce a rigorous competency assessment.

SCORING RULES (CRITICAL):
- Use the FULL 1.0-10.0 range with genuine variance
- 1-3: Answers actively contradict what role demands. Clear deficiency.
- 4-5: Weak. Some relevant experience but major gaps evident.
- 6-7: Adequate. Meets minimum bar but not differentiated.
- 8-9: Strong. Clear evidence of relevant expertise and behavioral fit.
- 10: Exceptional. Rare, elite-level responses with concrete evidence.
- DO NOT cluster all scores between 7-8. Use the FULL range based on evidence.

Return ONLY valid JSON:
{
  "technical_competencies": [
    {
      "skill": "Specific technical skill from JD",
      "score": 7.5,
      "evidence": "Specific quote or reference from their answer that demonstrates this",
      "gap": "What was missing or could be stronger"
    }
  ],
  "behavioral_competencies": [
    {
      "trait": "Leadership / Communication / Problem-Solving / etc.",
      "score": 6.8,
      "evidence": "Behavioral evidence from their answers",
      "star_adherence": "Did they use STAR method? Situation-Task-Action-Result analysis"
    }
  ],
  "communication_score": {
    "clarity": 7.5,
    "confidence": 8.0,
    "articulation": 7.0,
    "listening_skills": 6.5,
    "overall": 7.3,
    "notes": "Brief assessment of communication quality"
  },
  "red_flags": ["Any concerning patterns in answers"],
  "standout_moments": ["Particularly impressive responses or insights"],
  "overall_competency_score": 72
}"""

    qa_text = "\n".join(
        f"Q{qa['question_number']}: [{qa['topic_category']}] {qa['interviewer_question']}\nA: {qa['candidate_answer']}\n"
        for qa in parsed_qa.get("parsed_qa", [])
    )

    user_prompt = f"""ROLE: {role_title}

JOB DESCRIPTION:
{jd_text[:3000]}

KEY TOPICS DISCUSSED: {', '.join(parsed_qa.get('key_topics_discussed', []))}

INTERVIEW Q&A:
{qa_text}

Analyze the candidate's competencies against this JD. Be rigorous and evidence-based."""

    return await _call_interview_llm(system_prompt, user_prompt)


# ══════════════════════════════════════════════════════════════════════
# CHAIN 3: ROLE-FIT SCORER + DUAL REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════
async def generate_full_reports(
    parsed_qa: dict,
    competencies: dict,
    jd_text: str,
    role_title: str,
    candidate_name: str,
    duration_seconds: int,
) -> dict:
    """Generate comprehensive reports for interviewer, candidate, and interviewer quality assessment."""
    system_prompt = """You are InterviewIQ, an elite AI interview intelligence system. You produce three comprehensive reports from interview data.

═══ REPORT 1: INTERVIEWER REPORT (Recruiter-Facing) ═══
This is the hiring manager's decision document. Must be data-driven with specific evidence.

═══ REPORT 2: CANDIDATE FEEDBACK REPORT ═══
This helps the candidate understand their performance and grow. Must be constructive yet honest.

═══ REPORT 3: INTERVIEWER QUALITY ASSESSMENT ═══
This evaluates how well the INTERVIEW was conducted (question quality, coverage, fairness).

═══ SCORING RULES ═══
- role_fit_score: 0-100 based on overall alignment with JD
- FORBIDDEN scores: 74, 75, 76 (known lazy anchors)
- Use FULL range. A weak candidate should score 30-50, not 65.
- A strong candidate should score 80-95, not just 75.

═══ VERDICT RULES ═══
- STRONG HIRE: score >= 82, no red flags, strong evidence across competencies
- HIRE: score 70-81, minor gaps but overall positive
- HOLD: score 55-69, significant gaps needing clarification
- NO HIRE: score < 55, or critical red flags

Return ONLY valid JSON:
{
  "interviewer_report": {
    "executive_summary": "3-4 sentences summarizing the candidate's overall performance and recommendation",
    "role_fit_score": 78,
    "verdict": "STRONG HIRE | HIRE | HOLD | NO HIRE",
    "verdict_rationale": "3 sentences justifying the verdict with specific evidence from the interview",
    "competency_summary": {
      "technical_avg": 7.5,
      "behavioral_avg": 6.8,
      "communication_avg": 7.2,
      "overall_avg": 7.2
    },
    "key_strengths": [
      {"strength": "Specific strength", "evidence": "What in the interview demonstrated this"}
    ],
    "key_concerns": [
      {"concern": "Specific concern", "evidence": "What raised this concern", "severity": "LOW | MEDIUM | HIGH"}
    ],
    "recommended_next_steps": ["Next step 1", "Next step 2"],
    "salary_positioning": "Based on demonstrated experience, candidate appears to be at X level",
    "culture_fit_assessment": "2-3 sentences on likely cultural alignment"
  },
  "candidate_report": {
    "overall_performance": "2-3 sentences — how did the candidate do overall",
    "performance_score": 78,
    "grade": "A+ | A | B+ | B | C+ | C | D | F",
    "strengths": [
      {"area": "What they did well", "detail": "Specific feedback with actionable praise"}
    ],
    "improvements": [
      {"area": "What to improve", "detail": "Actionable advice for future interviews", "priority": "HIGH | MEDIUM | LOW"}
    ],
    "alternative_roles": [
      {"role": "Suggested role title", "reason": "Why this role might be a better fit based on demonstrated skills"}
    ],
    "interview_tips": [
      "Personalized tip 1 based on their actual performance",
      "Personalized tip 2"
    ],
    "skill_development": [
      {"skill": "Specific skill to develop", "resource_suggestion": "How to develop it"}
    ]
  },
  "interviewer_quality": {
    "question_quality_score": 7.5,
    "competency_coverage_percent": 80,
    "coverage_gaps": ["Competency areas from JD that were NOT assessed in the interview"],
    "question_diversity": "HIGH | MEDIUM | LOW — Did interviewer ask varied question types?",
    "bias_indicators": ["Any leading questions or evaluation concerns detected"],
    "interviewer_rating": 7.8,
    "interviewer_feedback": "2-3 sentences of constructive feedback for the interviewer",
    "best_question_asked": "The most effective question from the interview and why",
    "missed_opportunity": "What question SHOULD have been asked but wasn't"
  }
}"""

    competency_summary = f"""
COMPETENCY DATA:
- Technical Competencies: {json.dumps(competencies.get('technical_competencies', []), indent=2)[:1500]}
- Behavioral Competencies: {json.dumps(competencies.get('behavioral_competencies', []), indent=2)[:1500]}
- Communication: {json.dumps(competencies.get('communication_score', {}), indent=2)}
- Red Flags: {competencies.get('red_flags', [])}
- Standout Moments: {competencies.get('standout_moments', [])}
- Overall Competency Score: {competencies.get('overall_competency_score', 'N/A')}
"""

    qa_text = "\n".join(
        f"Q{qa['question_number']}: [{qa['topic_category']}] {qa['interviewer_question']}\nA: {qa['candidate_answer']}\n"
        for qa in parsed_qa.get("parsed_qa", [])
    )

    user_prompt = f"""CANDIDATE: {candidate_name}
ROLE: {role_title}
INTERVIEW DURATION: {duration_seconds // 60} minutes

JOB DESCRIPTION:
{jd_text[:2500]}

{competency_summary}

FULL INTERVIEW Q&A:
{qa_text[:3000]}

Generate all three reports (Interviewer Report, Candidate Feedback, Interviewer Quality Assessment)."""

    return await _call_interview_llm(system_prompt, user_prompt)


# ══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE — Runs all chains sequentially
# ══════════════════════════════════════════════════════════════════════
async def run_full_analysis_pipeline(
    transcript: str,
    jd_text: str,
    role_title: str,
    candidate_name: str,
    duration_seconds: int,
) -> dict:
    """
    Run the complete InterviewIQ analysis pipeline.
    Chain 1: Parse transcript → Chain 2: Analyze competencies → Chain 3: Generate reports.
    Returns the full combined result.
    """
    print(f"🧠 [InterviewIQ] Starting analysis pipeline for {candidate_name} — {role_title}")

    # ── Chain 1: Parse Transcript ─────────────────────────────────────
    print(f"🔗 [Chain 1/3] Parsing transcript...")
    parsed_qa = await parse_transcript(transcript)
    print(f"✅ [Chain 1/3] Parsed {parsed_qa.get('total_questions', 0)} Q&A pairs")

    # ── Chain 2: Analyze Competencies ─────────────────────────────────
    print(f"🔗 [Chain 2/3] Analyzing competencies...")
    competencies = await analyze_competencies(parsed_qa, jd_text, role_title)
    print(f"✅ [Chain 2/3] Competency analysis complete — score: {competencies.get('overall_competency_score', 'N/A')}")

    # ── Chain 3: Generate Full Reports ────────────────────────────────
    print(f"🔗 [Chain 3/3] Generating comprehensive reports...")
    reports = await generate_full_reports(
        parsed_qa=parsed_qa,
        competencies=competencies,
        jd_text=jd_text,
        role_title=role_title,
        candidate_name=candidate_name,
        duration_seconds=duration_seconds,
    )
    print(f"✅ [Chain 3/3] Reports generated — Verdict: {reports.get('interviewer_report', {}).get('verdict', 'N/A')}")

    # ── Combine all results ───────────────────────────────────────────
    return {
        "parsed_transcript": parsed_qa,
        "competency_analysis": competencies,
        "interviewer_report": reports.get("interviewer_report", {}),
        "candidate_report": reports.get("candidate_report", {}),
        "interviewer_quality": reports.get("interviewer_quality", {}),
    }

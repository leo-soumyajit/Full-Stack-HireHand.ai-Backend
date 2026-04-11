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
    system_prompt = """You are an expert interview transcript parser. Your ONLY job is to extract REAL question-answer pairs that ACTUALLY EXIST in the transcript.

CRITICAL RULES — FOLLOW STRICTLY:
1. The transcript may already contain explicit role labels like "Interviewer:" and "Candidate:". If present, TRUST these labels completely. Do NOT re-identify or swap speakers.
2. If no labels exist, identify speakers from context: the person asking short probing questions is the INTERVIEWER, the person giving longer descriptive answers is the CANDIDATE.
3. Extract ONLY questions and answers that ACTUALLY APPEAR in the transcript text. Do NOT invent, infer, or fabricate any Q&A pairs.
4. If a question was asked but the candidate gave no meaningful answer (just greetings, noise, or off-topic response), record the answer as "No substantive answer provided."
5. Do NOT reverse speaker roles midway through the transcript.
6. Combine fragmented sentences from the same speaker into coherent thoughts.

TRANSCRIPT QUALITY ASSESSMENT — Be brutally honest:
- HIGH: Clear back-and-forth interview with substantive technical/behavioral questions and detailed answers.
- MEDIUM: Some interview content but mixed with small talk, partial answers, or audio issues.
- LOW: Mostly greetings, small talk, or fragmented speech with very few real interview questions.
- INVALID: No real interview occurred. Transcript contains only noise, greetings, non-interview conversation, test audio, or gibberish. If INVALID, return parsed_qa as an EMPTY array [].

Return ONLY valid JSON:
{
  "parsed_qa": [
    {
      "question_number": 1,
      "interviewer_question": "The EXACT question from the transcript",
      "candidate_answer": "The EXACT answer from the transcript",
      "topic_category": "Technical | Behavioral | Situational | General | Introduction | Closing"
    }
  ],
  "total_questions": 0,
  "total_duration_estimate": "Estimate based on transcript length",
  "conversation_quality": "HIGH | MEDIUM | LOW | INVALID",
  "key_topics_discussed": [],
  "speaker_identification_confidence": "HIGH | MEDIUM | LOW"
}"""

    user_prompt = f"""Parse this interview transcript into structured Q&A pairs.
IMPORTANT: Only extract Q&A that ACTUALLY EXISTS in the text. If no real interview happened, return an empty parsed_qa array and set conversation_quality to INVALID.

--- TRANSCRIPT START ---
{raw_transcript[:20000]}
--- TRANSCRIPT END ---

Extract all real question-answer pairs and categorize them."""

    return await _call_interview_llm(system_prompt, user_prompt)


# ══════════════════════════════════════════════════════════════════════
# CHAIN 2: COMPETENCY ANALYZER
# ══════════════════════════════════════════════════════════════════════
async def analyze_competencies(parsed_qa: dict, jd_text: str, role_title: str) -> dict:
    """Analyze candidate competencies based on their interview answers mapped to JD requirements."""
    system_prompt = """You are an elite talent assessment AI used by McKinsey, Korn Ferry, and top executive search firms.

Your task: Analyze a candidate's ACTUAL interview answers against a specific Job Description. You must be ruthlessly evidence-based.

═══ ABSOLUTE RULES — VIOLATION IS UNACCEPTABLE ═══

1. EVIDENCE MUST BE VERBATIM: The "evidence" field MUST contain the candidate's EXACT words from the interview, enclosed in double quotes. Copy-paste their actual words. Do NOT paraphrase, summarize, or fabricate what they said.
2. NO EVIDENCE = SCORE 0: If the candidate did NOT discuss a particular skill or competency during the interview, you MUST set the score to 0.0 and write "NOT DISCUSSED IN INTERVIEW" as evidence. Do NOT guess or infer skills they didn't demonstrate.
3. NO SCORE CLUSTERING: Each score must be independently justified. Do NOT default all scores to the 6-8 range. If evidence is weak, score 2-4. If evidence is strong and specific, score 8-9. Score 10 only for genuinely exceptional, concrete demonstrations.
4. SCORE ONLY WHAT WAS SAID: Judge the candidate purely on what they actually said in the interview. Do NOT assume skills based on their resume, job title, or background. Only their spoken answers count.
5. RED FLAGS MUST BE REAL: Only flag patterns you can point to with exact transcript evidence. Do NOT invent red flags.
6. STANDOUT MOMENTS MUST BE REAL: Only cite moments with exact quotes. If no standout moment exists, return an empty array [].

═══ SCORING SCALE ═══
- 0: Not discussed at all in the interview. No evidence available.
- 1-3: Discussed but answers actively contradict role requirements or show clear misunderstanding.
- 4-5: Mentioned briefly but with major gaps, vague answers, or lack of depth.
- 6-7: Adequate demonstration with some relevant experience but not strongly differentiated.
- 8-9: Strong, specific, detailed answers with concrete examples and clear expertise.
- 10: Exceptional. Rare. Must have extraordinary depth with verifiable specifics.

Return ONLY valid JSON:
{
  "technical_competencies": [
    {
      "skill": "Specific technical skill from JD",
      "score": 0.0,
      "evidence": "EXACT quote from candidate OR 'NOT DISCUSSED IN INTERVIEW'",
      "gap": "What was missing or could be stronger"
    }
  ],
  "behavioral_competencies": [
    {
      "trait": "Leadership / Communication / Problem-Solving / etc.",
      "score": 0.0,
      "evidence": "EXACT quote from candidate OR 'NOT DISCUSSED IN INTERVIEW'",
      "star_adherence": "Did they use STAR method? Situation-Task-Action-Result analysis. If not discussed, write 'NOT ASSESSED'"
    }
  ],
  "communication_score": {
    "clarity": 0.0,
    "confidence": 0.0,
    "articulation": 0.0,
    "listening_skills": 0.0,
    "overall": 0.0,
    "notes": "Assessment based on HOW the candidate spoke — sentence structure, coherence, confidence. If insufficient data, state so."
  },
  "red_flags": [],
  "standout_moments": [],
  "overall_competency_score": 0
}"""

    qa_text = "\n".join(
        f"Q{qa['question_number']}: [{qa['topic_category']}] {qa['interviewer_question']}\nA: {qa['candidate_answer']}\n"
        for qa in parsed_qa.get("parsed_qa", [])
    )

    user_prompt = f"""ROLE: {role_title}

JOB DESCRIPTION:
{jd_text[:8000]}

KEY TOPICS DISCUSSED: {', '.join(parsed_qa.get('key_topics_discussed', []))}

INTERVIEW Q&A:
{qa_text}

Analyze the candidate's competencies against this JD.
REMINDER: Use ONLY verbatim quotes as evidence. Score 0 for anything not discussed. Do NOT fabricate or assume."""

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
    system_prompt = """You are InterviewIQ, an elite AI interview intelligence system. You produce three comprehensive reports STRICTLY based on interview evidence.

═══ ABSOLUTE RULES — APPLY TO ALL 3 REPORTS ═══
1. EVERY claim, strength, concern, and score MUST be backed by the candidate's EXACT words from the interview (verbatim quotes in double quotes).
2. Do NOT fabricate, infer, or assume anything the candidate did not explicitly say during the interview.
3. If the competency data shows "NOT DISCUSSED IN INTERVIEW" for a skill, that skill MUST be listed as a gap/concern, NOT as a strength.
4. If the majority of competencies show 0 scores or "NOT DISCUSSED", the candidate clearly did not demonstrate fitness for the role.

═══ REPORT 1: INTERVIEWER REPORT (Recruiter-Facing) ═══
This is the hiring manager's decision document. Must cite specific candidate quotes as evidence for every claim.

═══ REPORT 2: CANDIDATE FEEDBACK REPORT ═══
This helps the candidate understand their performance. Be constructive yet honest. Reference their actual answers.

═══ REPORT 3: INTERVIEWER QUALITY ASSESSMENT ═══
Evaluate the actual questions that were asked. Only reference questions that exist in the Q&A data. If few questions were asked, scores must be low.

═══ SCORING RULES (role_fit_score: 0-100) ═══
- The score MUST mathematically align with the competency averages from the input data.
- If overall competency average is below 3.0, role_fit_score MUST be below 35.
- If overall competency average is 3.0-5.0, role_fit_score MUST be 35-55.
- If overall competency average is 5.0-7.0, role_fit_score MUST be 55-75.
- If overall competency average is 7.0-8.5, role_fit_score MUST be 75-88.
- If overall competency average is above 8.5, role_fit_score MUST be 88-100.
- FORBIDDEN: Do NOT assign scores that contradict the competency data.

═══ VERDICT RULES ═══
- STRONG HIRE: role_fit_score >= 82, no red flags, strong verbatim evidence across competencies
- HIRE: role_fit_score 70-81, minor gaps but overall positive with evidence
- HOLD: role_fit_score 55-69, significant gaps needing clarification
- NO HIRE: role_fit_score < 55, or critical red flags, or majority of competencies not demonstrated

═══ INTERVIEWER QUALITY SCORING ═══
- question_quality_score: Based ONLY on the actual questions in the Q&A data. If questions were shallow or few, score low (1-4).
- competency_coverage_percent: Calculate as (number of JD competencies actually tested / total JD competencies) * 100.
- interviewer_rating: Must reflect actual interview quality. Poor coverage = low rating.
- best_question_asked: Must be an ACTUAL question from the Q&A data. If no good questions exist, write "No standout questions identified."

Return ONLY valid JSON:
{
  "interviewer_report": {
    "executive_summary": "3-4 sentences with verbatim evidence from candidate",
    "role_fit_score": 0,
    "verdict": "STRONG HIRE | HIRE | HOLD | NO HIRE",
    "verdict_rationale": "3 sentences with exact candidate quotes justifying the verdict",
    "competency_summary": {
      "technical_avg": 0.0,
      "behavioral_avg": 0.0,
      "communication_avg": 0.0,
      "overall_avg": 0.0
    },
    "key_strengths": [
      {"strength": "Specific strength", "evidence": "Verbatim candidate quote demonstrating this"}
    ],
    "key_concerns": [
      {"concern": "Specific concern", "evidence": "Verbatim quote or 'Not addressed in interview'", "severity": "LOW | MEDIUM | HIGH"}
    ],
    "recommended_next_steps": ["Evidence-based next step"],
    "salary_positioning": "Based on demonstrated (not assumed) experience level",
    "culture_fit_assessment": "Based ONLY on what candidate actually said about values, teamwork, etc."
  },
  "candidate_report": {
    "overall_performance": "2-3 sentences referencing their actual answers",
    "performance_score": 0,
    "grade": "A+ | A | B+ | B | C+ | C | D | F",
    "strengths": [
      {"area": "What they did well", "detail": "Specific feedback referencing their actual answer"}
    ],
    "improvements": [
      {"area": "What to improve", "detail": "Actionable advice based on gaps in their actual answers", "priority": "HIGH | MEDIUM | LOW"}
    ],
    "alternative_roles": [
      {"role": "Suggested role title", "reason": "Why, based on skills they actually demonstrated"}
    ],
    "interview_tips": [
      "Personalized tip based on their actual performance"
    ],
    "skill_development": [
      {"skill": "Specific skill to develop", "resource_suggestion": "How to develop it"}
    ]
  },
  "interviewer_quality": {
    "question_quality_score": 0.0,
    "competency_coverage_percent": 0,
    "coverage_gaps": ["JD competencies that were NOT tested by any question"],
    "question_diversity": "HIGH | MEDIUM | LOW",
    "bias_indicators": [],
    "interviewer_rating": 0.0,
    "interviewer_feedback": "Constructive feedback based on actual questions asked",
    "best_question_asked": "The actual best question from the Q&A data, or 'No standout questions identified'",
    "missed_opportunity": "What competency SHOULD have been tested but wasn't"
  }
}"""

    competency_summary = f"""
COMPETENCY DATA (from Chain 2 analysis):
- Technical Competencies: {json.dumps(competencies.get('technical_competencies', []), indent=2)[:4000]}
- Behavioral Competencies: {json.dumps(competencies.get('behavioral_competencies', []), indent=2)[:4000]}
- Communication: {json.dumps(competencies.get('communication_score', {}), indent=2)}
- Red Flags: {json.dumps(competencies.get('red_flags', []))}
- Standout Moments: {json.dumps(competencies.get('standout_moments', []))}
- Overall Competency Score: {competencies.get('overall_competency_score', 0)}
"""

    qa_text = "\n".join(
        f"Q{qa['question_number']}: [{qa['topic_category']}] {qa['interviewer_question']}\nA: {qa['candidate_answer']}\n"
        for qa in parsed_qa.get("parsed_qa", [])
    )

    user_prompt = f"""CANDIDATE: {candidate_name}
ROLE: {role_title}
INTERVIEW DURATION: {duration_seconds // 60} minutes

JOB DESCRIPTION:
{jd_text[:8000]}

{competency_summary}

FULL INTERVIEW Q&A:
{qa_text[:10000]}

Generate all three reports (Interviewer Report, Candidate Feedback, Interviewer Quality Assessment).
REMINDER: All evidence must be verbatim quotes. All scores must align with input competency data. Do NOT fabricate anything."""

    return await _call_interview_llm(system_prompt, user_prompt)


# ══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE — Runs all chains sequentially with guard rails
# ══════════════════════════════════════════════════════════════════════
async def run_full_analysis_pipeline(
    transcript: str,
    jd_text: str,
    role_title: str,
    candidate_name: str,
    duration_seconds: int,
) -> dict:
    """
    Run the complete InterviewIQ analysis pipeline with quality guard rails.
    Chain 1: Parse transcript → Quality Gate → Chain 2: Analyze competencies → Chain 3: Generate reports.
    Returns the full combined result.
    """
    print(f"🧠 [InterviewIQ] Starting analysis pipeline for {candidate_name} — {role_title}")

    # ── Chain 1: Parse Transcript ─────────────────────────────────────
    print(f"🔗 [Chain 1/3] Parsing transcript...")
    parsed_qa = await parse_transcript(transcript)
    total_q = parsed_qa.get('total_questions', 0)
    quality = parsed_qa.get('conversation_quality', 'INVALID').upper()
    print(f"✅ [Chain 1/3] Parsed {total_q} Q&A pairs — Quality: {quality}")

    # ── QUALITY GATE: Stop pipeline if transcript has no real interview ──
    qa_list = parsed_qa.get('parsed_qa', [])
    if quality == 'INVALID' or (total_q == 0 and len(qa_list) == 0):
        print(f"🛑 [InterviewIQ] INVALID transcript detected — aborting pipeline for {candidate_name}")
        raise ValueError(
            "Insufficient interview data: The transcript does not contain a real interview. "
            "No meaningful questions or answers were detected. Analysis cannot proceed."
        )

    # ── Chain 2: Analyze Competencies ─────────────────────────────────
    print(f"🔗 [Chain 2/3] Analyzing competencies...")
    competencies = await analyze_competencies(parsed_qa, jd_text, role_title)
    print(f"✅ [Chain 2/3] Competency analysis complete — score: {competencies.get('overall_competency_score', 0)}")

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

"""
HireHand AI Interviewer — LLM Conversation Orchestrator
═══════════════════════════════════════════════════════
Manages the AI interview conversation state, generates contextual questions,
handles follow-ups, and produces the final transcript for scoring.

100% ISOLATED — Does NOT modify any existing file.
Uses the same INTERVIEW_AI_KEY as interview_intelligence.py.
"""

import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════
# AI CONFIG — Uses the same isolated key as interview_intelligence.py
# ══════════════════════════════════════════════════════════════════════
INTERVIEW_AI_KEY = os.getenv("INTERVIEW_AI_KEY", "")
INTERVIEW_AI_MODEL = os.getenv("INTERVIEW_AI_MODEL", "openai/gpt-4o-mini")
INTERVIEW_AI_URL = os.getenv("INTERVIEW_AI_URL", "https://openrouter.ai/api/v1/chat/completions")


# ══════════════════════════════════════════════════════════════════════
# INTERVIEW TYPE PROMPTS
# ══════════════════════════════════════════════════════════════════════
TYPE_PROMPTS = {
    "technical": (
        "Focus on hands-on technical skills. Ask about architecture decisions, "
        "code quality, debugging approaches, system design, and scalability. "
        "Probe for SPECIFIC examples with tech stack details. Ask them to walk "
        "through real projects they've built."
    ),
    "behavioral": (
        "Use the STAR method (Situation-Task-Action-Result). Ask about real past "
        "experiences. Focus on leadership, conflict resolution, teamwork, failure "
        "recovery, and handling pressure. Always ask for specific examples."
    ),
    "managerial": (
        "Assess strategic thinking and people management. Ask about team building, "
        "performance reviews, stakeholder management, prioritization under pressure, "
        "and how they handle underperforming team members."
    ),
    "culture_fit": (
        "Understand the candidate's values and work style. Ask about their ideal "
        "work environment, collaboration preferences, growth mindset, handling "
        "feedback, and what motivates them."
    ),
    "hybrid": (
        "Balance questions across technical (40%), behavioral (30%), and "
        "culture fit (30%). Adapt based on the candidate's strengths and "
        "gaps as they emerge during the conversation."
    ),
}


def build_system_prompt(
    company_name: str,
    position_title: str,
    candidate_name: str,
    jd_text: str,
    interview_type: str = "hybrid",
    max_questions: int = 10,
    l1_questions: list[str] = None,
    focus_areas: list[str] = None,
    round_number: int = 1,
) -> str:
    """Build the system prompt for the AI interviewer based on interview config."""

    type_instruction = TYPE_PROMPTS.get(interview_type, TYPE_PROMPTS["hybrid"])

    questions_section = ""
    if l1_questions:
        q_list = "\n".join(f"  - {q}" for q in l1_questions[:15])
        questions_section = f"""
PRE-GENERATED QUESTIONS (use these as a starting guide, but adapt based on conversation):
{q_list}
"""

    focus_section = ""
    if focus_areas:
        focus_section = f"\nFOCUS AREAS: {', '.join(focus_areas)}"

    return f"""You are an expert AI interviewer for {company_name}, conducting a Round {round_number} interview for the role of {position_title}.

CANDIDATE: {candidate_name}

JOB DESCRIPTION:
{jd_text}
{questions_section}{focus_section}

INTERVIEW TYPE INSTRUCTION:
{type_instruction}

INTERVIEW RULES — FOLLOW STRICTLY:
1. Start with a warm, professional greeting. Introduce yourself as "HireHand AI". Welcome the candidate and briefly mention the role.
2. Ask ONE question at a time. Wait for the candidate's full response before continuing.
3. After each answer, decide: ask a FOLLOW-UP question that probes deeper, OR move to a new topic.
4. If the candidate gives a vague or incomplete answer, politely ask them to elaborate with a specific example.
5. Keep your responses concise (2-3 sentences max per turn). Do NOT give long monologues.
6. You must ask approximately {max_questions} questions total (including follow-ups).
7. Cover the key competencies from the job description. Track which areas you've already covered.
8. When all questions are done, conclude warmly: thank the candidate, tell them the team will review, and wish them well.
9. NEVER reveal scores, evaluations, or hints about their performance during the interview.
10. Maintain a conversational, supportive, professional tone — NOT robotic or interrogative.
11. If the candidate asks you a question about the role or company, give a brief helpful answer based on the JD, then continue with your next question.
12. DO NOT use markdown, emojis, bullet points, or any formatting. Speak in natural conversational English only.

OUTPUT: Return ONLY your spoken response as plain text. No JSON, no labels, no formatting."""


async def call_llm(messages: list[dict], retries: int = 3) -> str:
    """
    Call the LLM with the conversation history and return the AI's response text.
    Uses retry logic with exponential backoff.
    """
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    INTERVIEW_AI_URL,
                    headers={
                        "Authorization": f"Bearer {INTERVIEW_AI_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://hirehand.ai",
                        "X-Title": "HireHand AI Interviewer",
                    },
                    json={
                        "model": INTERVIEW_AI_MODEL,
                        "route": "fallback",
                        "messages": messages,
                        "max_tokens": 300,  # Keep responses concise
                        "temperature": 0.7,  # Natural variation
                    },
                )

                if resp.status_code in (401, 402, 403):
                    raise ValueError(f"AI API key error ({resp.status_code})")

                if resp.status_code in (429, 503) or resp.status_code >= 500:
                    last_error = f"Status {resp.status_code}"
                    if attempt < retries:
                        await asyncio.sleep(2.0 * attempt)
                        continue
                    raise ValueError(f"AI service unavailable ({resp.status_code})")

                if resp.status_code >= 400:
                    raise ValueError(f"AI error ({resp.status_code})")

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    if attempt < retries:
                        continue
                    raise ValueError("AI returned empty response")

                content = choices[0].get("message", {}).get("content", "").strip()
                if not content:
                    if attempt < retries:
                        continue
                    raise ValueError("AI returned empty content")

                return content

        except httpx.TimeoutException:
            last_error = "Timeout"
            if attempt < retries:
                continue
            raise ValueError("AI request timed out")
        except ValueError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                continue
            raise ValueError(f"AI error: {str(e)[:100]}")

    raise ValueError(f"AI failed after {retries} attempts: {last_error}")


class AIInterviewSession:
    """
    Manages the state of a single AI interview session.
    Tracks conversation history, question count, and generates responses.
    """

    def __init__(
        self,
        company_name: str,
        position_title: str,
        candidate_name: str,
        jd_text: str,
        interview_type: str = "hybrid",
        max_questions: int = 10,
        time_limit_minutes: int = 20,
        l1_questions: list[str] = None,
        focus_areas: list[str] = None,
        round_number: int = 1,
    ):
        self.company_name = company_name
        self.position_title = position_title
        self.candidate_name = candidate_name
        self.max_questions = max_questions
        self.time_limit_minutes = time_limit_minutes
        self.interview_type = interview_type
        self.round_number = round_number

        # Build system prompt
        self.system_prompt = build_system_prompt(
            company_name=company_name,
            position_title=position_title,
            candidate_name=candidate_name,
            jd_text=jd_text,
            interview_type=interview_type,
            max_questions=max_questions,
            l1_questions=l1_questions or [],
            focus_areas=focus_areas or [],
            round_number=round_number,
        )

        # Conversation history (for LLM context)
        self.messages: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

        # Transcript (for human-readable output)
        self.transcript_entries: list[dict] = []

        # Counters
        self.question_count = 0
        self.is_complete = False

    async def generate_greeting(self) -> str:
        """Generate the AI's opening greeting."""
        self.messages.append({
            "role": "user",
            "content": "The candidate has just joined. Please introduce yourself and start the interview with your first question."
        })

        response = await call_llm(self.messages)
        self.messages.append({"role": "assistant", "content": response})

        self.transcript_entries.append({
            "speaker": "Interviewer",
            "text": response,
        })

        self.question_count = 1
        return response

    async def process_candidate_answer(self, answer_text: str) -> str:
        """
        Process the candidate's answer and generate the AI's next response.
        Returns the AI's response text (could be a follow-up, new question, or closing).
        """
        if self.is_complete:
            return ""

        # Add candidate's answer to history
        self.messages.append({"role": "user", "content": answer_text})
        self.transcript_entries.append({
            "speaker": "Candidate",
            "text": answer_text,
        })

        # Check if we should end the interview
        if self.question_count >= self.max_questions:
            return await self._generate_closing()

        # Generate next response
        response = await call_llm(self.messages)
        self.messages.append({"role": "assistant", "content": response})

        self.transcript_entries.append({
            "speaker": "Interviewer",
            "text": response,
        })

        self.question_count += 1
        return response

    async def _generate_closing(self) -> str:
        """Generate a natural closing statement."""
        self.messages.append({
            "role": "user",
            "content": (
                "You have now asked all your questions. Please conclude the interview "
                "gracefully. Thank the candidate, let them know the team will review "
                "their responses, and wish them well. Keep it brief and warm."
            )
        })

        response = await call_llm(self.messages)
        self.messages.append({"role": "assistant", "content": response})

        self.transcript_entries.append({
            "speaker": "Interviewer",
            "text": response,
        })

        self.is_complete = True
        return response

    async def force_end(self) -> str:
        """Force-end the interview (candidate wants to leave or time's up)."""
        if self.is_complete:
            return ""
        return await self._generate_closing()

    def get_formatted_transcript(self) -> str:
        """
        Format the conversation into a transcript string suitable for
        the existing interview_intelligence analysis pipeline.
        """
        lines = []
        for entry in self.transcript_entries:
            speaker = entry["speaker"]
            text = entry["text"]
            lines.append(f"{speaker}: {text}")
        return "\n\n".join(lines)

    def get_transcript_entries(self) -> list[dict]:
        """Return transcript entries for saving to DB."""
        return self.transcript_entries.copy()

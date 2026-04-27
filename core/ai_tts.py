"""
HireHand AI TTS Engine — Deepgram Aura Text-to-Speech
═══════════════════════════════════════════════════════
Streams AI-generated text to Deepgram Aura TTS via WebSocket,
receives audio chunks, and forwards them to the client.

100% ISOLATED — Does NOT modify any existing file.
"""

import base64
import os
import re
import httpx
from typing import Optional, Callable, Awaitable

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# Available Deepgram Aura voices
AVAILABLE_VOICES = {
    "asteria": "aura-2-asteria-en",      # Professional female
    "luna": "aura-2-luna-en",             # Warm female
    "stella": "aura-2-stella-en",         # Clear female
    "orion": "aura-2-orion-en",           # Professional male
    "arcas": "aura-2-arcas-en",           # Warm male
}

DEFAULT_VOICE = "aura-2-asteria-en"


def get_voice_model(voice_key: str) -> str:
    """Resolve a voice key (e.g. 'asteria') to a Deepgram model ID."""
    return AVAILABLE_VOICES.get(voice_key.lower(), DEFAULT_VOICE)


def _split_into_sentences(text: str) -> list[str]:
    """Split text into natural sentence chunks for smooth TTS pacing."""
    # Split on sentence-ending punctuation followed by space or end-of-string
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out empty strings
    return [s.strip() for s in sentences if s.strip()]


async def synthesize_speech_rest(
    text: str,
    voice: str = DEFAULT_VOICE,
) -> Optional[bytes]:
    """
    Synthesize speech using Deepgram Aura REST API.
    Returns raw audio bytes (mp3 format).
    Falls back to REST if WebSocket is not needed.
    """
    if not DEEPGRAM_API_KEY:
        print("⚠️ [AI-TTS] DEEPGRAM_API_KEY not set — skipping TTS")
        return None

    url = f"https://api.deepgram.com/v1/speak?model={voice}&encoding=mp3"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            )

            if resp.status_code == 200:
                return resp.content
            else:
                print(f"❌ [AI-TTS] Deepgram REST error ({resp.status_code}): {resp.text[:200]}")
                return None

    except Exception as e:
        print(f"❌ [AI-TTS] TTS synthesis failed: {str(e)}")
        return None


async def stream_tts_to_client(
    text: str,
    send_audio_chunk: Callable[[str], Awaitable[None]],
    send_state: Callable[[str], Awaitable[None]],
    voice: str = DEFAULT_VOICE,
) -> None:
    """
    Stream TTS audio to the client.
    
    Splits text into sentences and synthesizes each one,
    sending audio chunks to the client for immediate playback.
    This creates a natural, low-latency speech experience.
    
    Args:
        text: The AI's response text to speak
        send_audio_chunk: Async callback to send base64-encoded audio to client
        send_state: Async callback to send state updates to client
        voice: Deepgram Aura voice model ID
    """
    if not text or not text.strip():
        return

    await send_state("speaking")

    sentences = _split_into_sentences(text)

    for sentence in sentences:
        audio_bytes = await synthesize_speech_rest(sentence, voice)
        if audio_bytes:
            # Encode as base64 and send to client
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            await send_audio_chunk(audio_b64)
        else:
            print(f"⚠️ [AI-TTS] Failed to synthesize: {sentence[:50]}...")

    # Signal that AI is done speaking
    await send_state("listening")
